"""CLI: application pools, images, AD search, entitlement writes, pool tasks."""

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
from vmware_vdi.cli.monitor import entitlement_app

app_pool_app = typer.Typer(help="Horizon application pools (read).")
task_app = typer.Typer(help="Horizon pool tasks (image push / provisioning).")


@app_pool_app.command("list")
@cli_errors
def app_pool_list_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """List published application pools."""
    from vmware_vdi.ops.apps import list_application_pools

    client, _ = _get_connection(target, config)
    for a in list_application_pools(client)["items"]:
        en = "enabled" if a["enabled"] else "disabled"
        console.print(f"  {a['id']}  [cyan]{a['name']}[/]  {en}  farm={a['farm_id']}")


@cli_errors
def images_cmd(target: TargetOption = None, config: ConfigOption = None) -> None:
    """List instant-clone base VMs and snapshots (the image catalog)."""
    from vmware_vdi.ops.images import list_images

    client, _ = _get_connection(target, config)
    out = list_images(client)
    console.print(f"\n[bold cyan]Base VMs ({out['base_vm_count']}):[/]")
    for b in out["base_vms"]:
        console.print(f"  {b['id']}  [cyan]{b['name']}[/]")
    console.print(f"[bold cyan]Snapshots ({out['snapshot_count']}):[/]")
    for s in out["snapshots"]:
        console.print(f"  {s['id']}  {s['name']}  base={s['base_vm_id']}")


@cli_errors
def ad_search_cmd(
    name: Annotated[str, typer.Argument(help="AD user/group name substring")],
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """Resolve AD users/groups to SIDs (for entitlement add)."""
    from vmware_vdi.ops.entitlements import search_ad

    client, _ = _get_connection(target, config)
    for p in search_ad(client, name)["principals"]:
        console.print(f"  {p['type']}  [cyan]{p['name']}[/]  {p['id']}  ({p['domain']})")


@entitlement_app.command("add")
@cli_errors
@guarded(risk_level="medium")
def entitlement_add_cmd(
    pool_id: Annotated[str, typer.Option("--pool", help="Desktop pool id")],
    sid: Annotated[list[str], typer.Option("--sid", help="AD SID (repeat; from ad-search)")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Grant pool access to AD user/group SID(s)."""
    from vmware_vdi.ops.entitlements import entitle

    client, tname = _get_connection(target, config)
    if dry_run:
        out = entitle(client, pool_id=pool_id, ad_user_or_group_ids=sid, confirm=False)
        console.print(f"[magenta][DRY-RUN] would entitle {out['would_entitle']}[/]")
        return
    entitle(client, pool_id=pool_id, ad_user_or_group_ids=sid, confirm=True, audit_logger=_audit, target_name=tname)
    console.print(f"[green]entitled {len(sid)} principal(s) to {pool_id}[/]")


@entitlement_app.command("remove")
@cli_errors
@guarded(risk_level="medium")
def entitlement_remove_cmd(
    pool_id: Annotated[str, typer.Option("--pool", help="Desktop pool id")],
    sid: Annotated[list[str], typer.Option("--sid", help="AD SID (repeat; from entitlement list)")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Revoke pool access from AD user/group SID(s)."""
    from vmware_vdi.ops.entitlements import unentitle

    client, tname = _get_connection(target, config)
    if dry_run:
        out = unentitle(client, pool_id=pool_id, ad_user_or_group_ids=sid, confirm=False)
        console.print(f"[magenta][DRY-RUN] would revoke {out['would_unentitle']}[/]")
        return
    _double_confirm("revoke access to", pool_id, _resolve_target(target), resource_type="pool")
    unentitle(client, pool_id=pool_id, ad_user_or_group_ids=sid, confirm=True, audit_logger=_audit, target_name=tname)
    console.print(f"[green]revoked {len(sid)} principal(s) from {pool_id}[/]")


@task_app.command("status")
@cli_errors
def task_status_cmd(
    pool_id: Annotated[str, typer.Option("--pool", help="Desktop pool id")],
    task_id: Annotated[str, typer.Option("--task", help="Task id (omit to list all)")] = "",
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """Status of a pool task, or all tasks for the pool."""
    from vmware_vdi.ops.tasks import task_status

    client, _ = _get_connection(target, config)
    out = task_status(client, pool_id, task_id or None)
    if task_id:
        console.print(f"  {out['id']}  {out['type']}  [{out['state']}]  {out['progress']}%  {out['message']}")
    else:
        for t in out["tasks"]:
            console.print(f"  {t['id']}  {t['type']}  [{t['state']}]  {t['progress']}%")


@task_app.command("cancel")
@cli_errors
@guarded(risk_level="medium")
def task_cancel_cmd(
    pool_id: Annotated[str, typer.Option("--pool", help="Desktop pool id")],
    task_id: Annotated[str, typer.Option("--task", help="Task id")],
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Cancel a running pool task (e.g. an in-progress image push)."""
    from vmware_vdi.ops.tasks import task_cancel

    client, tname = _get_connection(target, config)
    if dry_run:
        console.print(f"[magenta][DRY-RUN] would cancel task {task_id} on {pool_id}[/]")
        return
    _double_confirm("cancel task", task_id, _resolve_target(target), resource_type="pool task")
    task_cancel(client, pool_id=pool_id, task_id=task_id, confirm=True, audit_logger=_audit, target_name=tname)
    console.print(f"[green]cancel requested for task {task_id}[/]")
