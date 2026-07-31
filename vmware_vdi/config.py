"""Configuration management for VMware / Omnissa Horizon VDI.

Loads targets and settings from a YAML config file + environment variables.
Passwords are NEVER stored in config files — always via environment variables
(``VMWARE_VDI_<TARGET>_PASSWORD``), obfuscated at rest to ``b64:`` form.

A Horizon target differs from a vCenter target in one field: ``domain`` (the
Active Directory domain the Connection Server authenticates the admin account
against). Everything else mirrors the family's REST-wrapper config.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv, set_key

CONFIG_DIR = Path.home() / ".vmware-vdi"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

_log = logging.getLogger("vmware-vdi.config")

_PW_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*_PASSWORD")


class ConfigError(Exception):
    """Configuration is missing or invalid (e.g. a password env var is unset)."""


def _is_b64_token(value: str) -> tuple[bool, str]:
    """Return ``(True, decoded)`` if ``value`` is a valid ``b64:`` token, else ``(False, "")``.

    A value that merely *starts with* ``b64:`` but is not valid base64 (e.g. a
    real password ``b64:hunter2``) is treated as plaintext, so it still
    round-trips correctly instead of being corrupted.
    """
    if not value.startswith("b64:"):
        return (False, "")
    try:
        return (True, base64.b64decode(value[4:], validate=True).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return (False, "")


def _decode_secret(value: str) -> str:
    """Decode a ``b64:`` token; any other value passes through unchanged (obfuscation, not encryption)."""
    ok, decoded = _is_b64_token(value)
    return decoded if ok else value


def _autoencode_env_file(env_file: Path) -> None:
    """Rewrite plaintext ``*_PASSWORD`` values in .env to grep-safe ``b64:`` form.

    Read and written through python-dotenv's own parser/serializer so the stored
    value is exactly what ``load_dotenv`` returns — the secret never drifts.
    Idempotent; only ``*_PASSWORD`` keys are touched. Obfuscation, not encryption.
    """
    if not env_file.exists():
        return
    try:
        parsed = dotenv_values(env_file)
    except OSError:
        return

    changed = False
    for key, value in parsed.items():
        if not value or not _PW_KEY_RE.fullmatch(key) or _is_b64_token(value)[0]:
            continue
        encoded = "b64:" + base64.b64encode(value.encode("utf-8")).decode("ascii")
        try:
            set_key(str(env_file), key, encoded, quote_mode="never")
            changed = True
        except OSError as exc:
            _log.warning("Could not auto-encode %s in %s: %s", key, env_file, exc)

    if not changed:
        return
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass
    _log.warning(
        "Auto-encoded plaintext password(s) in %s to b64: (grep-safe; obfuscation, not encryption).",
        env_file,
    )


_autoencode_env_file(ENV_FILE)
load_dotenv(ENV_FILE)


def _check_env_permissions() -> None:
    """Warn if .env has permissions wider than owner-only (600)."""
    if not ENV_FILE.exists():
        return
    try:
        mode = ENV_FILE.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            _log.warning(
                "Security warning: %s has permissions %s (should be 600). Run: chmod 600 %s",
                ENV_FILE,
                oct(stat.S_IMODE(mode)),
                ENV_FILE,
            )
    except OSError:
        pass


_check_env_permissions()


@dataclass(frozen=True)
class TargetConfig:
    """A Horizon Connection Server connection target."""

    host: str
    username: str
    domain: str = ""
    """Active Directory domain the Connection Server authenticates against.

    Horizon's ``/rest/login`` takes ``{name, password, domain}``. A local
    Connection Server admin may leave this empty; a domain admin must set it.
    """
    port: int = 443
    verify_ssl: bool = True
    environment: str = ""
    """Optional free-form label a policy ``deny`` rule may scope itself to (see vmware_policy.environment)."""

    def get_password(self, target_name: str) -> str:
        """Retrieve password from ``VMWARE_VDI_<TARGET>_PASSWORD`` (upper-cased, hyphens→underscores)."""
        env_key = f"VMWARE_VDI_{target_name.upper().replace('-', '_')}_PASSWORD"
        pw = os.environ.get(env_key, "")
        if not pw:
            raise ConfigError(f"Password not found. Set environment variable: {env_key}")
        return _decode_secret(pw)

    def get_username(self, target_name: str) -> str:
        """Retrieve username from ``VMWARE_VDI_<TARGET>_USERNAME``, falling back to config.

        Resolved on every call (never cached at load time) so a rotated username
        takes effect at the same moment as the rotated password — the halves must
        not drift apart. Not ``b64:``-decoded; a username is not a secret.
        """
        env_key = f"VMWARE_VDI_{target_name.upper().replace('-', '_')}_USERNAME"
        return os.environ.get(env_key, "") or self.username


@dataclass(frozen=True)
class AppConfig:
    """Top-level application config."""

    targets: dict[str, TargetConfig] = field(default_factory=dict)
    default_target: str | None = None

    def get_target(self, name: str) -> TargetConfig | None:
        return self.targets.get(name)

    def environment_for(self, name: str | None) -> str:
        target = self.get_target(name or self.default_target or "")
        return target.environment if target else ""

    def get_target_strict(self, name: str) -> TargetConfig:
        cfg = self.get_target(name)
        if cfg is None:
            available = ", ".join(self.targets.keys())
            raise ConfigError(
                f"Target '{name}' not found. Available: {available or '(none)'}. "
                f"Pass --target with one of those names, or add a '{name}' entry "
                f"under 'targets:' in {CONFIG_FILE} and re-run."
            )
        return cfg


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML, with env var overrides for credentials."""
    env_override = os.environ.get("VMWARE_VDI_CONFIG")
    path = config_path or (Path(env_override) if env_override else CONFIG_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\nCopy config.example.yaml to {CONFIG_FILE} and edit it."
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if isinstance(raw, dict) and "read_only" in raw:
        _log.warning(
            "'read_only' in config is no longer honored (the skill-level read-only switch was removed). "
            "To run this agent read-only, point it at a read-only Horizon admin account (RBAC) — enforced "
            "at the Connection Server. Remove the 'read_only' key to silence this warning."
        )

    targets: dict[str, TargetConfig] = {}
    for name, t in raw.get("targets", {}).items():
        targets[name] = TargetConfig(
            host=t["host"],
            username=t.get("username", "administrator"),
            domain=str(t.get("domain", "") or "").strip(),
            port=t.get("port", 443),
            verify_ssl=t.get("verify_ssl", True),
            environment=str(t.get("environment", "") or "").strip(),
        )

    default = raw.get("default_target")
    if default and default not in targets:
        _log.warning("default_target '%s' not found in targets, ignoring", default)
        default = None

    return AppConfig(targets=targets, default_target=default)
