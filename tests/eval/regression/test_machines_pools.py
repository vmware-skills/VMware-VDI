"""Regression evals for the machines + pools verticals.

Pins runtime paths ∈ verified spec (踩坑 #36), projections, preview-vs-confirm, blast
radius, bad-id refusal, idempotent pool noop, and the normative pool_push_image
blast-radius preview (affected desktops + in-session users) from security HLD §15.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spec"))
from horizon_endpoints import ENDPOINTS, normalize  # noqa: E402

from vmware_vdi.connection import VdiApiError  # noqa: E402
from vmware_vdi.ops import machines as M  # noqa: E402
from vmware_vdi.ops import pools as P  # noqa: E402

_MACHINES = [
    {"id": "m-1", "name": "vdi-fin-01", "desktop_pool_id": "pool-fin", "state": "CONNECTED", "assigned_user": "ACME\\alice"},
    {"id": "m-2", "name": "vdi-fin-02", "desktop_pool_id": "pool-fin", "state": "AGENT_UNREACHABLE", "assigned_user": ""},
    {"id": "m-3", "name": "vdi-eng-01", "desktop_pool_id": "pool-eng", "state": "AVAILABLE", "assigned_user": ""},
]
_POOLS = [
    {"id": "pool-fin", "name": "Finance", "type": "AUTOMATED", "enabled": True, "user_assignment": "FLOATING"},
    {"id": "pool-eng", "name": "Engineering", "type": "AUTOMATED", "enabled": False, "user_assignment": "DEDICATED"},
]
_SESSIONS = [
    {"id": "s-1", "user_name": "ACME\\alice", "desktop_id": "pool-fin"},
]


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []

    def get(self, path, params=None, *, retries=1):
        self.calls.append(("GET", path, None))
        if path == "/inventory/v1/machines":
            return _MACHINES
        if path == "/inventory/v1/desktop-pools":
            return _POOLS
        if path == "/inventory/v1/sessions":
            return _SESSIONS
        if path.startswith("/inventory/v1/machines/"):
            mid = path.rsplit("/", 1)[-1]
            m = [x for x in _MACHINES if x["id"] == mid]
            if not m:
                raise VdiApiError("HTTP 404", status_code=404, path=path)
            return m[0]
        if path.startswith("/inventory/v1/desktop-pools/"):
            pid = path.rsplit("/", 1)[-1]
            p = [x for x in _POOLS if x["id"] == pid]
            if not p:
                raise VdiApiError("HTTP 404", status_code=404, path=path)
            return p[0]
        raise VdiApiError("HTTP 404", status_code=404, path=path)

    def post(self, path, json_data=None, *, retries=1):
        self.calls.append(("POST", path, json_data))
        return {}

    def delete(self, path, json_data=None, *, retries=1):
        self.calls.append(("DELETE", path, json_data))
        return {}


def _assert_spec(c):
    for method, path, _ in c.calls:
        assert (method, normalize(path)) in ENDPOINTS, f"unverified endpoint: {method} {path}"


# --- machines ----------------------------------------------------------------

def test_machine_list_projection_and_filters():
    c = FakeClient()
    out = M.list_machines(c)
    assert out["total"] == 3
    assert M.list_machines(c, pool="pool-fin")["total"] == 2
    assert M.list_machines(c, state="agent_unreachable")["total"] == 1
    _assert_spec(c)


def test_machine_reset_preview_then_confirm_paths():
    c = FakeClient()
    prev = M.reset_machines(c, machine_ids=["m-1"])
    assert prev["action"] == "preview" and prev["would_affect"]["machine_count"] == 1
    assert prev["would_affect"]["assigned_users"] == ["ACME\\alice"]
    assert not any(m == "POST" for m, _, _ in c.calls)
    out = M.reset_machines(c, machine_ids=["m-1"], confirm=True)
    assert out["action"] == "reset"
    post = [(p, b) for m, p, b in c.calls if m == "POST"][0]
    assert post == ("/inventory/v1/machines/action/reset", ["m-1"])
    _assert_spec(c)


def test_machine_maintenance_enter_and_exit():
    c = FakeClient()
    M.set_maintenance(c, machine_ids=["m-2"], enabled=True, confirm=True)
    M.set_maintenance(c, machine_ids=["m-2"], enabled=False, confirm=True)
    verbs = [p for m, p, _ in c.calls if m == "POST"]
    assert verbs == ["/inventory/v1/machines/action/enter-maintenance",
                     "/inventory/v1/machines/action/exit-maintenance"]
    _assert_spec(c)


def test_machine_remove_deletes_each_and_bad_id_refuses():
    c = FakeClient()
    with pytest.raises(M.MachineError, match="not found"):
        M.remove_machines(c, machine_ids=["m-1", "m-bad"], confirm=True)
    assert not any(m == "DELETE" for m, _, _ in c.calls)
    c2 = FakeClient()
    M.remove_machines(c2, machine_ids=["m-1"], confirm=True)
    assert ("DELETE", "/inventory/v1/machines/m-1", None) in c2.calls
    _assert_spec(c2)


# --- pools -------------------------------------------------------------------

def test_pool_list_and_set_enabled_idempotent_noop():
    c = FakeClient()
    assert P.list_pools(c)["total"] == 2
    noop = P.set_pool_enabled(c, pool_id="pool-fin", enabled=True, confirm=True)  # already enabled
    assert noop["action"] == "noop"
    assert not any(m == "POST" for m, _, _ in c.calls)
    out = P.set_pool_enabled(c, pool_id="pool-fin", enabled=False, confirm=True)
    assert out["action"] == "set"
    assert ("POST", "/inventory/v1/desktop-pools/action/disable", ["pool-fin"]) in c.calls
    _assert_spec(c)


def test_pool_set_enabled_bad_id_refuses():
    c = FakeClient()
    with pytest.raises(P.PoolError, match="not found"):
        P.set_pool_enabled(c, pool_id="pool-x", enabled=True, confirm=True)


def test_pool_push_image_blast_radius_preview_then_confirm():
    c = FakeClient()
    prev = P.push_image(c, pool_id="pool-fin")  # confirm defaults False
    assert prev["action"] == "preview"
    # pool-fin has 2 machines and 1 in-session user (alice)
    assert prev["blast_radius"]["affected_desktops"] == 2
    assert prev["blast_radius"]["in_session_users"] == 1
    assert not any(m == "POST" for m, _, _ in c.calls)  # preview never writes

    out = P.push_image(c, pool_id="pool-fin", confirm=True)
    assert out["action"] == "apply-image"
    post = [(p, b) for m, p, b in c.calls if m == "POST"][0]
    assert post[0] == "/inventory/v1/desktop-pools/pool-fin/action/apply-image"
    assert post[1]["logoff_policy"] == "WAIT_FOR_LOGOFF"
    _assert_spec(c)


def test_pool_push_image_bad_logoff_policy_refuses():
    c = FakeClient()
    with pytest.raises(P.PoolError, match="logoff_policy"):
        P.push_image(c, pool_id="pool-fin", logoff_policy="MAYBE", confirm=True)
