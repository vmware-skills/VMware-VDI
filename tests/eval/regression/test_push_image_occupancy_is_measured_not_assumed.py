"""The blast-radius guard on pool_push_image must measure occupancy, not assume it.

Real-hardware review finding, 2026-08-30. ``pool_push_image`` recreates every
desktop in a pool — the largest single-call blast radius in this family — and
the only thing standing between an operator and doing that to a pool full of
working people is the ``in_session_users`` number printed in the preview.

That number was structurally always zero. ``_pool_blast`` read one field:

    {sanitize(str(s.get("user_name") or "")) for s in sessions if s.get("user_name")}

and Horizon's documented ``SessionInfo`` has no ``user_name`` field at all. The
response model (developer.broadcom.com, VMware Horizon Server API, "Get Session
Info") carries ``user_id`` — "Unique SID of the user logged into the session" —
alongside ``broker_user_id``; the field this code asked for does not exist in
it. So every pool reported nobody logged in, and the guard waved every push
through. The mock in the existing pool test happened to use ``user_name``, which
is why five green tests never noticed (形态 #3: verified in an environment where
the defect cannot occur).

The count being wrong is the smaller half. The larger half is that a count of
zero was produced by *failing to look*, and read as *looked and found nobody* —
this family's single most repeated defect (形态 #1). Two ways occupancy can be
undeterminable are covered here:

  * a session row carries no field this code recognises as a user identity;
  * a session row carries no desktop-pool id and no farm id, so it cannot be
    attributed to this pool or ruled out of it. The pool's session count is then
    a lower bound, and a lower bound of zero is not a finding of zero.

The controls matter as much as the assertions: a pool that genuinely has nobody
in it must still push with no extra friction, and a session that belongs to an
RDS farm must not be mistaken for an unattributable row — every estate with a
farm would otherwise refuse every desktop-pool push.
"""

from __future__ import annotations

import pytest

from vmware_vdi.connection import VdiApiError
from vmware_vdi.ops import pools as P
from vmware_vdi.ops._fields import user_of

_POOLS = [{"id": "pool-fin", "name": "Finance", "type": "AUTOMATED", "enabled": True}]
_MACHINES = [
    {"id": "m-1", "name": "vdi-fin-01", "desktop_pool_id": "pool-fin"},
    {"id": "m-2", "name": "vdi-fin-02", "desktop_pool_id": "pool-fin"},
]


class FakeClient:
    """Serves the three collections push_image reads, from injected session rows."""

    def __init__(self, sessions: list[dict]):
        self._sessions = sessions
        self.calls: list[tuple[str, str, object]] = []

    def get(self, path, params=None, *, retries=1):
        self.calls.append(("GET", path, None))
        if path == "/inventory/v1/machines":
            return _MACHINES
        if path == "/inventory/v1/sessions":
            return self._sessions
        if path == "/inventory/v1/desktop-pools":
            return _POOLS
        if path.startswith("/inventory/v1/desktop-pools/"):
            pid = path.rsplit("/", 1)[-1]
            found = [p for p in _POOLS if p["id"] == pid]
            if not found:
                raise VdiApiError("HTTP 404", status_code=404, path=path)
            return found[0]
        raise VdiApiError("HTTP 404", status_code=404, path=path)

    def post(self, path, json_data=None, *, retries=1):
        self.calls.append(("POST", path, json_data))
        return {}

    def _posts(self):
        return [(p, b) for m, p, b in self.calls if m == "POST"]


class RecordingAudit:
    def __init__(self):
        self.rows: list[dict] = []

    def log(self, **kw):
        self.rows.append(kw)


# --- the field itself --------------------------------------------------------


def test_the_documented_horizon_session_user_field_is_the_one_we_read():
    """``user_id`` is what a Horizon 8 Connection Server actually sends.

    Asserted on the helper rather than only end-to-end, so the reason this
    changed is recorded next to the field name (踩坑 #36 — an API layer written
    from recollection is how this skill got here).
    """
    assert user_of({"user_id": "S-1-5-21-99-1105"}) == "S-1-5-21-99-1105"


def test_a_row_that_identifies_nobody_returns_empty_not_a_placeholder():
    """The caller has to be able to tell "no identity here" from an identity."""
    assert user_of({"id": "s-1", "session_state": "CONNECTED"}) == ""


# --- the count is real -------------------------------------------------------


def test_a_documented_session_row_is_counted_as_an_occupant():
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-1105", "desktop_pool_id": "pool-fin"}])

    blast = P.push_image(c, pool_id="pool-fin")["blast_radius"]

    assert blast["in_session_count"] == 1
    assert blast["in_session_users"] == 1
    assert blast["occupancy"] == "determined"


