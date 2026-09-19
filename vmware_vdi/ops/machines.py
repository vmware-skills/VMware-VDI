"""Machine (desktop VM) operations.

Verified Horizon 8 endpoints (developer.broadcom.com operation index):

    GET    /rest/inventory/v1/machines                          — list
    GET    /rest/inventory/v1/machines/{id}                     — get one
    DELETE /rest/inventory/v1/machines/{id}                     — remove one
    POST   /rest/inventory/v1/machines/action/reset             — body: [machine_id, ...]
    POST   /rest/inventory/v1/machines/action/enter-maintenance — body: [machine_id, ...]
    POST   /rest/inventory/v1/machines/action/exit-maintenance  — body: [machine_id, ...]

Note: Horizon's REST API has no graceful *guest* restart for a desktop machine —
a hard ``reset`` is the only power action here. A graceful in-guest reboot is a
vCenter VM operation → route to vmware-aiops. Field names in the GET projection are
defensive (``.get()``) and pinned by the mock-shape regression test.
"""

from __future__ import annotations

from typing import Any

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient, VdiApiError
from vmware_vdi.ops._errors import VdiOpsError
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._fields import pool_id_of
from vmware_vdi.ops._gate import PREVIEW_HINT, capped, refuse_unless_measured
from vmware_vdi.ops._paging import envelope as _envelope

_BASE = "/inventory/v1/machines"

#: Machine-row keys that can name the assigned user. A row with none of them says
#: nothing about assignment — that is "not read", not "nobody assigned".
_USER_FIELDS = ("user", "assigned_user")


class MachineError(VdiOpsError):
    """A machine operation cannot proceed (e.g. an id does not exist)."""


def _summary(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "name": sanitize(str(m.get("name") or m.get("machine_name") or ""), 200),
        "pool_id": pool_id_of(m),
        "state": m.get("state") or m.get("machine_state"),
        "user": sanitize(str(m.get("user") or m.get("assigned_user") or ""), 200),
        "agent_version": m.get("agent_version"),
        "base_image": m.get("base_image_snapshot") or m.get("base_image"),
    }


def list_machines(
    client: HorizonClient,
    *,
    pool: str | None = None,
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List desktop machines, optionally filtered by pool id / state. Paginated envelope."""
    rows = [_summary(m) for m in fetch_all(client, _BASE)]
    if pool:
        rows = [r for r in rows if r["pool_id"] == pool]
    if state:
        st = state.upper()
        rows = [r for r in rows if (r["state"] or "").upper() == st]
    rows.sort(key=lambda r: (r["pool_id"] or "", r["name"] or ""))
    return _envelope(rows, limit=limit, offset=offset)


def get_machine(client: HorizonClient, machine_id: str) -> dict:
    """One machine by id — same projection as machine_list. Teaching 404 on a wrong id."""
    return _summary(client.get(f"{_BASE}/{machine_id}"))


def _resolve(client: HorizonClient, machine_ids: list[str]) -> list[dict]:
    """Validate explicit ids with per-id GETs — no full-estate fetch for a targeted action.

    Only a 404 *from the machine GET* means the id is wrong; a failed login raises
    the same status from inside this call, and calling that a missing machine sends
    the operator to machine_list, which logs in first. See ``pools._require_pool``.
    """
    if not machine_ids:
        raise MachineError("Provide at least one machine_id. Run machine_list to find ids.")
    found, missing = [], []
    for mid in machine_ids:
        path = f"{_BASE}/{mid}"
        try:
            raw = client.get(path)
            found.append({**_summary(raw),
                          "_assignment_read": any(k in raw for k in _USER_FIELDS)})
        except VdiApiError as exc:
            if exc.status_code != 404 or exc.path != path:
                raise
            missing.append(mid)
    if missing:
        raise MachineError(
            f"Machine id(s) not found: {sanitize(str(missing), 200)}. Run machine_list for current ids."
        )
    return found


_DETAIL_CAP = 20


def _blast(targets: list[dict]) -> dict:
    """Counts + affected users complete; per-machine detail capped for the token budget."""
    out = {
        "machine_count": len(targets),
        "assigned_users": sorted({t["user"] for t in targets if t["user"]}),
        "machines": [
            {"id": t["id"], "name": t["name"], "state": t["state"], "user": t["user"]}
            for t in targets[:_DETAIL_CAP]
        ],
    }
    if len(targets) > _DETAIL_CAP:
        out["machines_note"] = f"showing {_DETAIL_CAP} of {len(targets)}"
    return out


def blast_radius(targets: list[dict], operation: str) -> dict:
    """L1 for the machine writes: which machines, who is assigned, and what could not be read.

    ``state`` is the one field the blast radius depends on: it is how the preview
    says whether someone is on the desktop that is about to be reset, removed or
    drained. A machine whose state did not read is unmeasured, not idle.

    Assignment is reported, not gated on: ``assigned_users`` lists only users read
    from ``user``/``assigned_user``, and a machine whose row carries neither field
    is listed in ``assignment_unread`` — its assignment was not read, which is not
    "nobody assigned".
    """
    unread = [t["id"] for t in targets if not t.get("_assignment_read", True)]
    notes = {}
    if unread:
        notes["assignment_note"] = (
            f"{len(unread)} machine(s) carry no user/assigned_user field: who is assigned to "
            f"them was not read (that is not 'nobody assigned'). Check with machine_get."
        )
    return {
        "operation": operation,
        **_blast(targets),
        "machine_ids": capped([t["id"] for t in targets]),
        "pool_ids": sorted({t["pool_id"] for t in targets if t["pool_id"]}),
        "assignment_unread_count": len(unread),
        "assignment_unread": capped(unread),
        **notes,
        "blockers": [],
        "unmeasured": [f"state of machine {t['id']}" for t in targets if not t["state"]],
    }


def _gate(verb: str, targets: list[dict], confirm: bool) -> tuple[dict, dict]:
    """Measure; on confirm, refuse an unmeasured blast radius before anything is sent."""
    blast = _blast(targets)
    radius = blast_radius(targets, verb)
    if confirm:
        refuse_unless_measured(
            f"machine {verb}", f"{radius['machine_count']} machine(s)", radius,
            "Check each machine with machine_get; retry once its state reads.",
        )
    return blast, radius


def _bulk_action(
    client: HorizonClient,
    verb: str,
    *,
    machine_ids: list[str],
    confirm: bool,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Shared preview/confirm/audit flow for the bulk POST actions (reset, enter/exit-maintenance).

    ``verb`` doubles as the POST path segment (…/action/{verb}); all POST a bare id array.
    """
    targets = _resolve(client, machine_ids)
    blast, radius = _gate(verb, targets, confirm)
    if not confirm:
        return {"action": "preview", "operation": verb, "would_affect": blast,
                "blast_radius": radius, "hint": PREVIEW_HINT}
    client.post(f"{_BASE}/action/{verb}", json_data=[t["id"] for t in targets])
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation=f"machine_{verb.replace('-', '_')}",
                         resource=",".join(machine_ids), parameters={"machine_count": blast["machine_count"]},
                         result="ok")
    return {"action": verb, "affected": blast, "blast_radius": radius}


