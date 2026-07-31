"""Shared CLI helpers for vmware-vdi: options, connection, confirmation, audit, error wrapping."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from vmware_vdi.config import ConfigError, load_config
from vmware_vdi.connection import ConnectionManager, VdiApiError
from vmware_vdi.notify.audit import AuditLogger
from vmware_vdi.ops._errors import VdiOpsError

console = Console()
_audit = AuditLogger()

TargetOption = Annotated[str | None, typer.Option("--target", "-t", help="Target name from config")]
ConfigOption = Annotated[Path | None, typer.Option("--config", "-c", help="Config file path")]
DryRunOption = Annotated[bool, typer.Option("--dry-run", help="Preview the action without executing")]

# One manager per distinct config path so --config actually selects a config file.
_managers: dict[str, ConnectionManager] = {}


def _resolve_target(target: str | None) -> str:
    return target or "default"


def _get_connection(target: str | None, config_path: Path | None = None):
    """Return (HorizonClient, target_name) for the target, honouring --config if given."""
    key = str(config_path) if config_path else ""
    if key not in _managers:
        cfg = load_config(config_path) if config_path else load_config()
        _managers[key] = ConnectionManager(cfg)
    return _managers[key].connect(target), _resolve_target(target)


def cli_errors(fn):
    """Turn a teaching error (API / ops refusal / config) into a clean red message + exit 1."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (VdiApiError, VdiOpsError, ConfigError, ValueError, FileNotFoundError) as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc

    return wrapper


def _double_confirm(action: str, resource: str, target: str = "default", resource_type: str = "session") -> None:
    """Require two confirmations for a destructive command; audit a 'rejected' entry on abort."""
    console.print(f"[bold yellow]⚠️  About to: {action} {resource_type} '{resource}' on '{target}'[/]")
    try:
        typer.confirm(f"Confirm 1/2: {action} '{resource}'?", abort=True)
        typer.confirm(f"Confirm 2/2: really {action} '{resource}'? This cannot be undone.", abort=True)
    except typer.Abort:
        _audit.log(target=target, operation=action, resource=resource, result="rejected")
        raise