def test_the_preview_hint_states_the_occupancy_it_measured():
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-1105", "desktop_pool_id": "pool-fin"}])

    hint = P.push_image(c, pool_id="pool-fin")["hint"]

    assert "2 desktop(s)" in hint
    assert "1" in hint and "0 logged-in" not in hint


# --- unknown is not zero -----------------------------------------------------


def test_an_unattributable_session_makes_occupancy_unknown_not_zero():
    """A row with neither a desktop-pool id nor a farm id could be in this pool."""
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-1105", "session_state": "CONNECTED"}])

    blast = P.push_image(c, pool_id="pool-fin")["blast_radius"]

    assert blast["occupancy"] == "unknown"
    assert blast["in_session_count"] == 0
    assert "lower bound" in blast["occupancy_note"]


def test_the_preview_does_not_read_as_an_all_clear_when_occupancy_is_unknown():
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-1105"}])

    hint = P.push_image(c, pool_id="pool-fin")["hint"]

    assert "could not be determined" in hint
    assert "confirm=True to schedule" not in hint, (
        "an undetermined occupancy must not end in the same 'go ahead' sentence "
        "as a measured one"
    )


def test_confirm_refuses_while_occupancy_is_unknown():
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-1105"}])

    with pytest.raises(P.PoolError) as exc:
        P.push_image(c, pool_id="pool-fin", confirm=True)

    assert "could not be determined" in str(exc.value)
    assert "acknowledge_unknown_occupancy" in str(exc.value), "the refusal must say how to proceed"
    assert not c._posts(), "a refused push must not have reached the Connection Server"


def test_a_session_with_no_identifiable_user_is_still_counted_as_occupancy():
    """An unauthenticated or oddly-shaped row still means somebody is on that desktop."""
    c = FakeClient([{"id": "s-1", "desktop_pool_id": "pool-fin", "session_state": "CONNECTED"}])

    blast = P.push_image(c, pool_id="pool-fin")["blast_radius"]

    assert blast["in_session_count"] == 1, "the session exists even though nobody is named"
    assert blast["in_session_users"] == 0
    assert blast["unidentified_sessions"] == 1


def test_acknowledging_the_unknown_proceeds_and_records_that_it_was_unknown():
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-1105"}])
    audit = RecordingAudit()

    out = P.push_image(
        c,
        pool_id="pool-fin",
        confirm=True,
        acknowledge_unknown_occupancy=True,
        audit_logger=audit,
        target_name="cs1",
    )

    assert out["action"] == "apply-image"
    assert c._posts()[0][0] == "/inventory/v1/desktop-pools/pool-fin/action/apply-image"
    assert audit.rows[0]["parameters"]["occupancy"] == "unknown"
    assert audit.rows[0]["parameters"]["acknowledged_unknown_occupancy"] is True


# --- controls ----------------------------------------------------------------


def test_an_empty_pool_still_pushes_with_no_extra_friction():
    """The control. A pool nobody is using must not acquire a new gate."""
    c = FakeClient([])

    prev = P.push_image(c, pool_id="pool-fin")
    assert prev["blast_radius"]["occupancy"] == "determined"
    assert prev["blast_radius"]["in_session_count"] == 0

    out = P.push_image(c, pool_id="pool-fin", confirm=True)
    assert out["action"] == "apply-image"
    assert c._posts()[0][0] == "/inventory/v1/desktop-pools/pool-fin/action/apply-image"


def test_a_farm_session_is_attributed_to_its_farm_not_left_unattributed():
    """The second control, and the one that decides whether this is usable.

    An RDS session carries ``farm_id`` and no ``desktop_pool_id``. Treating that
    as "cannot attribute" would make every estate that runs a farm refuse every
    desktop-pool push — a guard that fires on every estate is a guard nobody
    keeps.
    """
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-7", "farm_id": "farm-1"}])

    blast = P.push_image(c, pool_id="pool-fin")["blast_radius"]

    assert blast["occupancy"] == "determined"
    assert blast["in_session_count"] == 0


def test_a_session_in_another_desktop_pool_is_not_counted_against_this_one():
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-7", "desktop_pool_id": "pool-eng"}])

    blast = P.push_image(c, pool_id="pool-fin")["blast_radius"]

    assert blast["occupancy"] == "determined"
    assert blast["in_session_count"] == 0


def test_the_acknowledgement_does_not_bypass_the_confirm_gate():
    """Acknowledging an unknown occupancy is not consent to push."""
    c = FakeClient([{"id": "s-1", "user_id": "S-1-5-21-99-7"}])

    out = P.push_image(c, pool_id="pool-fin", acknowledge_unknown_occupancy=True)

    assert out["action"] == "preview"
    assert not c._posts()
