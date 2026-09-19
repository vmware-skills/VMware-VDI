# ruff: noqa: F811 — pytest fixtures are imported by name and used as parameters
"""Blast-radius reads must not stop at page 1 or read an absent field as "nobody".

Review findings on the VDI confirmation gates (HLD §7):

* ``_read_entitled`` made one GET with no ``page``/``size``. On a list-shaped
  answer that was page 1 treated as the whole list: a SID entitled on page 2
  read as *not entitled*, so ``entitlement_remove``'s preview said the revoke
  took access from no one. A full first page was, meanwhile, refused outright.
* ``_pool_blast`` dropped machine rows that carry no desktop-pool id, so a push
  preview could say "recreates 0 desktops" while unplaceable desktops existed.
* A machine row with neither ``user`` nor ``assigned_user`` read as "nobody
  assigned"; it is "not read".
"""

from __future__ import annotations

import pytest

from tests.eval.regression.test_mcp_writes_state_blast_radius import (  # noqa: F401 — fixtures
    FakeHorizon,
    _is_preview,
    _refused,
    fresh_policy,
    horizon,
)
from vmware_vdi.mcp_server.tools.entitlement import entitlement_add, entitlement_remove
from vmware_vdi.mcp_server.tools.machine import machine_remove, machine_reset
from vmware_vdi.mcp_server.tools.pool import pool_push_image

_ENT = "/entitlements/v1/desktop-pools/pool-fin"


def _rows(n: int, *, with_id: bool = True) -> list[dict]:
    return [
        {"ad_user_or_group_id": f"S-1-5-21-{i:05d}", **({"id": f"S-1-5-21-{i:05d}"} if with_id else {})}
        for i in range(n)
    ]


def _paginate(horizon: FakeHorizon, rows: list, *, wrap: bool = False, honour_params: bool = True):
    """Serve the entitlement read the way a paginating Horizon would (default page = first 1000)."""
    plain_get = horizon.get

    def get(path, params=None, *, retries=1):
        if path != _ENT:
            return plain_get(path, params, retries=retries)
        horizon.calls.append(("GET", path, params))
        if honour_params and params:
            page, size = params["page"], params["size"]
            chunk = rows[(page - 1) * size: page * size]
        elif honour_params:
            chunk = rows[:1000]
        else:
            chunk = rows
        return {"results": chunk} if wrap else chunk

    horizon.get = get


# --- entitlements ------------------------------------------------------------


@pytest.mark.parametrize("wrap", [False, True])
def test_a_sid_entitled_on_page_two_is_measured_as_losing_access(horizon, wrap):
    rows = _rows(1500)
    _paginate(horizon, rows, wrap=wrap)
    late = rows[1200]["ad_user_or_group_id"]
    radius = _is_preview(entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=[late, "S-1-5-21-none"],
                                            confirm=False))
    assert radius["losing_access"] == [late] and radius["losing_access_count"] == 1
    assert radius["not_entitled"] == ["S-1-5-21-none"]


def test_a_sid_on_page_two_is_already_entitled_for_add(horizon):
    rows = _rows(1500)
    _paginate(horizon, rows)
    late = rows[1499]["ad_user_or_group_id"]
    radius = _is_preview(entitlement_add(pool_id="pool-fin", ad_user_or_group_ids=[late], confirm=False))
    assert radius["already_entitled"] == [late]
    assert radius["newly_entitled_count"] == 0


def test_a_full_single_page_is_not_unreadable(horizon):
    """A server that ignores page/size and returns 1200 rows at once: that is the whole list."""
    rows = _rows(1200)
    _paginate(horizon, rows, honour_params=False)
    radius = _is_preview(entitlement_remove(pool_id="pool-fin",
                                            ad_user_or_group_ids=[rows[1100]["ad_user_or_group_id"]],
                                            confirm=False))
    assert radius["losing_access_count"] == 1


def test_a_row_without_a_principal_on_page_two_is_unmeasured(horizon):
    rows = [*_rows(1000), {"name": "no principal id"}]
    _paginate(horizon, rows)
    _refused(entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-00001"], confirm=True),
             horizon, "current entitlements")


def test_the_entitlement_info_object_shape_is_still_read(horizon):
    radius = _is_preview(entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-ops"],
                                            confirm=False))
    assert radius["losing_access"] == ["S-1-5-21-ops"]


# --- push image: desktops with no pool id ------------------------------------


def test_a_machine_with_no_pool_id_makes_the_desktop_count_unmeasured(horizon):
    horizon.machines.append({"id": "m-9", "name": "vdi-lost-09", "state": "AVAILABLE", "assigned_user": ""})
    out = pool_push_image(pool_id="pool-fin", confirm=False)
    assert out["action"] == "preview"
    radius = out["blast_radius"]
    assert radius["affected_desktops"] == 2
    assert radius["unattributed_desktops"] == 1
    assert radius["unattributed_desktop_ids"] == ["m-9"]
    assert any("m-9" in u for u in radius["unmeasured"]), radius["unmeasured"]
    assert "at least 2" in out["hint"], out["hint"]


@pytest.mark.parametrize("ack", [False, True])
def test_unplaceable_desktops_refuse_confirm_even_with_the_occupancy_override(horizon, ack):
    horizon.machines.append({"id": "m-9", "name": "vdi-lost-09", "state": "AVAILABLE"})
    out = pool_push_image(pool_id="pool-fin", confirm=True, acknowledge_unknown_occupancy=ack)
    assert "error" in out, out
    assert "m-9" in out["error"] and "Nothing was changed" in out["error"]
    assert not horizon.writes()


def test_a_machine_in_another_pool_is_not_unmeasured(horizon):
    horizon.machines.append({"id": "m-7", "name": "vdi-hr-07", "desktop_pool_id": "pool-hr", "state": "AVAILABLE"})
    radius = _is_preview(pool_push_image(pool_id="pool-fin", confirm=False))
    assert radius["unattributed_desktops"] == 0
    assert radius["affected_desktops"] == 2


# --- machines: assigned user absent is "unread" ------------------------------


def test_a_machine_without_a_user_field_is_listed_as_assignment_unread(horizon):
    del horizon.machines[1]["assigned_user"]
    out = machine_reset(machine_ids=["m-1", "m-2"], confirm=False)
    radius = out["blast_radius"]
    assert radius["assigned_users"] == ["ACME\\alice"]
    assert radius["assignment_unread_count"] == 1
    assert radius["assignment_unread"] == ["m-2"]
    assert "not read" in radius["assignment_note"]


def test_an_empty_user_field_is_read_as_nobody_assigned(horizon):
    radius = _is_preview(machine_remove(machine_ids=["m-1", "m-2"], confirm=False))
    assert radius["assignment_unread_count"] == 0
    assert radius["assignment_unread"] == []
    assert "assignment_note" not in radius
