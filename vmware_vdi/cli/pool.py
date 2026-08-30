"""CLI: Horizon desktop-pool commands (list/get/enable/disable/push-image)."""

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

pool_app = typer.Typer(help="Horizon desktop pools: list, enable/disable, push image.")


@pool_app.command("list")
@cli_errors
def pool_list_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """List desktop pools."""
    from vmware_vdi.ops.pools import list_pools

    client, _ = _get_connection(target, config)
    out = list_pools(client)
    console.print(f"\n[bold cyan]Desktop pools ({out['returned']}/{out['total']}):[/]")
    for p in out["items"]:
        en = "enabled" if p["enabled"] else "disabled"
        console.print(f"  {p['id']}  [cyan]{p['name']}[/]  {p['type']}/{en}  {p['assignment']}")


@pool_app.command("set-enabled")
@cli_errors
@guarded(risk_level="medium")
def pool_set_enabled_cmd(
    pool_id: Annotated[str, typer.Option("--id", help="Pool id")],
    enabled: Annotated[bool, typer.Option("--enable/--disable", help="Enable or disable the pool")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Enable/disable a pool (disable stops new sessions). Idempotent."""
    from vmware_vdi.ops.pools import set_pool_enabled

    client, tname = _get_connection(target, config)
    preview = set_pool_enabled(client, pool_id=pool_id, enabled=enabled, confirm=False)
    if preview["action"] == "noop":
        console.print(f"[dim]{preview['hint']}[/]")
        return
    if dry_run:
        console.print(f"[magenta][DRY-RUN] would {'enable' if enabled else 'disable'} pool {pool_id}[/]")
        return
    _double_confirm("enable" if enabled else "disable", pool_id, _resolve_target(target), resource_type="pool")
    out = set_pool_enabled(client, pool_id=pool_id, enabled=enabled, confirm=True,
                           audit_logger=_audit, target_name=tname)
    console.print(f"[green]{out['action']}[/]: {out.get('hint', pool_id)}")


@pool_app.command("push-image")
@cli_errors
@guarded(risk_level="high")
def pool_push_image_cmd(
    pool_id: Annotated[str, typer.Option("--id", help="Pool id")],
    force_logoff: Annotated[bool, typer.Option("--force-logoff", help="FORCE_LOGOFF instead of WAIT_FOR_LOGOFF")] = False,
    acknowledge_unknown_occupancy: Annotated[
        bool,
        typer.Option(
            "--acknowledge-unknown-occupancy",
            help="Push even when who is logged in could not be determined (audited).",
        ),
    ] = False,
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Apply the pending image to an instant-clone pool — recreates EVERY desktop. Double-confirm + --dry-run."""
    from vmware_vdi.ops.pools import push_image

    policy = "FORCE_LOGOFF" if force_logoff else "WAIT_FOR_LOGOFF"
    client, tname = _get_connection(target, config)
    preview = push_image(client, pool_id=pool_id, logoff_policy=policy, confirm=False)
    b = preview["blast_radius"]
    if b["occupancy"] == "unknown":
        # Never print a count here: the number is a lower bound, and printed next to
        # "BLAST RADIUS" a lower bound of 0 reads as an all-clear.
        console.print(
            f"[bold red]BLAST RADIUS:[/] recreates [cyan]{b['affected_desktops']}[/] desktop(s); "
            f"[bold yellow]who is logged in could not be determined[/] — {b['occupancy_note']}"
        )
    else:
        console.print(
            f"[bold red]BLAST RADIUS:[/] recreates [cyan]{b['affected_desktops']}[/] desktop(s), "
            f"affecting [cyan]{b['in_session_count']}[/] logged-in session(s): {', '.join(b['users']) or '-'}"
        )
    if dry_run:
        console.print("[magenta][DRY-RUN] no changes made.[/]")
        return
    _double_confirm("push image to", pool_id, _resolve_target(target), resource_type="pool")
    push_image(client, pool_id=pool_id, logoff_policy=policy, confirm=True,
               acknowledge_unknown_occupancy=acknowledge_unknown_occupancy,
               audit_logger=_audit, target_name=tname)
    console.print("[green]image push scheduled[/]")
