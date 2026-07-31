"""Pool-scoped long-task operations (image push / provisioning). Verified:
    GET  /rest/inventory/v1/desktop-pools/{id}/tasks            — list tasks for a pool
    GET  /rest/inventory/v1/desktop-pools/{id}/tasks/{taskId}   — one task's status
    POST /rest/inventory/v1/desktop-pools/{id}/tasks/{taskId}/action/cancel

Tasks in Horizon are pool-scoped, so both status and cancel need the pool id + task id.
This is the surface BACKLOG [MCP-1] (native MCP tasks/* primitive) will build on.
"""

from __future__ import annotations

from typing import Any

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._fetch import fetch_all

_BASE = "/inventory/v1/desktop-pools"


def _summary(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "type": t.get("type") or t.get("task_type"),
        "state": t.get("state") or t.get("status"),
        "progress": t.get("percent_complete") if t.get("percent_complete") is not None else t.get("progress"),
        "started": t.get("start_time"),
        "message": sanitize(str(t.get("message") or ""), 300),
    }


def task_status(client: HorizonClient, pool_id: str, task_id: str | None = None) -> dict:
    """One task's status (task_id given) or all tasks for a pool. Teaching 404 on a wrong id."""
    if task_id:
        return _summary(client.get(f"{_BASE}/{pool_id}/tasks/{task_id}"))
    tasks = fetch_all(client, f"{_BASE}/{pool_id}/tasks")
    return {"pool_id": pool_id, "tasks": [_summary(t) for t in tasks]}


def task_cancel(
    client: HorizonClient,
    *,
    pool_id: str,
    task_id: str,
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Cancel a running pool task (e.g. an in-progress image push). Preview unless confirm=True."""
    if not confirm:
        return {"action": "preview", "would_cancel": {"pool_id": pool_id, "task_id": task_id},
                "hint": "Re-run with confirm=True to cancel. Work already applied is not rolled back."}
    client.post(f"{_BASE}/{pool_id}/tasks/{task_id}/action/cancel")
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="task_cancel", resource=f"{pool_id}/{task_id}",
                         parameters={}, result="ok")
    return {"action": "cancel", "pool_id": pool_id, "task_id": task_id}
