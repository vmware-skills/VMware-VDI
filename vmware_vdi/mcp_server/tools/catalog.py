"""Catalog read tools: application pools, instant-clone images, AD principals. Optional[X] (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _get_connection, _safe_error, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def app_pool_list(limit: int = 50, offset: int = 0, target: Optional[str] = None) -> dict:
    """[READ] List published application pools: id, name, farm, enabled, executable path. Paginated.

    Args:
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.apps import list_application_pools

        return list_application_pools(_get_connection(target), limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "app_pool_list")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def image_list(base_vm_id: Optional[str] = None, target: Optional[str] = None) -> dict:
    """[READ] List instant-clone base VMs and snapshots (the golden-image catalog for pool_push_image).

    Args:
        base_vm_id: Optionally scope snapshots to one base VM.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.images import list_images

        return list_images(_get_connection(target), base_vm_id=base_vm_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "image_list")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ad_user_search(name: str, limit: int = 25, target: Optional[str] = None) -> dict:
    """[READ] Resolve AD users/groups by name to their SIDs — needed to entitle a pool (entitlement_add).

    Args:
        name: Name substring to search for.
        limit: Max principals to return (default 25).
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import search_ad

        return search_ad(_get_connection(target), name, limit=limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "ad_user_search")}
