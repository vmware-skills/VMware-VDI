"""Desktop-pool operations.

Verified Horizon 8 endpoints (developer.broadcom.com operation index):

    GET  /rest/inventory/v1/desktop-pools                       — list
    GET  /rest/inventory/v1/desktop-pools/{id}                  — get one
    POST /rest/inventory/v1/desktop-pools/action/enable         — body: [pool_id, ...]
    POST /rest/inventory/v1/desktop-pools/action/disable        — body: [pool_id, ...]
    POST /rest/inventory/v1/desktop-pools/{id}/action/apply-image — apply the pending/current image

``pool_push_image`` (apply-image) recreates every desktop in the pool → the highest
single-call blast radius in the family (security HLD §15). Its preview is NORMATIVE:
it must state the affected-desktop and in-session counts before confirm, and it must
distinguish a measured occupancy from one it could not establish — see ``_pool_blast``.
"""

from __future__ import annotations

from typing import Any

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient, VdiApiError
from vmware_vdi.ops._errors import VdiOpsError
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._fields import pool_id_of, user_of
from vmware_vdi.ops._paging import envelope as _envelope

_BASE = "/inventory/v1/desktop-pools"
_MACHINES = "/inventory/v1/machines"
_SESSIONS = "/inventory/v1/sessions"


class PoolError(VdiOpsError):
    """A pool operation cannot proceed (e.g. an id does not exist)."""


def _summary(p: dict) -> dict:
    settings = p.get("settings") or {}
    return {
        "id": p.get("id"),
        "name": sanitize(str(p.get("name") or p.get("display_name") or ""), 200),
        "type": p.get("type") or p.get("source"),  # AUTOMATED / MANUAL / RDS
        "enabled": p.get("enabled") if p.get("enabled") is not None else settings.get("enabled"),
        "provisioning_enabled": p.get("provisioning_enabled"),
        "assignment": p.get("user_assignment") or p.get("assignment"),  # DEDICATED / FLOATING
    }


def list_pools(client: HorizonClient, *, limit: int = 50, offset: int = 0) -> dict:
    """List desktop pools with type, enabled state, and assignment. Paginated envelope."""
    rows = [_summary(p) for p in fetch_all(client, _BASE)]
    rows.sort(key=lambda r: r["name"] or "")
    return _envelope(rows, limit=limit, offset=offset)


def get_pool(client: HorizonClient, pool_id: str) -> dict:
    """One pool by id — same projection as pool_list. Teaching 404 on a wrong id."""
    return _summary(client.get(f"{_BASE}/{pool_id}"))


def _require_pool(client: HorizonClient, pool_id: str) -> dict:
    """Fetch one pool by id (single GET, not a collection scan); teaching refusal on 404.

    Only a 404 *from this GET* means the id is wrong. The same status also arrives
    from ``POST /rest/login`` when nothing answers at that path — a wrong host or
    port, or a Horizon 7 server with no ``/rest`` API — because the login happens
    lazily inside this call. Re-labelling that as "pool not found, run pool_list"
    restores the exact circular advice the login fix removed, and makes it sound
    specific about an id that is perfectly valid. Matching on the path keeps the
    login diagnosis intact (形态 #7).
    """
    path = f"{_BASE}/{pool_id}"
    try:
        return _summary(client.get(path))
    except VdiApiError as exc:
        if exc.status_code != 404 or exc.path != path:
            raise
        raise PoolError(
            f"Pool id '{sanitize(pool_id, 100)}' not found. Run pool_list for current pool ids."
        ) from exc