def reset_machines(
    client: HorizonClient,
    *,
    machine_ids: list[str],
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Hard-reset desktop machine(s) — the user loses unsaved state. Preview unless confirm=True."""
    return _bulk_action(client, "reset", machine_ids=machine_ids, confirm=confirm,
                        audit_logger=audit_logger, target_name=target_name)


def set_maintenance(
    client: HorizonClient,
    *,
    machine_ids: list[str],
    enabled: bool,
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Enter (enabled=True) or exit (False) maintenance mode for machine(s). Preview unless confirm=True."""
    verb = "enter-maintenance" if enabled else "exit-maintenance"
    return _bulk_action(client, verb, machine_ids=machine_ids, confirm=confirm,
                        audit_logger=audit_logger, target_name=target_name)


def remove_machines(
    client: HorizonClient,
    *,
    machine_ids: list[str],
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Remove machine(s) from their pool — for instant clones this deletes the VM. Preview unless confirm=True."""
    targets = _resolve(client, machine_ids)
    blast, radius = _gate("remove", targets, confirm)
    if not confirm:
        return {"action": "preview", "operation": "remove", "would_affect": blast,
                "blast_radius": radius,
                "hint": f"{PREVIEW_HINT} For instant clones removing a machine deletes its backing VM."}
    # Delete one at a time; audit each success individually so a mid-loop failure still
    # records exactly what was removed (never leave already-deleted VMs unaudited).
    removed, failed = [], None
    try:
        for t in targets:
            client.delete(f"{_BASE}/{t['id']}")
            if audit_logger is not None:
                audit_logger.log(target=target_name, operation="machine_remove", resource=t["id"],
                                 parameters={"name": t["name"]}, result="ok")
            removed.append(t["id"])
    except Exception as exc:  # noqa: BLE001 — record partial progress, then re-raise a teaching error
        failed = str(exc)
    if failed is not None:
        raise MachineError(
            f"Removed {removed} then failed before the rest ({failed}). "
            f"Re-run machine_remove for the remaining ids after checking machine_list."
        )
    return {"action": "remove", "removed": removed, "affected": blast, "blast_radius": radius}
