"""Catalog read tools: application pools, instant-clone images, AD principals. Optional[X] (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _get_connection, _safe_error, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def list_app_pools(limit: int = 50, offset: int = 0, target: Optional[str] = None) -> dict:
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
        return {"error": _safe_error(exc, "list_app_pools")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def list_vdi_images(base_vm_id: Optional[str] = None, target: Optional[str] = None) -> dict:
    """[READ] List instant-clone base VMs and snapshots (the golden-image catalog for push_desktop_pool_image).

    Args:
        base_vm_id: Optionally scope snapshots to one base VM.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.images import list_images

        return list_images(_get_connection(target), base_vm_id=base_vm_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "list_vdi_images")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def search_ad_users(name: str, limit: int = 25, target: Optional[str] = None) -> dict:
    """[READ] Resolve AD users/groups by name to their SIDs — needed to entitle a pool (add_entitlement).

    Args:
        name: Name substring to search for.
        limit: Max principals to return (default 25).
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.entitlements import search_ad

        return search_ad(_get_connection(target), name, limit=limit)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "search_ad_users")}
