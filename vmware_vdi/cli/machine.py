"""CLI: Horizon desktop-machine commands (list/get/reset/maintenance/remove)."""

from __future__ import annotations

from typing import Annotated

import typer
from vmware_policy import guarded

from vmware_vdi.cli._common import (
    ConfigOption,
    DryRunOption,
    TargetOption,
    _audit,
    _double_confirm,
    _get_connection,
    _resolve_target,
    cli_errors,
    console,
)

machine_app = typer.Typer(help="Horizon desktop machines: list, reset, maintenance, remove.")


def _print_blast(blast: dict) -> None:
    console.print(f"  machines: [cyan]{blast['machine_count']}[/]  users: {', '.join(blast['assigned_users']) or '-'}")
    for m in blast["machines"]:
        console.print(f"    - {m['id']}  {m['name']}  [{m['state']}]  {m['user']}")


@machine_app.command("list")
@cli_errors
def machine_list_cmd(
    pool: Annotated[str, typer.Option("--pool", help="Filter by pool id")] = "",
    state: Annotated[str, typer.Option("--state", help="Machine state, e.g. AGENT_UNREACHABLE")] = "",
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """List desktop machines."""
    from vmware_vdi.ops.machines import list_machines

    client, _ = _get_connection(target, config)
    out = list_machines(client, pool=pool or None, state=state or None)
    console.print(f"\n[bold cyan]Machines ({out['returned']}/{out['total']}):[/]")
    for m in out["items"]:
        console.print(f"  {m['id']}  [cyan]{m['name']}[/]  {m['state']}  pool={m['pool_id']}  {m['user']}")
    if out["truncated"]:
        console.print(f"  [dim]{out['hint']}[/]")


def _ids(machine_id: str) -> list[str]:
    return [machine_id] if machine_id else []


@machine_app.command("reset")
@cli_errors
@guarded(risk_level="high")
def machine_reset_cmd(
    machine_id: Annotated[str, typer.Option("--id", help="Machine id")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Hard-reset a machine — user loses unsaved state. Double-confirm + --dry-run."""
    from vmware_vdi.ops.machines import reset_machines

    client, tname = _get_connection(target, config)
    preview = reset_machines(client, machine_ids=_ids(machine_id), confirm=False)
    _print_blast(preview["would_affect"])
    if dry_run:
        console.print("[magenta][DRY-RUN] no changes made.[/]")
        return
    _double_confirm("reset", machine_id, _resolve_target(target), resource_type="machine")
    reset_machines(client, machine_ids=_ids(machine_id), confirm=True, audit_logger=_audit, target_name=tname)
    console.print("[green]reset issued[/]")


@machine_app.command("maintenance")
@cli_errors
@guarded(risk_level="medium")
def machine_maintenance_cmd(
    machine_id: Annotated[str, typer.Option("--id", help="Machine id")],
    enabled: Annotated[bool, typer.Option("--enter/--exit", help="Enter or exit maintenance")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Enter/exit maintenance mode for a machine."""
    from vmware_vdi.ops.machines import set_maintenance

    client, tname = _get_connection(target, config)
    preview = set_maintenance(client, machine_ids=_ids(machine_id), enabled=enabled, confirm=False)
    console.print(f"[magenta]{preview['operation']}:[/]")
    _print_blast(preview["would_affect"])
    if dry_run:
        console.print("[magenta][DRY-RUN] no changes made.[/]")
        return
    _double_confirm("enter maintenance" if enabled else "exit maintenance", machine_id,
                    _resolve_target(target), resource_type="machine")
    set_maintenance(client, machine_ids=_ids(machine_id), enabled=enabled, confirm=True,
                    audit_logger=_audit, target_name=tname)
    console.print(f"[green]{'entered' if enabled else 'exited'} maintenance[/]")


@machine_app.command("remove")
@cli_errors
@guarded(risk_level="high")
def machine_remove_cmd(
    machine_id: Annotated[str, typer.Option("--id", help="Machine id")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Remove a machine from its pool (deletes the VM for instant clones). Double-confirm + --dry-run."""
    from vmware_vdi.ops.machines import remove_machines

    client, tname = _get_connection(target, config)
    preview = remove_machines(client, machine_ids=_ids(machine_id), confirm=False)
    _print_blast(preview["would_affect"])
    if dry_run:
        console.print("[magenta][DRY-RUN] no changes made.[/]")
        return
    _double_confirm("remove", machine_id, _resolve_target(target), resource_type="machine")
    remove_machines(client, machine_ids=_ids(machine_id), confirm=True, audit_logger=_audit, target_name=tname)
    console.print("[green]removed[/]")
