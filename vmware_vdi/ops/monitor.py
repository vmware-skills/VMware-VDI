"""Monitoring + statistics (read-only) — health, session stats, pool utilization, events.

health_summary / session_stats / pool_utilization AGGREGATE already-verified endpoints
(/inventory/v1/sessions, /machines, /desktop-pools) — no new API surface. Events use the
verified GET /external/v1/audit-events (Horizon 2106+). Field names are defensive (.get()).
"""

from __future__ import annotations

from collections import Counter

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._fields import pool_id_of
from vmware_vdi.ops._paging import envelope as _envelope

_SESSIONS = "/inventory/v1/sessions"
_MACHINES = "/inventory/v1/machines"
_POOLS = "/inventory/v1/desktop-pools"
_EVENTS = "/external/v1/audit-events"

# Machine states that mean "this desktop is not serviceable right now".
_PROBLEM_STATES = {"AGENT_UNREACHABLE", "ERROR", "PROVISIONING_ERROR", "DELETING", "MAINTENANCE"}


def _mstate(m: dict) -> str:
    return (m.get("state") or m.get("machine_state") or "").upper()


def health_summary(client: HorizonClient) -> dict:
    """One-glance VDI health: session totals by state, problem machines, pool availability."""
    sessions = fetch_all(client, _SESSIONS)
    machines = fetch_all(client, _MACHINES)
    pools = fetch_all(client, _POOLS)

    sess_by_state = Counter((s.get("session_state") or s.get("state") or "UNKNOWN").upper() for s in sessions)
    problem = [m for m in machines if _mstate(m) in _PROBLEM_STATES]
    problem_by_state = Counter(_mstate(m) for m in problem)
    pools_enabled = sum(1 for p in pools if p.get("enabled"))

    return {
        "sessions": {"total": len(sessions), "by_state": dict(sess_by_state)},
        "machines": {"total": len(machines), "problem": len(problem), "problem_by_state": dict(problem_by_state)},
        "pools": {"total": len(pools), "enabled": pools_enabled, "disabled": len(pools) - pools_enabled},
        "hint": "healthy" if not problem else f"{len(problem)} machine(s) need attention — see machine_list --state.",
    }


def session_stats(client: HorizonClient) -> dict:
    """统计: concurrency by pool / protocol / state, and the busiest pools."""
    sessions = fetch_all(client, _SESSIONS)
    by_state = Counter((s.get("session_state") or s.get("state") or "UNKNOWN").upper() for s in sessions)
    by_proto = Counter((s.get("session_protocol") or s.get("protocol") or "UNKNOWN").upper() for s in sessions)
    by_pool = Counter(pool_id_of(s) or "UNKNOWN" for s in sessions)
    connected = by_state.get("CONNECTED", 0)
    top = [{"pool_id": p, "sessions": n} for p, n in by_pool.most_common(10)]
    return {
        "total_sessions": len(sessions),
        "current_concurrent": connected,
        "by_state": dict(by_state),
        "by_protocol": dict(by_proto),
        "top_pools": top,
    }


def pool_utilization(client: HorizonClient) -> dict:
    """统计: per-pool machine counts (total/available/in-use/error) and utilization %."""
    machines = fetch_all(client, _MACHINES)
    pools = {p.get("id"): sanitize(str(p.get("name") or ""), 200) for p in fetch_all(client, _POOLS)}
    buckets: dict[str, Counter] = {}
    for m in machines:
        buckets.setdefault(pool_id_of(m) or "UNKNOWN", Counter())[_mstate(m)] += 1

    out = []
    for pid, c in buckets.items():
        total = sum(c.values())
        in_use = c.get("CONNECTED", 0) + c.get("DISCONNECTED", 0)
        available = c.get("AVAILABLE", 0)
        errors = sum(c.get(s, 0) for s in _PROBLEM_STATES)
        out.append({
            "pool_id": pid, "pool_name": pools.get(pid, ""),
            "total": total, "available": available, "in_use": in_use, "error": errors,
            "utilization_pct": round(100 * in_use / total, 1) if total else 0.0,
        })
    out.sort(key=lambda r: r["utilization_pct"], reverse=True)
    return {"pools": out, "pool_count": len(out)}


def _event_summary(e: dict) -> dict:
    return {
        "time": e.get("time") or e.get("timestamp"),
        "severity": e.get("severity"),
        "type": e.get("type") or e.get("event_type"),
        "module": e.get("module"),
        "user": sanitize(str(e.get("user_display_name") or e.get("user") or ""), 200),
        "machine": sanitize(str(e.get("machine_dns_name") or e.get("machine") or ""), 200),
        "message": sanitize(str(e.get("message") or ""), 500),
    }


def list_events(
    client: HorizonClient,
    *,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List Horizon audit events (GET /external/v1/audit-events), newest first. Paginated envelope.

    Severity is filtered client-side: Horizon's ``filter`` query param takes a URL-encoded
    JSON object, so passing a bare string would 400 the whole call — safer to fetch and filter here.
    """
    rows = [_event_summary(e) for e in fetch_all(client, _EVENTS)]
    if severity:
        sev = severity.upper()
        rows = [r for r in rows if (r["severity"] or "").upper() == sev]
    # Timestamps may be epoch ints or ISO strings and some rows lack one — sort on a
    # uniform string key so a mixed/absent ``time`` never raises a TypeError.
    rows.sort(key=lambda r: str(r["time"]) if r["time"] is not None else "", reverse=True)
    return _envelope(rows, limit=limit, offset=offset)
