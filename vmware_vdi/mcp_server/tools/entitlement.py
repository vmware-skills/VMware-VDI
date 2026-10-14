"""Entitlement MCP tools (1 read / 2 write). Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _audit, _get_connection, _safe_error, _target_name, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def list_entitlements(pool_id: str, limit: int = 50, offset: int = 0, target: Optional[str] = None) -> dict:
    """[READ] List the AD users/groups entitled to a desktop pool (who can access it). Paginated.

    A wrong pool id returns a teaching 404. Use list_desktop_pools for pool ids.

    Args:
        pool_id: The desktop-pool id (from list_desktop_pools).
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import list_entitlements as _ops_list_entitlements

        return _ops_list_entitlements(_get_connection(target), pool_id, limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "list_entitlements")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def add_entitlement(
    pool_id: str,
    ad_user_or_group_ids: list[str],
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Grant desktop-pool access to AD user/group SID(s).

    Get SIDs from search_ad_users. A bare call returns blast_radius (pool identity, which
    principals are already entitled and which are new) and grants nothing; confirm=True
    grants. Refused when the pool's current entitlements cannot be read.
    Show blast_radius to the user and wait for their decision. Do not set confirm=True
    on your own because the user asked for this earlier: they have not seen the blast
    radius yet.
    Audited.

    Args:
        pool_id: The desktop-pool id (from list_desktop_pools).
        ad_user_or_group_ids: AD SIDs to entitle (from search_ad_users).
        confirm: False (default) returns the blast radius and changes nothing. True grants.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import entitle

        return entitle(_get_connection(target), pool_id=pool_id, ad_user_or_group_ids=ad_user_or_group_ids,
                       confirm=confirm, audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "add_entitlement")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def remove_entitlement(
    pool_id: str,
    ad_user_or_group_ids: list[str],
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Revoke desktop-pool access from AD user/group SID(s).

    Get SIDs from list_entitlements. A bare call returns blast_radius (pool identity, which
    principals lose access and which were not entitled) and revokes nothing; confirm=True
    revokes. Refused when the pool's current entitlements cannot be read.
    Show blast_radius to the user and wait for their decision. Do not set confirm=True
    on your own because the user asked for this earlier: they have not seen the blast
    radius yet.
    Audited.

    Args:
        pool_id: The desktop-pool id (from list_desktop_pools).
        ad_user_or_group_ids: AD SIDs to remove (from list_entitlements).
        confirm: False (default) returns the blast radius and changes nothing. True revokes.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import unentitle

        return unentitle(_get_connection(target), pool_id=pool_id, ad_user_or_group_ids=ad_user_or_group_ids,
                         confirm=confirm, audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "remove_entitlement")}
