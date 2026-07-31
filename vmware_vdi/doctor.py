"""Environment diagnostics for vmware-vdi: config, credentials, connectivity."""

from __future__ import annotations

from vmware_vdi.config import CONFIG_FILE, ConfigError, load_config


def _check_config() -> tuple[bool, str]:
    if not CONFIG_FILE.exists():
        return False, f"Config file missing — copy config.example.yaml to {CONFIG_FILE}"
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — doctor reports, never raises
        return False, f"Config unreadable: {exc}"
    if not cfg.targets:
        return False, "No targets defined in config.yaml"
    return True, f"{len(cfg.targets)} target(s) configured; default={cfg.default_target or '(none)'}"


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
