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
from vmware_vdi.ops._gate import PREVIEW_HINT, refuse_unless_measured

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


def blast_radius(client: HorizonClient, pool_id: str, task_id: str) -> dict:
    """L1 for task_cancel: the task that would be cancelled, read before anything is sent.

    A wrong id raises the connection layer's teaching 404 here, on the preview,
    instead of surfacing only when the cancel POST fails. ``type`` and ``state``
    are what tell the operator which long operation stops mid-way; a task whose
    state did not read might be one that already finished or one half-way through
    recreating a pool, and those are not the same decision.
    """
    task = _summary(client.get(f"{_BASE}/{pool_id}/tasks/{task_id}"))
    unmeasured = [label for label, value in (("task type", task["type"]), ("task state", task["state"]))
                  if not value]
    return {
        "pool_id": pool_id,
        "task_id": task_id,
        "task_type": task["type"],
        "state": task["state"],
        "progress": task["progress"],
        "blockers": [],
        "unmeasured": unmeasured,
    }


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
    radius = blast_radius(client, pool_id, task_id)
    if not confirm:
        return {"action": "preview", "would_cancel": {"pool_id": pool_id, "task_id": task_id},
                "blast_radius": radius,
                "hint": f"{PREVIEW_HINT} Work the task already applied is not rolled back."}
    refuse_unless_measured(
        "task_cancel", f"task '{sanitize(task_id, 100)}' on pool '{sanitize(pool_id, 100)}'", radius,
        "Check it with task_status and retry once its type and state read.",
    )
    client.post(f"{_BASE}/{pool_id}/tasks/{task_id}/action/cancel")
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="task_cancel", resource=f"{pool_id}/{task_id}",
                         parameters={"task_type": radius["task_type"], "state": radius["state"]}, result="ok")
    return {"action": "cancel", "pool_id": pool_id, "task_id": task_id, "blast_radius": radius}
