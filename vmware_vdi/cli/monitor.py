"""CLI: read-only monitoring / statistics / events / farms / entitlements."""

from __future__ import annotations

from typing import Annotated

import typer

from vmware_vdi.cli._common import ConfigOption, TargetOption, _get_connection, cli_errors, console

farm_app = typer.Typer(help="Horizon RDS farms (read).")
entitlement_app = typer.Typer(help="Horizon pool entitlements (read).")


@cli_errors
def health_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """One-glance VDI health summary."""
    from vmware_vdi.ops.monitor import health_summary

    client, _ = _get_connection(target, config)
    h = health_summary(client)
    console.print("\n[bold cyan]VDI health[/]")
    console.print(f"  sessions: {h['sessions']['total']}  {h['sessions']['by_state']}")
    console.print(f"  machines: {h['machines']['total']} (problem: {h['machines']['problem']} {h['machines']['problem_by_state']})")
    console.print(f"  pools: {h['pools']['enabled']} enabled / {h['pools']['disabled']} disabled")
    console.print(f"  [dim]{h['hint']}[/]")


@cli_errors
def stats_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """Session statistics (concurrency by state/protocol, busiest pools)."""
    from vmware_vdi.ops.monitor import session_stats

    client, _ = _get_connection(target, config)
    s = session_stats(client)
    console.print(f"\n[bold cyan]Session stats[/]  concurrent={s['current_concurrent']} total={s['total_sessions']}")
    console.print(f"  by_state: {s['by_state']}\n  by_protocol: {s['by_protocol']}")
    for p in s["top_pools"]:
        console.print(f"    {p['pool_id']}: {p['sessions']}")


@cli_errors
def utilization_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """Per-pool desktop utilization."""
    from vmware_vdi.ops.monitor import pool_utilization

    client, _ = _get_connection(target, config)
    for p in pool_utilization(client)["pools"]:
        console.print(f"  [cyan]{p['pool_name'] or p['pool_id']}[/]  {p['utilization_pct']}%  "
                      f"(total {p['total']}, avail {p['available']}, in-use {p['in_use']}, err {p['error']})")


@cli_errors
def events_cmd(
    severity: Annotated[str, typer.Option("--severity", help="ERROR|WARNING|...")] = "",
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """List recent Horizon audit events."""
    from vmware_vdi.ops.monitor import list_events

    client, _ = _get_connection(target, config)
    out = list_events(client, severity=severity or None)
    console.print(f"\n[bold cyan]Events ({out['returned']}/{out['total']}):[/]")
    for e in out["items"]:
        console.print(f"  [{e['severity']}] {e['time']}  {e['user']}  {e['message']}")


@farm_app.command("list")
@cli_errors
def farm_list_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """List RDS farms."""
    from vmware_vdi.ops.farms import list_farms

    client, _ = _get_connection(target, config)
    for f in list_farms(client)["items"]:
        en = "enabled" if f["enabled"] else "disabled"
        console.print(f"  {f['id']}  [cyan]{f['name']}[/]  {f['type']}/{en}  servers={f['rds_server_count']}")


@entitlement_app.command("list")
@cli_errors
def entitlement_list_cmd(
    pool_id: Annotated[str, typer.Option("--pool", help="Desktop pool id")],
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """List AD users/groups entitled to a pool."""
    from vmware_vdi.ops.entitlements import list_entitlements

    client, _ = _get_connection(target, config)
    for e in list_entitlements(client, pool_id)["items"]:
        console.print(f"  {e['type']}  [cyan]{e['principal']}[/]  {e['principal_id']}")
