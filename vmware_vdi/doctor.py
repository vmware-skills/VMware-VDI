"""Environment diagnostics for vmware-vdi: config, credentials, connectivity."""

from __future__ import annotations

from vmware_vdi.config import ConfigError, load_config, resolve_config_path


def _check_config() -> tuple[bool, str]:
    """Report on the file the tools will open, not on the default path.

    This asked whether the default existed, while load_config() — which the two
    checks below call, and which every tool calls — honours $VMWARE_VDI_CONFIG.
    So with the variable naming a good config and nothing at the default, the
    doctor answered "Config file missing" and told the operator to create a
    second file that would then be ignored, in the same report that went on to
    list the real file's targets (2026-08-30). The path is named in both the
    pass and the fail answer for the same reason: a verdict about an unnamed
    file is not one the reader can check.
    """
    path = resolve_config_path()
    if not path.exists():
        return False, f"Config file missing — copy config.example.yaml to {path}"
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — doctor reports, never raises
        return False, f"Config unreadable: {exc}"
    if not cfg.targets:
        return False, f"No targets defined in {path}"
    return True, (
        f"{path}: {len(cfg.targets)} target(s) configured; "
        f"default={cfg.default_target or '(none)'}"
    )


def _check_credentials() -> tuple[bool, str]:
    try:
        cfg = load_config()
    except Exception:  # noqa: BLE001
        return False, "Config not loadable — fix the config check first"
    missing = []
    for name, target in cfg.targets.items():
        try:
            target.get_password(name)
        except ConfigError:
            missing.append(f"VMWARE_VDI_{name.upper().replace('-', '_')}_PASSWORD")
    if missing:
        return False, "Missing password env var(s): " + ", ".join(missing)
    return True, "All target passwords present in ~/.vmware-vdi/.env"


def _check_connectivity() -> tuple[bool, str]:
    from vmware_vdi.connection import ConnectionManager, VdiApiError

    try:
        mgr = ConnectionManager.from_config()
    except Exception as exc:  # noqa: BLE001
        return False, f"Cannot build connection manager: {exc}"
    cfg = load_config()
    if not cfg.default_target:
        return True, "Connectivity check skipped (no default_target set)"
    try:
        client = mgr.connect(cfg.default_target)
        client.get("/monitor/v1/connection-servers", retries=0)
        return True, f"Reached Connection Server '{cfg.default_target}'"
    except VdiApiError as exc:
        return False, f"Connection Server unreachable: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Connectivity error: {exc}"


CHECKS = [
    ("Config", _check_config),
    ("Credentials", _check_credentials),
    ("Connectivity", _check_connectivity),
]


def run_doctor() -> int:
    """Run all checks, print results, return 0 if all pass else 1."""
    from rich.console import Console

    console = Console()
    console.print("\n[bold cyan]vmware-vdi doctor[/]\n")
    ok_all = True
    for name, check in CHECKS:
        ok, msg = check()
        ok_all = ok_all and ok
        mark = "[green]✓[/]" if ok else "[red]✗[/]"
        console.print(f"  {mark} [bold]{name}[/]: {msg}")
    console.print()
    return 0 if ok_all else 1