def set_pool_enabled(
    client: HorizonClient,
    *,
    pool_id: str,
    enabled: bool,
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Enable or disable a pool (disable stops NEW sessions; existing keep running). Idempotent."""
    pool = _require_pool(client, pool_id)
    if pool["enabled"] is not None and bool(pool["enabled"]) == enabled:
        return {"action": "noop", "pool": pool,
                "hint": f"Pool '{pool['name']}' is already {'enabled' if enabled else 'disabled'}."}
    if not confirm:
        return {"action": "preview", "would_set": {"pool": pool, "enabled": enabled},
                "hint": "Re-run with confirm=True to apply."}
    client.post(f"{_BASE}/action/{'enable' if enabled else 'disable'}", json_data=[pool_id])
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="pool_set_enabled", resource=pool_id,
                         parameters={"enabled": enabled}, result="ok")
    return {"action": "set", "pool": pool, "enabled": enabled}


_DETAIL_CAP = 20


def _pool_blast(client: HorizonClient, pool_id: str) -> dict:
    """Affected-desktop and in-session counts for a pool — the normative push preview (HLD §15).

    ``in_session_count`` is the safety number: how many sessions this pool is
    carrying. It needs only that a session row can be attributed to a pool, so it
    survives rows that name nobody. ``in_session_users`` counts the distinct people
    we could actually identify, and is therefore never larger.

    ``occupancy`` says whether the count can be believed. A session row carrying
    neither a desktop-pool id nor a farm id cannot be placed in this pool *or* ruled
    out of it, so ``in_session_count`` becomes a lower bound — and a lower bound of
    zero is not a finding of zero. Reporting that as "0 logged-in users" is how the
    guard on the family's most destructive call came to pass silently (形态 #1).
    """
    machines = [m for m in fetch_all(client, _MACHINES) if pool_id_of(m) == pool_id]

    mine: list[dict] = []
    unattributed = 0
    for s in fetch_all(client, _SESSIONS):
        sid = pool_id_of(s)
        if sid == pool_id:
            mine.append(s)
        elif sid is None and not s.get("farm_id"):
            # Neither a desktop pool nor a farm: this row could belong to this pool.
            unattributed += 1

    # Filter on the sanitized value, not the raw one: a row whose identity is nothing
    # but control characters sanitizes to "" and would otherwise be counted as a person.
    identities = [sanitize(user_of(s), 200) for s in mine]
    users = sorted({u for u in identities if u})
    unidentified = sum(1 for u in identities if not u)

    # Counts are complete; the name list is capped so a large pool's preview stays compact.
    blast = {
        "affected_desktops": len(machines),
        "in_session_count": len(mine),
        "in_session_users": len(users),
        "users": users[:_DETAIL_CAP],
        "occupancy": "unknown" if unattributed else "determined",
    }
    if len(users) > _DETAIL_CAP:
        blast["users_note"] = f"showing {_DETAIL_CAP} of {len(users)}"
    if unidentified:
        blast["unidentified_sessions"] = unidentified
    if unattributed:
        blast["occupancy_note"] = (
            f"{unattributed} session(s) carry neither a desktop-pool id nor a farm id, so they "
            f"could belong to this pool: in_session_count is a lower bound, not a count."
        )
    return blast


def push_image(
    client: HorizonClient,
    *,
    pool_id: str,
    stop_on_error: bool = True,
    logoff_policy: str = "WAIT_FOR_LOGOFF",
    confirm: bool = False,
    acknowledge_unknown_occupancy: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Apply the pending image to an instant-clone pool — RECREATES EVERY DESKTOP in it.

    Highest blast radius in the family. The preview states affected-desktop and
    in-session counts (HLD §15); confirm=True schedules the apply.

    When the blast radius cannot establish occupancy the confirm is refused rather
    than taken on an unverified count — see ``_pool_blast``. It is a refusal and not
    a warning because there is nothing between this call and every desktop in the
    pool being recreated, and the operator has no second chance to read the warning
    afterwards. ``acknowledge_unknown_occupancy=True`` is the deliberate override,
    and it is recorded in the audit row so the decision is visible later.
    """
    if logoff_policy.upper() not in {"WAIT_FOR_LOGOFF", "FORCE_LOGOFF"}:
        raise PoolError("logoff_policy must be WAIT_FOR_LOGOFF or FORCE_LOGOFF.")
    pool = _require_pool(client, pool_id)
    blast = _pool_blast(client, pool_id)
    unknown = blast["occupancy"] == "unknown"
    if not confirm:
        if unknown:
            hint = (
                f"This recreates {blast['affected_desktops']} desktop(s). Who is logged in "
                f"could not be determined: {blast['occupancy_note']} Check session_list before "
                f"pushing; to proceed anyway re-run with confirm=True and "
                f"acknowledge_unknown_occupancy=True."
            )
        else:
            hint = (
                f"This recreates {blast['affected_desktops']} desktop(s), affecting "
                f"{blast['in_session_count']} logged-in session(s). "
                f"Re-run with confirm=True to schedule."
            )
        return {
            "action": "preview", "operation": "apply-image", "pool": pool,
            "blast_radius": blast, "hint": hint,
        }
    if unknown and not acknowledge_unknown_occupancy:
        raise PoolError(
            f"Refusing to recreate every desktop in pool '{pool['name'] or sanitize(pool_id, 100)}' "
            f"while its occupancy could not be determined: {blast['occupancy_note']} "
            f"Run session_list to check who is connected, or re-run with "
            f"acknowledge_unknown_occupancy=True to push regardless."
        )
    body = {"stop_on_first_error": stop_on_error, "logoff_policy": logoff_policy.upper()}
    client.post(f"{_BASE}/{pool_id}/action/apply-image", json_data=body)
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="pool_push_image", resource=pool_id,
                         parameters={"affected_desktops": blast["affected_desktops"],
                                     "in_session_count": blast["in_session_count"],
                                     "in_session_users": blast["in_session_users"],
                                     "occupancy": blast["occupancy"],
                                     "acknowledged_unknown_occupancy": bool(unknown and acknowledge_unknown_occupancy),
                                     "logoff_policy": logoff_policy.upper()}, result="ok")
    return {"action": "apply-image", "pool": pool, "blast_radius": blast,
            "hint": f"Track progress with task_status(pool_id='{pool_id}')."}
