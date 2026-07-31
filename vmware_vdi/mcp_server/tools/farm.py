"""Farm read MCP tool. Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _get_connection, _safe_error, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def farm_list(limit: int = 50, offset: int = 0, target: Optional[str] = None) -> dict:
    """[READ] List Horizon RDS farms: id, name, type, enabled, RDS server count. Paginated.

    Args:
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.farms import list_farms

        return list_farms(_get_connection(target), limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "farm_list")}
