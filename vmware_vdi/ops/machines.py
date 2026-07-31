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

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._errors import VdiOpsError
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._paging import envelope as _envelope

_BASE = "/inventory/v1/machines"


class MachineError(VdiOpsError):
    """A machine operation cannot proceed (e.g. an id does not exist)."""


def _summary(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "name": sanitize(str(m.get("name") or m.get("machine_name") or ""), 200),
        "pool_id": m.get("desktop_pool_id") or m.get("desktop_id") or m.get("pool_id"),
        "state": m.get("state") or m.get("machine_state"),
        "user": sanitize(str(m.get("user") or m.get("assigned_user") or ""), 200),
        "agent_version": m.get("agent_version"),
        "base_image": m.get("base_image_snapshot") or m.get("base_image"),
    }


def _fetch_all(client: HorizonClient) -> list[dict]:
    return fetch_all(client, _BASE)


def list_machines(
    client: HorizonClient,
    *,
    pool: str | None = None,
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List desktop machines, optionally filtered by pool id / state. Paginated envelope."""
    rows = [_summary(m) for m in _fetch_all(client)]
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
    if not machine_ids:
        raise MachineError("Provide at least one machine_id. Run machine_list to find ids.")
    by_id = {r["id"]: r for r in (_summary(m) for m in _fetch_all(client))}
    missing = [mid for mid in machine_ids if mid not in by_id]
    if missing:
        raise MachineError(
            f"Machine id(s) not found: {sanitize(str(missing), 200)}. Run machine_list for current ids."
        )
    return [by_id[mid] for mid in machine_ids]


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


def reset_machines(
    client: HorizonClient,
    *,
    machine_ids: list[str],
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Hard-reset desktop machine(s) — the user loses unsaved state. Preview unless confirm=True."""
    targets = _resolve(client, machine_ids)
    blast = _blast(targets)
    if not confirm:
        return {"action": "preview", "operation": "reset", "would_affect": blast,
                "hint": f"Re-run with confirm=True to reset {blast['machine_count']} machine(s)."}
    client.post(f"{_BASE}/action/reset", json_data=[t["id"] for t in targets])
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="machine_reset", resource=",".join(machine_ids),
                         parameters={"machine_count": blast["machine_count"]}, result="ok")
    return {"action": "reset", "affected": blast}


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
    targets = _resolve(client, machine_ids)
    blast = _blast(targets)
    verb = "enter-maintenance" if enabled else "exit-maintenance"
    if not confirm:
        return {"action": "preview", "operation": verb, "would_affect": blast,
                "hint": f"Re-run with confirm=True to {verb} {blast['machine_count']} machine(s)."}
    client.post(f"{_BASE}/action/{verb}", json_data=[t["id"] for t in targets])
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation=f"machine_{verb.replace('-', '_')}",
                         resource=",".join(machine_ids), parameters={"machine_count": blast["machine_count"]},
                         result="ok")
    return {"action": verb, "affected": blast}


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
    blast = _blast(targets)
    if not confirm:
        return {"action": "preview", "operation": "remove", "would_affect": blast,
                "hint": f"Re-run with confirm=True to remove {blast['machine_count']} machine(s). "
                        "For instant clones this deletes the backing VM."}
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
    return {"action": "remove", "removed": removed, "affected": blast}
