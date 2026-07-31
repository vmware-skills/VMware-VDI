"""Pool-task MCP tools (1 read / 1 write). Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _audit, _get_connection, _safe_error, _target_name, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def task_status(pool_id: str, task_id: Optional[str] = None, target: Optional[str] = None) -> dict:
    """[READ] Status of a pool's long task (image push / provisioning), or all tasks for the pool.

    Horizon tasks are pool-scoped. Give task_id (from pool_push_image or a prior task_status) for one
    task; omit it to list all tasks for the pool.

    Args:
        pool_id: The desktop-pool id.
        task_id: A specific task id; omit to list all tasks for the pool.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.tasks import task_status as _s

        return _s(_get_connection(target), pool_id, task_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "task_status")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def task_cancel(
    pool_id: str,
    task_id: str,
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Cancel a running pool task (e.g. an in-progress image push).

    confirm=False previews; confirm=True cancels. Work already applied is not rolled back. Audited.

    Args:
        pool_id: The desktop-pool id.
        task_id: The task id (from task_status).
        confirm: False previews; True cancels.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.tasks import task_cancel as _c

        return _c(_get_connection(target), pool_id=pool_id, task_id=task_id,
                  confirm=confirm, audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "task_cancel")}
