"""Regression evals for monitor / statistics / events / farms / entitlements.

Pins runtime paths ∈ verified spec (踩坑 #36) and the aggregation math for
health_summary / session_stats / pool_utilization, plus event/farm/entitlement projection.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spec"))
from horizon_endpoints import ENDPOINTS, normalize  # noqa: E402

from vmware_vdi.ops import entitlements as E  # noqa: E402
from vmware_vdi.ops import farms as F  # noqa: E402
from vmware_vdi.ops import monitor as MON  # noqa: E402

_MACHINES = [
    {"id": "m-1", "desktop_pool_id": "pool-fin", "state": "CONNECTED"},
    {"id": "m-2", "desktop_pool_id": "pool-fin", "state": "AVAILABLE"},
    {"id": "m-3", "desktop_pool_id": "pool-fin", "state": "AGENT_UNREACHABLE"},
    {"id": "m-4", "desktop_pool_id": "pool-eng", "state": "AVAILABLE"},
]
_SESSIONS = [
    {"id": "s-1", "session_state": "CONNECTED", "session_protocol": "BLAST", "desktop_id": "pool-fin", "user_name": "a"},
    {"id": "s-2", "session_state": "DISCONNECTED", "session_protocol": "PCOIP", "desktop_id": "pool-fin", "user_name": "b"},
]
_POOLS = [{"id": "pool-fin", "name": "Finance", "enabled": True}, {"id": "pool-eng", "name": "Eng", "enabled": False}]
_EVENTS = [
    {"time": 2, "severity": "ERROR", "message": "agent down", "user_display_name": "a"},
    {"time": 1, "severity": "INFO", "message": "login", "user_display_name": "b"},
]
_FARMS = [{"id": "farm-1", "name": "RDS-A", "type": "AUTOMATED", "enabled": True, "rds_server_ids": ["r1", "r2"]}]
_ENTS = [{"ad_user_or_group_id": "g-1", "name": "Domain Users", "group": True}]


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None, *, retries=1):
        self.calls.append(("GET", path))
        return {
            "/inventory/v1/machines": _MACHINES,
            "/inventory/v1/sessions": _SESSIONS,
            "/inventory/v1/desktop-pools": _POOLS,
            "/external/v1/audit-events": _EVENTS,
            "/inventory/v1/farms": _FARMS,
            "/entitlements/v1/desktop-pools/pool-fin": _ENTS,
        }.get(path, [])


def _assert_spec(c):
    for method, path in c.calls:
        assert (method, normalize(path)) in ENDPOINTS, f"unverified endpoint: {method} {path}"


def test_health_summary_aggregation():
    c = FakeClient()
    h = MON.health_summary(c)
    assert h["sessions"]["total"] == 2
    assert h["machines"]["problem"] == 1 and h["machines"]["problem_by_state"] == {"AGENT_UNREACHABLE": 1}
    assert h["pools"] == {"total": 2, "enabled": 1, "disabled": 1}
    _assert_spec(c)


def test_session_stats():
    c = FakeClient()
    s = MON.session_stats(c)
    assert s["current_concurrent"] == 1 and s["total_sessions"] == 2
    assert s["by_protocol"] == {"BLAST": 1, "PCOIP": 1}
    assert s["top_pools"][0] == {"pool_id": "pool-fin", "sessions": 2}
    _assert_spec(c)


def test_pool_utilization_math():
    c = FakeClient()
    u = {p["pool_id"]: p for p in MON.pool_utilization(c)["pools"]}
    fin = u["pool-fin"]  # 3 machines: 1 CONNECTED(in_use), 1 AVAILABLE, 1 AGENT_UNREACHABLE(error)
    assert fin["total"] == 3 and fin["in_use"] == 1 and fin["available"] == 1 and fin["error"] == 1
    assert fin["utilization_pct"] == round(100 / 3, 1)
    _assert_spec(c)


def test_event_list_sorted_and_filtered():
    c = FakeClient()
    out = MON.list_events(c)
    assert out["total"] == 2 and out["items"][0]["severity"] == "ERROR"  # newest first
    only_err = MON.list_events(c, severity="error")
    assert only_err["total"] == 1
    _assert_spec(c)


def test_farm_and_entitlement_projection():
    c = FakeClient()
    farms = F.list_farms(c)
    assert farms["items"][0]["rds_server_count"] == 2
    ents = E.list_entitlements(c, "pool-fin")
    assert ents["items"][0]["type"] == "GROUP" and ents["items"][0]["principal"] == "Domain Users"
    _assert_spec(c)
