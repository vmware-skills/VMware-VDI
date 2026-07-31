"""CLI: Horizon session commands (list/logoff/disconnect/message).

Writes are wrapped in @guarded (policy + audit via vmware_policy) and destructive
ones add an interactive double-confirm + --dry-run, per the family convention.
"""

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

session_app = typer.Typer(help="Horizon VDI sessions: list, logoff, disconnect, message.")


def _print_blast(blast: dict) -> None:
    console.print(f"  sessions: [cyan]{blast['session_count']}[/]  users: {', '.join(blast['affected_users']) or '-'}")
    for s in blast["sessions"]:
        console.print(f"    - {s['id']}  {s['user']}  [{s['state']}]")


@session_app.command("list")
@cli_errors
def session_list_cmd(
    user: Annotated[str, typer.Option("--user", help="Filter by AD user (substring)")] = "",
    pool: Annotated[str, typer.Option("--pool", help="Filter by pool/farm id")] = "",
    state: Annotated[str, typer.Option("--state", help="CONNECTED|DISCONNECTED|PENDING")] = "",
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """List Horizon sessions."""
    from vmware_vdi.ops.sessions import list_sessions

    client, _ = _get_connection(target, config)
    out = list_sessions(client, user=user or None, pool=pool or None, state=state or None)
    console.print(f"\n[bold cyan]Sessions ({out['returned']}/{out['total']}):[/]")
    for s in out["items"]:
        console.print(f"  {s['id']}  [cyan]{s['user']}[/]  {s['type']}/{s['state']}/{s['protocol']}  pool={s['pool_id']}")
    if out["truncated"]:
        console.print(f"  [dim]{out['hint']}[/]")


@session_app.command("logoff")
@cli_errors
@guarded(risk_level="high")
def session_logoff_cmd(
    session_id: Annotated[str, typer.Option("--id", help="Session id")] = "",
    user: Annotated[str, typer.Option("--user", help="Log off all sessions of this AD user")] = "",
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Force-logoff session(s) — kicks the user. Double-confirm + --dry-run."""
    from vmware_vdi.ops.sessions import logoff_sessions

    ids = [session_id] if session_id else None
    client, tname = _get_connection(target, config)
    if dry_run:
        out = logoff_sessions(client, session_ids=ids, user=user or None, confirm=False)
        console.print("[magenta][DRY-RUN] would logoff:[/]")
        _print_blast(out["would_affect"])
        return
    preview = logoff_sessions(client, session_ids=ids, user=user or None, confirm=False)
    _print_blast(preview["would_affect"])
    _double_confirm("logoff", session_id or f"user:{user}", _resolve_target(target), resource_type="session(s)")
    out = logoff_sessions(
        client, session_ids=ids, user=user or None, confirm=True, audit_logger=_audit, target_name=tname
    )
    console.print(f"[green]logged off {out['affected']['session_count']} session(s)[/]")


@session_app.command("disconnect")
@cli_errors
@guarded(risk_level="medium")
def session_disconnect_cmd(
    session_id: Annotated[str, typer.Option("--id", help="Session id")] = "",
    user: Annotated[str, typer.Option("--user", help="Disconnect all sessions of this AD user")] = "",
    target: TargetOption = None,
    config: ConfigOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Disconnect session(s) — state preserved. Double-confirm + --dry-run."""
    from vmware_vdi.ops.sessions import disconnect_sessions

    ids = [session_id] if session_id else None
    client, tname = _get_connection(target, config)
    if dry_run:
        out = disconnect_sessions(client, session_ids=ids, user=user or None, confirm=False)
        console.print("[magenta][DRY-RUN] would disconnect:[/]")
        _print_blast(out["would_affect"])
        return
    preview = disconnect_sessions(client, session_ids=ids, user=user or None, confirm=False)
    _print_blast(preview["would_affect"])
    _double_confirm("disconnect", session_id or f"user:{user}", _resolve_target(target), resource_type="session(s)")
    out = disconnect_sessions(
        client, session_ids=ids, user=user or None, confirm=True, audit_logger=_audit, target_name=tname
    )
    console.print(f"[green]disconnected {out['affected']['session_count']} session(s)[/]")


@session_app.command("message")
@cli_errors
@guarded(risk_level="low")
def session_message_cmd(
    message: Annotated[str, typer.Argument(help="Message text")],
    user: Annotated[str, typer.Option("--user", help="Message all sessions of this AD user")] = "",
    session_id: Annotated[str, typer.Option("--id", help="Session id")] = "",
    message_type: Annotated[str, typer.Option("--type", help="INFO|WARNING|ERROR")] = "INFO",
    target: TargetOption = None,
    config: ConfigOption = None,
) -> None:
    """Send a message to session(s) (low-risk, no confirm)."""
    from vmware_vdi.ops.sessions import send_message

    ids = [session_id] if session_id else None
    client, tname = _get_connection(target, config)
    out = send_message(
        client, message=message, session_ids=ids, user=user or None,
        message_type=message_type, audit_logger=_audit, target_name=tname,
    )
    console.print(f"[green]sent to {out['sent_to']['session_count']} session(s)[/]")
