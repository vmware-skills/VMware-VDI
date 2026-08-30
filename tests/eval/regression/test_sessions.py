"""Regression evals for the session ops vertical.

Pins: (1) every runtime path is in the verified endpoint spec (踩坑 #36); (2) the
list projection field names; (3) user-lookup refusal on no match; (4) logoff/disconnect
preview-vs-confirm and blast radius; (5) a bad id → teaching error via VdiApiError;
(6) send-message body shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spec"))
from horizon_endpoints import ENDPOINTS, normalize  # noqa: E402

from vmware_vdi.connection import VdiApiError  # noqa: E402
from vmware_vdi.ops import sessions as S  # noqa: E402

_ROWS = [
    {
        "id": "s-1", "user_name": "ACME\\alice", "session_type": "DESKTOP",
        "session_state": "CONNECTED", "session_protocol": "BLAST",
        "desktop_id": "pool-fin", "machine_id": "m-1", "start_time": 1,
    },
    {
        "id": "s-2", "user_name": "ACME\\bob", "session_type": "APPLICATION",
        "session_state": "DISCONNECTED", "session_protocol": "PCOIP",
        "desktop_id": "pool-eng", "machine_id": "m-2", "start_time": 2,
    },
]


class FakeClient:
    """Records every (method, path) so tests can assert paths ∈ verified spec."""

    def __init__(self, rows=None, get_error=None):
        self._rows = rows if rows is not None else _ROWS
        self._get_error = get_error
        self.calls: list[tuple[str, str, object]] = []

    def get(self, path, params=None, *, retries=1):
        self.calls.append(("GET", path, None))
        if self._get_error is not None:
            raise self._get_error
        if path == "/inventory/v1/sessions":
            return self._rows
        # /inventory/v1/sessions/{id}
        sid = path.rsplit("/", 1)[-1]
        match = [r for r in self._rows if r["id"] == sid]
        if not match:
            raise VdiApiError("Horizon returned HTTP 404. Verify the id...", status_code=404, path=path)
        return match[0]

    def post(self, path, json_data=None, *, retries=1):
        self.calls.append(("POST", path, json_data))
        return {}


def _assert_paths_in_spec(client: FakeClient) -> None:
    for method, path, _ in client.calls:
        assert (method, normalize(path)) in ENDPOINTS, f"unverified endpoint: {method} {path}"


def test_list_projection_and_filters():
    c = FakeClient()
    out = S.list_sessions(c)
    assert out["total"] == 2 and out["returned"] == 2
    alice = next(r for r in out["items"] if "alice" in r["user"])
    assert alice["state"] == "CONNECTED" and alice["protocol"] == "BLAST" and alice["pool_id"] == "pool-fin"
    # filters
    assert S.list_sessions(c, user="bob")["total"] == 1
    assert S.list_sessions(c, state="connected")["total"] == 1
    assert S.list_sessions(c, pool="pool-eng")["total"] == 1
    _assert_paths_in_spec(c)


def test_get_bad_id_is_teaching_error():
    c = FakeClient()
    with pytest.raises(VdiApiError) as ei:
        S.get_session(c, "s-999")
    assert ei.value.status_code == 404
    _assert_paths_in_spec(c)


def test_logoff_user_no_match_refuses():
    c = FakeClient()
    with pytest.raises(S.SessionError, match="No active sessions"):
        S.logoff_sessions(c, user="nobody", confirm=True)
    # refused before any POST
    assert all(m == "GET" for m, _, _ in c.calls)


def test_logoff_preview_then_confirm_blast_radius():
    c = FakeClient()
    prev = S.logoff_sessions(c, user="alice")  # confirm defaults False
    assert prev["action"] == "preview"
    assert prev["would_affect"]["session_count"] == 1
    assert prev["would_affect"]["affected_users"] == ["ACME\\alice"]
    assert not any(m == "POST" for m, _, _ in c.calls)  # preview never writes

    out = S.logoff_sessions(c, user="alice", confirm=True)
    assert out["action"] == "logoff" and out["affected"]["session_count"] == 1
    post = [(p, body) for m, p, body in c.calls if m == "POST"][0]
    assert post[0] == "/inventory/v1/sessions/action/logoff"
    assert post[1] == ["s-1"]  # body is a bare id array (verified spec)
    _assert_paths_in_spec(c)


def test_disconnect_by_ids_confirm():
    c = FakeClient()
    out = S.disconnect_sessions(c, session_ids=["s-1", "s-2"], confirm=True)
    assert out["affected"]["session_count"] == 2
    post = [(p, body) for m, p, body in c.calls if m == "POST"][0]
    assert post[0] == "/inventory/v1/sessions/action/disconnect" and post[1] == ["s-1", "s-2"]
    _assert_paths_in_spec(c)


def test_disconnect_bad_id_refuses():
    c = FakeClient()
    with pytest.raises(S.SessionError, match="not found"):
        S.disconnect_sessions(c, session_ids=["s-1", "s-bad"], confirm=True)
    assert not any(m == "POST" for m, _, _ in c.calls)


def test_send_message_body_and_validation():
    c = FakeClient()
    with pytest.raises(S.SessionError, match="message_type"):
        S.send_message(c, message="hi", user="alice", message_type="LOUD")
    out = S.send_message(c, message="maintenance in 10 min", user="alice", message_type="warning")
    assert out["action"] == "send_message"
    post = [(p, body) for m, p, body in c.calls if m == "POST"][0]
    assert post[0] == "/inventory/v1/sessions/action/send-message"
    assert post[1]["session_ids"] == ["s-1"] and post[1]["message_type"] == "WARNING"
    _assert_paths_in_spec(c)
