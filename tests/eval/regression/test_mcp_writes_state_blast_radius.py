"""Every destructive VDI write states its blast radius and refuses to act blind (HLD §7).

The ten gated tools already previewed on a bare call (L2). What they did not do:

* L1 — carry one ``blast_radius`` dict on the preview *and* on the acting response.
  Each tool used its own key (``would_affect``, ``would_cancel``, ``would_set``,
  ``would_entitle``); ``task_cancel`` measured nothing at all, and
  ``entitlement_add`` / ``entitlement_remove`` echoed the caller's input back as
  if it were a measurement. The old keys stay for one minor release.
* L3 — refuse ``confirm=True`` when something the blast radius depends on could
  not be read. Before this, a machine whose state was missing, a session that
  named nobody, or a pool whose enabled flag was absent was acted on exactly like
  one that had been read — the unread value simply vanished from the preview.
* Wording — ``confirm: False previews; True resets.`` reads as an invitation, and
  the hints said "Re-run with confirm=True to …". The preview now tells the agent
  to show the blast radius and wait for the user.

Tests call the MCP tool functions, through ``@vmware_tool``, against a recording
fake Horizon client: what a model calling the tool actually receives.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest
from vmware_policy import get_engine
from vmware_policy.budget import reset_budget
from vmware_policy.policy import reset_policy_engine
from vmware_policy.undo import reset_undo_store

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spec"))
from horizon_endpoints import ENDPOINTS, normalize

import vmware_vdi.mcp_server.tools.entitlement as ent_tools
import vmware_vdi.mcp_server.tools.machine as machine_tools
import vmware_vdi.mcp_server.tools.pool as pool_tools
import vmware_vdi.mcp_server.tools.session as session_tools
import vmware_vdi.mcp_server.tools.task as task_tools
from vmware_vdi.connection import VdiApiError
from vmware_vdi.mcp_server.server import mcp
from vmware_vdi.mcp_server.tools.entitlement import entitlement_add, entitlement_remove
from vmware_vdi.mcp_server.tools.machine import machine_maintenance, machine_remove, machine_reset
from vmware_vdi.mcp_server.tools.pool import pool_push_image, pool_set_enabled
from vmware_vdi.mcp_server.tools.session import session_disconnect, session_logoff
from vmware_vdi.mcp_server.tools.task import task_cancel

GATED = (
    "machine_reset", "machine_remove", "machine_maintenance", "session_logoff",
    "session_disconnect", "task_cancel", "pool_set_enabled", "pool_push_image",
    "entitlement_add", "entitlement_remove",
)

_TOOL_MODULES = (ent_tools, machine_tools, pool_tools, session_tools, task_tools)


def _machines():
    return [
        {"id": "m-1", "name": "vdi-fin-01", "desktop_pool_id": "pool-fin", "state": "CONNECTED",
         "assigned_user": "ACME\\alice"},
        {"id": "m-2", "name": "vdi-fin-02", "desktop_pool_id": "pool-fin", "state": "AVAILABLE",
         "assigned_user": ""},
    ]


def _sessions():
    return [
        {"id": "s-1", "user_id": "S-1-5-21-alice", "desktop_pool_id": "pool-fin", "session_state": "CONNECTED"},
        {"id": "s-2", "user_id": "S-1-5-21-bob", "desktop_pool_id": "pool-fin", "session_state": "DISCONNECTED"},
    ]


class FakeHorizon:
    """Serves the reads each gate measures from; records every call."""

    def __init__(self):
        self.machines = _machines()
        self.sessions = _sessions()
        self.pools = [{"id": "pool-fin", "name": "Finance", "type": "AUTOMATED", "enabled": True}]
        self.tasks = {"t-1": {"id": "t-1", "type": "PUSH_IMAGE", "state": "RUNNING", "percent_complete": 40}}
        self.entitlements = {"id": "pool-fin", "ad_user_or_group_ids": ["S-1-5-21-fin", "S-1-5-21-ops"]}
        self.calls: list[tuple[str, str, object]] = []

    def _one(self, rows, path):
        rid = path.rsplit("/", 1)[-1]
        found = [r for r in rows if r["id"] == rid]
        if not found:
            raise VdiApiError("HTTP 404", status_code=404, path=path)
        return found[0]

    def get(self, path, params=None, *, retries=1):
        self.calls.append(("GET", path, None))
        if path == "/inventory/v1/machines":
            return self.machines
        if path == "/inventory/v1/sessions":
            return self.sessions
        if path.startswith("/inventory/v1/machines/"):
            return self._one(self.machines, path)
        if path.startswith("/inventory/v1/sessions/"):
            return self._one(self.sessions, path)
        if path.startswith("/inventory/v1/desktop-pools/pool-fin/tasks/"):
            task = self.tasks.get(path.rsplit("/", 1)[-1])
            if task is None:
                raise VdiApiError("HTTP 404", status_code=404, path=path)
            return task
        if path.startswith("/inventory/v1/desktop-pools/"):
            return self._one(self.pools, path)
        if path == "/entitlements/v1/desktop-pools/pool-fin":
            return self.entitlements
        raise VdiApiError("HTTP 404", status_code=404, path=path)

    def post(self, path, json_data=None, *, retries=1):
        self.calls.append(("POST", path, json_data))
        return {}

    def delete(self, path, json_data=None, *, retries=1):
        self.calls.append(("DELETE", path, json_data))
        return {}

    def writes(self):
        return [(m, p, b) for m, p, b in self.calls if m in ("POST", "DELETE")]


@pytest.fixture(autouse=True)
def fresh_policy():
    reset_policy_engine()
    reset_budget()
    reset_undo_store()
    yield
    reset_policy_engine()
    reset_budget()
    reset_undo_store()


@pytest.fixture
def horizon(monkeypatch):
    fake = FakeHorizon()
    for module in _TOOL_MODULES:
        monkeypatch.setattr(module, "_get_connection", lambda target, _f=fake: _f)
    yield fake
    for method, path, _ in fake.calls:
        assert (method, normalize(path)) in ENDPOINTS, f"unverified endpoint: {method} {path}"


def _is_preview(out: dict) -> dict:
    assert "error" not in out, out
    assert out["action"] == "preview", out
    radius = out["blast_radius"]
    assert radius["blockers"] == [] and radius["unmeasured"] == []
    assert "only after they agree" in out["hint"], out["hint"]
    assert "Re-run with confirm=True to" not in out["hint"]
    return radius


def _refused(out: dict, horizon: FakeHorizon, *words: str) -> None:
    assert "error" in out, f"confirm=True acted on an unmeasured blast radius: {out}"
    assert "Nothing was changed" in out["error"]
    for word in words:
        assert word in out["error"], out["error"]
    assert not horizon.writes(), "a refused call reached the Connection Server"


# --- schema and wording ------------------------------------------------------


def _tools():
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


@pytest.mark.parametrize("name", GATED)
def test_schema_defaults_confirm_to_false(name):
    prop = _tools()[name].inputSchema["properties"]["confirm"]
    assert prop.get("default") is False


@pytest.mark.parametrize("name", GATED)
def test_description_states_the_consequence_not_an_invitation(name):
    tool = _tools()[name]
    # The Args entry becomes the schema's parameter description; the body stays the tool's.
    param = tool.inputSchema["properties"]["confirm"]["description"]
    assert param.startswith("False (default) returns the blast radius and changes nothing. True "), param
    assert "previews;" not in param
    assert "have not seen" in tool.description, "the description must tell the model not to confirm on its own"
    assert "re-run with confirm=True to" not in tool.description.lower()


# --- machines ----------------------------------------------------------------


def test_machine_reset_preview_measures_and_changes_nothing(horizon):
    out = machine_reset(machine_ids=["m-1", "m-2"], confirm=False)
    radius = _is_preview(out)
    assert radius["operation"] == "reset"
    assert radius["machine_count"] == 2
    assert radius["machine_ids"] == ["m-1", "m-2"]
    assert radius["assigned_users"] == ["ACME\\alice"]
    assert [m["state"] for m in radius["machines"]] == ["CONNECTED", "AVAILABLE"]
    assert out["would_affect"]["machine_count"] == 2, "the legacy key stays for one minor release"
    assert not horizon.writes()


def test_machine_reset_confirm_acts_once_and_states_the_blast_radius(horizon):
    out = machine_reset(machine_ids=["m-1"], confirm=True)
    assert out["action"] == "reset"
    assert out["blast_radius"]["machine_ids"] == ["m-1"]
    assert horizon.writes() == [("POST", "/inventory/v1/machines/action/reset", ["m-1"])]


def test_machine_reset_unreadable_state_is_refused(horizon):
    del horizon.machines[0]["state"]
    preview = machine_reset(machine_ids=["m-1"], confirm=False)
    assert preview["blast_radius"]["unmeasured"] == ["state of machine m-1"]
    _refused(machine_reset(machine_ids=["m-1"], confirm=True), horizon, "state of machine m-1", "machine_get")


def test_machine_remove_preview_measures_and_changes_nothing(horizon):
    radius = _is_preview(machine_remove(machine_ids=["m-2"], confirm=False))
    assert radius["operation"] == "remove"
    assert radius["machine_count"] == 1 and radius["machine_ids"] == ["m-2"]
    assert radius["machines"][0]["name"] == "vdi-fin-02"
    assert not horizon.writes()


def test_machine_remove_confirm_deletes_each_and_states_the_blast_radius(horizon):
    out = machine_remove(machine_ids=["m-1", "m-2"], confirm=True)
    assert out["removed"] == ["m-1", "m-2"]
    assert out["blast_radius"]["machine_count"] == 2
    assert horizon.writes() == [("DELETE", "/inventory/v1/machines/m-1", None),
                                ("DELETE", "/inventory/v1/machines/m-2", None)]


def test_machine_remove_unreadable_state_is_refused(horizon):
    horizon.machines[1]["state"] = None
    _refused(machine_remove(machine_ids=["m-1", "m-2"], confirm=True), horizon, "state of machine m-2")


def test_machine_maintenance_preview_measures_and_changes_nothing(horizon):
    radius = _is_preview(machine_maintenance(machine_ids=["m-1"], enabled=True, confirm=False))
    assert radius["operation"] == "enter-maintenance"
    assert radius["machine_ids"] == ["m-1"] and radius["assigned_users"] == ["ACME\\alice"]
    assert not horizon.writes()


def test_machine_maintenance_confirm_acts_and_states_the_blast_radius(horizon):
    out = machine_maintenance(machine_ids=["m-2"], enabled=False, confirm=True)
    assert out["blast_radius"]["operation"] == "exit-maintenance"
    assert horizon.writes() == [("POST", "/inventory/v1/machines/action/exit-maintenance", ["m-2"])]


def test_machine_maintenance_unreadable_state_is_refused(horizon):
    del horizon.machines[0]["state"]
    _refused(machine_maintenance(machine_ids=["m-1"], enabled=True, confirm=True), horizon, "state")


# --- sessions ----------------------------------------------------------------


def test_session_logoff_preview_measures_and_changes_nothing(horizon):
    radius = _is_preview(session_logoff(session_ids=["s-1", "s-2"], confirm=False))
    assert radius["operation"] == "logoff"
    assert radius["session_count"] == 2
    assert radius["session_ids"] == ["s-1", "s-2"]
    assert radius["affected_users"] == ["S-1-5-21-alice", "S-1-5-21-bob"]
    assert not horizon.writes()


def test_session_logoff_confirm_acts_once_and_states_the_blast_radius(horizon):
    out = session_logoff(user="alice", confirm=True)
    assert out["blast_radius"]["session_ids"] == ["s-1"]
    assert horizon.writes() == [("POST", "/inventory/v1/sessions/action/logoff", ["s-1"])]


def test_session_logoff_a_session_naming_nobody_is_refused(horizon):
    del horizon.sessions[1]["user_id"]
    preview = session_logoff(session_ids=["s-2"], confirm=False)
    assert preview["blast_radius"]["unmeasured"] == ["user of session s-2"]
    _refused(session_logoff(session_ids=["s-2"], confirm=True), horizon, "user of session s-2", "session_get")


def test_session_disconnect_preview_measures_and_changes_nothing(horizon):
    radius = _is_preview(session_disconnect(user="bob", confirm=False))
    assert radius["operation"] == "disconnect"
    assert radius["session_count"] == 1 and radius["affected_users"] == ["S-1-5-21-bob"]
    assert not horizon.writes()


def test_session_disconnect_confirm_acts_once_and_states_the_blast_radius(horizon):
    out = session_disconnect(session_ids=["s-2"], confirm=True)
    assert out["blast_radius"]["session_ids"] == ["s-2"]
    assert horizon.writes() == [("POST", "/inventory/v1/sessions/action/disconnect", ["s-2"])]


def test_session_disconnect_a_session_naming_nobody_is_refused(horizon):
    del horizon.sessions[0]["user_id"]
    _refused(session_disconnect(session_ids=["s-1"], confirm=True), horizon, "user of session s-1")


# --- task_cancel -------------------------------------------------------------


def test_task_cancel_preview_measures_the_task_it_would_cancel(horizon):
    out = task_cancel(pool_id="pool-fin", task_id="t-1", confirm=False)
    radius = _is_preview(out)
    assert radius == {**radius, "pool_id": "pool-fin", "task_id": "t-1", "task_type": "PUSH_IMAGE",
                      "state": "RUNNING", "progress": 40}
    assert out["would_cancel"] == {"pool_id": "pool-fin", "task_id": "t-1"}
    assert not horizon.writes()


def test_task_cancel_confirm_cancels_once_and_states_the_blast_radius(horizon):
    out = task_cancel(pool_id="pool-fin", task_id="t-1", confirm=True)
    assert out["blast_radius"]["task_type"] == "PUSH_IMAGE"
    assert horizon.writes() == [("POST", "/inventory/v1/desktop-pools/pool-fin/tasks/t-1/action/cancel", None)]


def test_task_cancel_a_wrong_task_id_is_a_teaching_error_not_a_cancel(horizon):
    out = task_cancel(pool_id="pool-fin", task_id="t-404", confirm=True)
    assert "error" in out and not horizon.writes()


def test_task_cancel_unreadable_task_state_is_refused(horizon):
    horizon.tasks["t-1"] = {"id": "t-1", "type": "PUSH_IMAGE"}
    _refused(task_cancel(pool_id="pool-fin", task_id="t-1", confirm=True), horizon, "task state", "task_status")


# --- pools -------------------------------------------------------------------


def test_pool_set_enabled_preview_measures_the_pool(horizon):
    out = pool_set_enabled(pool_id="pool-fin", enabled=False, confirm=False)
    radius = _is_preview(out)
    assert radius == {**radius, "pool_id": "pool-fin", "pool_name": "Finance",
                      "current_enabled": True, "new_enabled": False}
    assert out["would_set"]["enabled"] is False
    assert not horizon.writes()


def test_pool_set_enabled_confirm_acts_and_states_the_blast_radius(horizon):
    out = pool_set_enabled(pool_id="pool-fin", enabled=False, confirm=True)
    assert out["blast_radius"]["new_enabled"] is False
    assert horizon.writes() == [("POST", "/inventory/v1/desktop-pools/action/disable", ["pool-fin"])]


def test_pool_set_enabled_unreadable_enabled_flag_is_refused(horizon):
    del horizon.pools[0]["enabled"]
    _refused(pool_set_enabled(pool_id="pool-fin", enabled=False, confirm=True), horizon,
             "current enabled state", "pool_get")


def test_pool_push_image_preview_carries_identity_and_the_reference_shape(horizon):
    out = pool_push_image(pool_id="pool-fin", confirm=False)
    radius = _is_preview(out)
    assert radius["pool_id"] == "pool-fin" and radius["pool_name"] == "Finance"
    assert radius["affected_desktops"] == 2
    assert radius["desktop_ids"] == ["m-1", "m-2"]
    assert radius["in_session_count"] == 2 and radius["in_session_users"] == 2
    assert radius["occupancy"] == "determined"
    assert not horizon.writes()


def test_pool_push_image_confirm_acts_and_states_the_blast_radius(horizon):
    out = pool_push_image(pool_id="pool-fin", confirm=True)
    assert out["blast_radius"]["affected_desktops"] == 2
    assert [p for _, p, _ in horizon.writes()] == ["/inventory/v1/desktop-pools/pool-fin/action/apply-image"]


def test_pool_push_image_unknown_occupancy_is_unmeasured_and_refused(horizon):
    horizon.sessions.append({"id": "s-9", "user_id": "S-1-5-21-carol"})  # no pool, no farm
    preview = pool_push_image(pool_id="pool-fin", confirm=False)
    assert preview["blast_radius"]["unmeasured"] == ["occupancy"]
    out = pool_push_image(pool_id="pool-fin", confirm=True)
    assert "acknowledge_unknown_occupancy" in out["error"]
    assert not horizon.writes()


# --- entitlements ------------------------------------------------------------


def test_entitlement_add_preview_measures_who_gains_access(horizon):
    out = entitlement_add(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-fin", "S-1-5-21-new"],
                          confirm=False)
    radius = _is_preview(out)
    assert radius["pool_name"] == "Finance"
    assert radius["principal_count"] == 2
    assert radius["already_entitled"] == ["S-1-5-21-fin"]
    assert radius["newly_entitled"] == ["S-1-5-21-new"] and radius["newly_entitled_count"] == 1
    assert out["would_entitle"]["pool_id"] == "pool-fin"
    assert not horizon.writes()


def test_entitlement_add_confirm_grants_and_states_the_blast_radius(horizon):
    out = entitlement_add(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-new"], confirm=True)
    assert out["blast_radius"]["newly_entitled"] == ["S-1-5-21-new"]
    assert horizon.writes() == [("POST", "/entitlements/v1/desktop-pools",
                                 [{"id": "pool-fin", "ad_user_or_group_ids": ["S-1-5-21-new"]}])]


def test_entitlement_add_unreadable_entitlements_are_refused(horizon):
    horizon.entitlements = {"unexpected": "shape"}
    _refused(entitlement_add(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-new"], confirm=True),
             horizon, "current entitlements", "entitlement_list")


def test_entitlement_remove_preview_measures_who_loses_access(horizon):
    out = entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-ops", "S-1-5-21-none"],
                             confirm=False)
    radius = _is_preview(out)
    assert radius["losing_access"] == ["S-1-5-21-ops"] and radius["losing_access_count"] == 1
    assert radius["not_entitled"] == ["S-1-5-21-none"]
    assert out["would_unentitle"]["pool_id"] == "pool-fin"
    assert not horizon.writes()


def test_entitlement_remove_confirm_revokes_and_states_the_blast_radius(horizon):
    out = entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-ops"], confirm=True)
    assert out["blast_radius"]["losing_access"] == ["S-1-5-21-ops"]
    assert horizon.writes() == [("DELETE", "/entitlements/v1/desktop-pools",
                                 [{"id": "pool-fin", "ad_user_or_group_ids": ["S-1-5-21-ops"]}])]


def test_entitlement_remove_unreadable_entitlements_are_refused(horizon):
    horizon.entitlements = [{"name": "a row without a principal id"}]
    _refused(entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-ops"], confirm=True),
             horizon, "current entitlements")


def test_entitlements_read_as_a_list_of_rows_are_measured_too(horizon):
    """The other documented shape: one row per principal."""
    horizon.entitlements = [{"ad_user_or_group_id": "S-1-5-21-ops"}]
    radius = _is_preview(entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-ops"],
                                            confirm=False))
    assert radius["losing_access"] == ["S-1-5-21-ops"]


# --- caps and audit ----------------------------------------------------------


def test_identifiers_are_capped_but_counts_are_complete(horizon):
    horizon.sessions = [{"id": f"s-{i}", "user_id": "S-1-5-21-alice", "desktop_pool_id": "pool-fin"}
                        for i in range(30)]
    radius = _is_preview(session_logoff(user="alice", confirm=False))
    assert radius["session_count"] == 30
    assert len(radius["session_ids"]) == 20


def test_a_refusal_is_audited_as_a_failure(horizon):
    del horizon.machines[0]["state"]
    out = machine_reset(machine_ids=["m-1"], confirm=True)
    assert "error" in out
    db = Path(get_engine()._path)
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        status, result = con.execute(
            "SELECT status, result FROM audit_log WHERE tool = 'machine_reset' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert status == "error", f"the refused call was audited as {status!r}"
    assert "state of machine m-1" in result


BARE_CALLS = {
    "machine_reset": lambda: machine_reset(machine_ids=["m-1"]),
    "machine_remove": lambda: machine_remove(machine_ids=["m-1"]),
    "machine_maintenance": lambda: machine_maintenance(machine_ids=["m-1"], enabled=True),
    "session_logoff": lambda: session_logoff(session_ids=["s-1"]),
    "session_disconnect": lambda: session_disconnect(session_ids=["s-1"]),
    "task_cancel": lambda: task_cancel(pool_id="pool-fin", task_id="t-1"),
    "pool_set_enabled": lambda: pool_set_enabled(pool_id="pool-fin", enabled=False),
    "pool_push_image": lambda: pool_push_image(pool_id="pool-fin"),
    "entitlement_add": lambda: entitlement_add(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-new"]),
    "entitlement_remove": lambda: entitlement_remove(pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-ops"]),
}


@pytest.mark.parametrize("name", GATED)
def test_a_bare_call_previews_and_writes_nothing(name, horizon):
    """No ``confirm`` argument at all: the default must be the preview (L2)."""
    _is_preview(BARE_CALLS[name]())
    assert not horizon.writes()
