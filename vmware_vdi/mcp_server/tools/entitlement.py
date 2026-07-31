"""Entitlement MCP tools (1 read / 2 write). Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _audit, _get_connection, _safe_error, _target_name, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def entitlement_list(pool_id: str, limit: int = 50, offset: int = 0, target: Optional[str] = None) -> dict:
    """[READ] List the AD users/groups entitled to a desktop pool (who can access it). Paginated.

    A wrong pool id returns a teaching 404. Use pool_list for pool ids.

    Args:
        pool_id: The desktop-pool id (from pool_list).
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import list_entitlements

        return list_entitlements(_get_connection(target), pool_id, limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "entitlement_list")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def entitlement_add(
    pool_id: str,
    ad_user_or_group_ids: list[str],
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Grant desktop-pool access to AD user/group SID(s).

    Get SIDs from ad_user_search. confirm=False previews; confirm=True grants. Audited.

    Args:
        pool_id: The desktop-pool id (from pool_list).
        ad_user_or_group_ids: AD SIDs to entitle (from ad_user_search).
        confirm: False previews; True grants.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import entitle

        return entitle(_get_connection(target), pool_id=pool_id, ad_user_or_group_ids=ad_user_or_group_ids,
                       confirm=confirm, audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "entitlement_add")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def entitlement_remove(
    pool_id: str,
    ad_user_or_group_ids: list[str],
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Revoke desktop-pool access from AD user/group SID(s).

    Get SIDs from entitlement_list. confirm=False previews; confirm=True revokes. Audited.

    Args:
        pool_id: The desktop-pool id (from pool_list).
        ad_user_or_group_ids: AD SIDs to remove (from entitlement_list).
        confirm: False previews; True revokes.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import unentitle

        return unentitle(_get_connection(target), pool_id=pool_id, ad_user_or_group_ids=ad_user_or_group_ids,
                         confirm=confirm, audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "entitlement_remove")}
