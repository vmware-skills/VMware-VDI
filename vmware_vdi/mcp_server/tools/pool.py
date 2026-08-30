"""Desktop-pool MCP tools (2 read / 2 write). Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _audit, _get_connection, _safe_error, _target_name, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def pool_list(limit: int = 50, offset: int = 0, target: Optional[str] = None) -> dict:
    """[READ] List Horizon desktop pools: id, name, type (AUTOMATED/MANUAL/RDS), enabled, assignment.

    The verify pair for pool_set_enabled and pool_push_image. Paginated envelope.

    Args:
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.pools import list_pools

        return list_pools(_get_connection(target), limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "pool_list")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def pool_get(pool_id: str, target: Optional[str] = None) -> dict:
    """[READ] One desktop pool by id (teaching 404 on a wrong id).

    Same projection as one pool_list row — id, name, type, enabled, provisioning_enabled,
    assignment — fetched with a single GET instead of listing every pool. Use it to
    re-check one pool after a write, or when you already hold an id.

    Args:
        pool_id: Horizon desktop-pool id (the opaque 'id' of a pool_list row, not the
            pool's display name). A wrong id returns a 404 whose hint tells you to
            re-run pool_list for exact ids.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.pools import get_pool

        return get_pool(_get_connection(target), pool_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "pool_get")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def pool_set_enabled(
    pool_id: str,
    enabled: bool,
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Enable or disable a desktop pool — disabling stops NEW sessions (existing keep running).

    Idempotent (matching state returns a noop). confirm=False previews; confirm=True applies. Audited.

    Args:
        pool_id: The pool id (from pool_list).
        enabled: True enables; False disables.
        confirm: False previews; True applies.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.pools import set_pool_enabled

        return set_pool_enabled(_get_connection(target), pool_id=pool_id, enabled=enabled, confirm=confirm,
                                audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "pool_set_enabled")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def pool_push_image(
    pool_id: str,
    stop_on_error: bool = True,
    logoff_policy: str = "WAIT_FOR_LOGOFF",
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Apply the pending image to an instant-clone pool — RECREATES EVERY DESKTOP in it.

    Highest blast radius in the family: the preview states affected-desktop and in-session-user
    counts before you confirm. confirm=True schedules the apply. Audited.

    Args:
        pool_id: The pool id (from pool_list).
        stop_on_error: Halt the rolling push on the first machine error (default True).
        logoff_policy: WAIT_FOR_LOGOFF (default) or FORCE_LOGOFF.
        confirm: False previews the blast radius; True schedules the push.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.pools import push_image

        return push_image(_get_connection(target), pool_id=pool_id, stop_on_error=stop_on_error,
                          logoff_policy=logoff_policy, confirm=confirm, audit_logger=_audit,
                          target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "pool_push_image")}
