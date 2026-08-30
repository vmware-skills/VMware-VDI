"""A login 404 must survive the write paths, not be re-diagnosed as a bad id.

Real-hardware review finding, 2026-08-30, and the second half of a fix that was
only ever applied to the first half.

The earlier round fixed ``HorizonClient._login``: a 404 there means nothing
answers at ``/rest/login`` — wrong host, wrong port, or a Horizon 7 server that
has no ``/rest`` API — and the old message told the operator to "run pool_list
and copy an exact id", which logs in first and so reproduces the error one API
call per lap.

That fix holds on the read path, where ``pool_get`` / ``machine_get`` /
``session_list`` let the exception through untouched. It does not hold on the
write path. Every write op first validates its target ids with a per-id GET
inside a helper shaped like::

    except VdiApiError as exc:
        if exc.status_code != 404:
            raise
        raise PoolError("Pool id '…' not found. Run pool_list for current pool ids.")

A failed login raises ``VdiApiError(status_code=404)`` from inside that GET, so
the helper catches it and replaces the login diagnosis with exactly the sentence
the previous release removed — on all eight write operations. The user-visible
result is worse than before the fix, because the message now sounds specific: it
names an id that is perfectly valid.

This is the family's most repeated shape: one instance of a pattern fixed while
its siblings keep the defect (形态 #7). The three helpers are ``pools._require_pool``,
``machines._resolve`` and ``sessions._resolve_ids``; between them they gate
pool_set_enabled, pool_push_image, machine_reset, machine_set_maintenance,
machine_remove, session_logoff, session_disconnect and session_send_message.

The tests run against a real ``HorizonClient`` over a mock transport rather than
a hand-raised exception, so they exercise the actual login → ops path. The
positive control — a server that authenticates and then genuinely 404s the id —
must keep its "not found, run …_list" message, which is right and is the whole
reason the helpers exist.
"""

from __future__ import annotations

import httpx
import pytest

from vmware_vdi import connection as conn
from vmware_vdi.connection import VdiApiError
from vmware_vdi.ops import machines as M
from vmware_vdi.ops import pools as P
from vmware_vdi.ops import sessions as S


def _client(monkeypatch, handler):
    target = type("T", (), {"host": "cs.example", "port": 443, "domain": "CORP"})()
    c = object.__new__(conn.HorizonClient)
    c._target = target
    c._username = "admin"
    c._password = "secret"
    c._base_url = "https://cs.example:443/rest"
    c._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://cs.example:443/rest",
    )
    c._access_token = None
    c._refresh_token = None
    monkeypatch.setattr(conn.time, "sleep", lambda _s: None)
    return c


def _nothing_answers(monkeypatch):
    """No /rest API at all — every path, login included, returns 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    return _client(monkeypatch, handler)


def _logged_in_but_id_is_wrong(monkeypatch):
    """The control: authentication succeeds, the object really does not exist."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"access_token": "t", "refresh_token": "r"})
        return httpx.Response(404, json={})

    return _client(monkeypatch, handler)


#: Every write op that validates ids before acting, and the list tool its
#: not-found message points at. One entry per operation, so a helper fixed in
#: one module and not the others fails here rather than in production.
WRITES = {
    "pool_set_enabled": (
        lambda c: P.set_pool_enabled(c, pool_id="pool-1", enabled=False, confirm=True),
        "pool_list",
    ),
    "pool_push_image": (
        lambda c: P.push_image(c, pool_id="pool-1", confirm=True),
        "pool_list",
    ),
    "machine_reset": (
        lambda c: M.reset_machines(c, machine_ids=["m-1"], confirm=True),
        "machine_list",
    ),
    "machine_set_maintenance": (
        lambda c: M.set_maintenance(c, machine_ids=["m-1"], enabled=True, confirm=True),
        "machine_list",
    ),
    "machine_remove": (
        lambda c: M.remove_machines(c, machine_ids=["m-1"], confirm=True),
        "machine_list",
    ),
    "session_logoff": (
        lambda c: S.logoff_sessions(c, session_ids=["s-1"], confirm=True),
        "session_list",
    ),
    "session_disconnect": (
        lambda c: S.disconnect_sessions(c, session_ids=["s-1"], confirm=True),
        "session_list",
    ),
    "session_send_message": (
        lambda c: S.send_message(c, session_ids=["s-1"], message="maintenance in 10 min"),
        "session_list",
    ),
}


def test_the_write_surface_this_covers_is_not_empty():
    """Refuse to pass vacuously: an empty table would make every case below green."""
    assert len(WRITES) == 8, "eight write operations validate ids before acting"


@pytest.mark.parametrize("name", sorted(WRITES))
def test_a_login_404_keeps_its_own_diagnosis_on_the_write_path(name, monkeypatch):
    call, list_tool = WRITES[name]
    c = _nothing_answers(monkeypatch)

    with pytest.raises(VdiApiError) as exc:
        call(c)

    message = str(exc.value)
    assert "Nothing answers at" in message, (
        f"{name} replaced the login diagnosis with its own not-found message"
    )
    assert list_tool not in message, (
        f"{name} told the operator to run {list_tool}, which logs in first — it is "
        f"the call that just failed"
    )
    assert "cs.example" in message and "443" in message


@pytest.mark.parametrize("name", sorted(WRITES))
def test_a_genuine_missing_id_still_gets_the_teaching_refusal(name, monkeypatch):
    """The control. These messages are correct where they were written to be used,
    and losing them would cost a real diagnosis on every mistyped id."""
    call, list_tool = WRITES[name]
    c = _logged_in_but_id_is_wrong(monkeypatch)

    with pytest.raises(Exception) as exc:
        call(c)

    message = str(exc.value)
    assert "not found" in message, f"{name} lost its bad-id refusal"
    assert list_tool in message, f"{name} no longer names the tool that lists valid ids"
    assert "Nothing answers at" not in message, (
        f"{name} blamed the connection for what is really a wrong id"
    )
