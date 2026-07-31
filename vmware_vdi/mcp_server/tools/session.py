"""Session MCP tools (2 read / 3 write) — the help-desk surface.

session_list, session_get [READ]; session_logoff, session_disconnect,
session_send_message [WRITE]. Signatures use ``Optional[X]`` (not PEP 604) because
FastMCP/Pydantic reflect them under interpreters where the union form can raise
(踩坑 #33).
"""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _audit, _get_connection, _safe_error, _target_name, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def session_list(
    user: Optional[str] = None,
    pool: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    target: Optional[str] = None,
) -> dict:
    """[READ] List Horizon VDI sessions, filtered by user / pool id / state. Paginated.

    Returns a {items, returned, limit, total, truncated, hint} envelope; each item has
    id, user, type (DESKTOP/APPLICATION), state (CONNECTED/DISCONNECTED/PENDING),
    protocol (BLAST/PCOIP/RDP), pool_id, machine_id, start_time. This is the verify
    pair for logoff/disconnect — get a session id or confirm a user's sessions here first.

    Args:
        user: Substring-match the AD user name.
        pool: Exact desktop-pool / farm id.
        state: CONNECTED, DISCONNECTED, or PENDING.
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.sessions import list_sessions

        return list_sessions(
            _get_connection(target), user=user, pool=pool, state=state, limit=limit, offset=offset
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "session_list")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def session_get(session_id: str, target: Optional[str] = None) -> dict:
    """[READ] Full detail for one Horizon session by id.

    A wrong id returns a teaching error ("run session_list for current ids"), not a
    traceback. Use session_list to discover ids.

    Args:
        session_id: The session id (from session_list).
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.sessions import get_session

        return get_session(_get_connection(target), session_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "session_get")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def session_logoff(
    session_ids: Optional[list[str]] = None,
    user: Optional[str] = None,
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Force-logoff Horizon session(s) — kicks the user, triggers profile write-back.

    Identify targets by explicit session_ids OR by user (all of that user's sessions).
    confirm=False (default) returns a preview stating the blast radius — session count
    and affected user names — without acting; re-run with confirm=True to apply. Audited.

    Args:
        session_ids: Session ids to log off (from session_list).
        user: Log off all sessions of this AD user (substring match); refuses if none match.
        confirm: False previews; True logs off.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.sessions import logoff_sessions

        return logoff_sessions(
            _get_connection(target), session_ids=session_ids, user=user,
            confirm=confirm, audit_logger=_audit, target_name=_target_name(target),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "session_logoff")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def session_disconnect(
    session_ids: Optional[list[str]] = None,
    user: Optional[str] = None,
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Disconnect Horizon session(s) — state preserved, the user can reconnect.

    Less disruptive than logoff. Identify by session_ids OR user. confirm=False previews
    the blast radius; confirm=True applies. Audited.

    Args:
        session_ids: Session ids to disconnect.
        user: Disconnect all sessions of this AD user (substring match).
        confirm: False previews; True disconnects.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.sessions import disconnect_sessions

        return disconnect_sessions(
            _get_connection(target), session_ids=session_ids, user=user,
            confirm=confirm, audit_logger=_audit, target_name=_target_name(target),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "session_disconnect")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="low")
def session_send_message(
    message: str,
    session_ids: Optional[list[str]] = None,
    user: Optional[str] = None,
    message_type: str = "INFO",
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Send a message to Horizon session(s) — e.g. "save your work, maintenance in 10 min".

    Low blast radius (informational only, no session disruption), so no confirm gate.
    Identify by session_ids OR user. Audited.

    Args:
        message: The text to display to the user(s).
        session_ids: Session ids to message.
        user: Message all sessions of this AD user (substring match).
        message_type: INFO, WARNING, or ERROR.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.sessions import send_message

        return send_message(
            _get_connection(target), message=message, session_ids=session_ids, user=user,
            message_type=message_type, audit_logger=_audit, target_name=_target_name(target),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "session_send_message")}
