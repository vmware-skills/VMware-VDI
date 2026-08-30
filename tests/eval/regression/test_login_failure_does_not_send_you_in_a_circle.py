"""A 404 on login must not be diagnosed as a bad object id.

Real-hardware finding, 2026-08-30. Authentication failed with HTTP 404 and the
remedy offered was "Verify the id — list the parent collection first (e.g. the
pool_list / session_list / machine_list tools) and copy an exact id."

A login has no id. And `pool_list` is the call that just failed — it logs in
first. Following the advice reproduces the error, one API call per lap.

The cause is a fall-through: `_login` hands every status to `_hint_for_status`,
which is written for *resource* calls where 404 really does mean "wrong id". On
POST /rest/login the same status means nothing answers at that path, which is a
host, port or Connection Server version question (the /rest API is Horizon 8;
Horizon 7 has no such endpoint).

The identical defect was found and fixed in vmware-log-insight the same day.
Both are REST wrappers with a status→hint table, and both let the login path
fall into it — the family's most-repeated shape (CLAUDE.md 形态 #7).
"""

from __future__ import annotations

import httpx
import pytest

from vmware_vdi import connection as conn


def _client_returning(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={})

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://cs.example:443/rest",
    )


def _client(monkeypatch, status: int):
    target = type(
        "T", (), {"host": "cs.example", "port": 443, "domain": "CORP"}
    )()
    c = object.__new__(conn.HorizonClient)
    c._target = target
    c._username = "admin"
    c._password = "secret"
    c._base_url = "https://cs.example:443/rest"
    c._client = _client_returning(status)
    c._access_token = None
    c._refresh_token = None
    # No sleeping in tests: 5xx would otherwise burn the retry delay.
    monkeypatch.setattr(conn.time, "sleep", lambda _s: None)
    return c


@pytest.mark.unit
def test_a_404_on_login_is_not_blamed_on_an_object_id(monkeypatch):
    c = _client(monkeypatch, 404)

    with pytest.raises(conn.VdiApiError) as exc:
        c._login()

    message = str(exc.value)
    assert "copy an exact id" not in message, (
        "a login has no id; this is the generic resource-404 hint reaching a "
        "path it was never written for"
    )
    assert "pool_list" not in message, (
        "pool_list logs in first — it is the call that just failed"
    )
    assert "cs.example" in message


@pytest.mark.unit
def test_the_404_message_names_what_is_actually_wrong(monkeypatch):
    c = _client(monkeypatch, 404)

    with pytest.raises(conn.VdiApiError) as exc:
        c._login()

    message = str(exc.value)
    assert "/rest" in message
    assert "443" in message
    # Horizon 7 has no /rest API at all, which is the most common real cause.
    assert "8" in message


@pytest.mark.unit
@pytest.mark.parametrize("status", [400, 401, 403])
def test_credential_failures_keep_their_own_message(status, monkeypatch):
    """The control. These already said the right thing, and sweeping them into
    a 'check your host' answer would send the user to inspect networking that
    is fine."""
    c = _client(monkeypatch, status)

    with pytest.raises(conn.VdiApiError) as exc:
        c._login()

    message = str(exc.value).lower()
    assert "password" in message or "parameters" in message


@pytest.mark.unit
def test_a_resource_404_still_gets_the_id_hint():
    """The other control: the generic hint is right where it was written to be
    used, and deleting it would cost a real diagnosis on real calls."""
    assert "copy an exact id" in conn._hint_for_status(404)


@pytest.mark.unit
def test_a_405_on_login_is_treated_like_a_404(monkeypatch):
    """A proxy that forwards the path but not the method answers 405, and the
    id hint is no better there."""
    c = _client(monkeypatch, 405)

    with pytest.raises(conn.VdiApiError) as exc:
        c._login()

    message = str(exc.value)
    assert "copy an exact id" not in message
    # Absence alone would also be satisfied by the generic fallback, so the
    # diagnosis itself is asserted (形态 #4).
    assert "/rest" in message and "443" in message


@pytest.mark.unit
@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409])
def test_the_remedy_survives_the_mcp_layers_truncation(status, monkeypatch):
    """The MCP layer renders exceptions through sanitize(str(exc), 300). A
    message longer than that loses its own closing remedy, leaving the agent
    with a diagnosis and no next step — which is how a long, careful error
    message ends up worse than a short one."""
    from vmware_policy import sanitize

    c = _client(monkeypatch, status)
    with pytest.raises(conn.VdiApiError) as exc:
        c._login()

    raw = str(exc.value)
    assert sanitize(raw, 300) == raw, (
        f"the message is {len(raw)} chars; the tail is cut before the agent "
        f"sees it: {raw[300:]!r}"
    )
