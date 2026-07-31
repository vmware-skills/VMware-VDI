"""Monitoring + statistics MCP tools (4 read). Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _get_connection, _safe_error, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def health_summary(target: Optional[str] = None) -> dict:
    """[READ] One-glance Horizon VDI health: session totals by state, problem machines, pool availability.

    The first thing to call for "how is VDI right now?". Aggregates sessions, machines, and pools into
    a compact status. Drill into problems with machine_list --state or session_list.

    Args:
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.monitor import health_summary as _h

        return _h(_get_connection(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "health_summary")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def session_stats(target: Optional[str] = None) -> dict:
    """[READ] Session statistics: concurrency by state / protocol, current concurrent, busiest pools.

    The reporting counterpart to session_list — aggregate numbers, not per-session rows.

    Args:
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.monitor import session_stats as _s

        return _s(_get_connection(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "session_stats")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def pool_utilization(target: Optional[str] = None) -> dict:
    """[READ] Per-pool capacity: total / available / in-use / error machines and utilization %.

    The "am I running out of desktops?" view, sorted by utilization. Drill in with machine_list --pool.

    Args:
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.monitor import pool_utilization as _u

        return _u(_get_connection(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "pool_utilization")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def event_list(
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    target: Optional[str] = None,
) -> dict:
    """[READ] List Horizon audit events (newest first), optionally filtered by severity. Paginated.

    Each item: time, severity, type, module, user, machine, message. Use for "what went wrong recently".

    Args:
        severity: Filter by severity (e.g. ERROR, WARNING, AUDIT_FAIL).
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.monitor import list_events

        return list_events(_get_connection(target), severity=severity, limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "event_list")}
