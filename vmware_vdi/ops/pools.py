"""Desktop-pool operations.

Verified Horizon 8 endpoints (developer.broadcom.com operation index):

    GET  /rest/inventory/v1/desktop-pools                       — list
    GET  /rest/inventory/v1/desktop-pools/{id}                  — get one
    POST /rest/inventory/v1/desktop-pools/action/enable         — body: [pool_id, ...]
    POST /rest/inventory/v1/desktop-pools/action/disable        — body: [pool_id, ...]
    POST /rest/inventory/v1/desktop-pools/{id}/action/apply-image — apply the pending/current image

``pool_push_image`` (apply-image) recreates every desktop in the pool → the highest
single-call blast radius in the family (security HLD §15). Its preview is NORMATIVE:
it must state the affected-desktop and in-session-user counts before confirm.
"""

from __future__ import annotations

from typing import Any

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._errors import VdiOpsError
from vmware_vdi.ops._fetch import fetch_all
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


def _fetch_all(client: HorizonClient, path: str) -> list[dict]:
    return fetch_all(client, path)


def list_pools(client: HorizonClient, *, limit: int = 50, offset: int = 0) -> dict:
    """List desktop pools with type, enabled state, and assignment. Paginated envelope."""
    rows = [_summary(p) for p in _fetch_all(client, _BASE)]
    rows.sort(key=lambda r: r["name"] or "")
    return _envelope(rows, limit=limit, offset=offset)


def get_pool(client: HorizonClient, pool_id: str) -> dict:
    """One pool by id — same projection as pool_list. Teaching 404 on a wrong id."""
    return _summary(client.get(f"{_BASE}/{pool_id}"))


def _require_pool(client: HorizonClient, pool_id: str) -> dict:
    for p in (_summary(x) for x in _fetch_all(client, _BASE)):
        if p["id"] == pool_id:
            return p
    raise PoolError(f"Pool id '{sanitize(pool_id, 100)}' not found. Run pool_list for current pool ids.")


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


def _pool_blast(client: HorizonClient, pool_id: str) -> dict:
    """Affected-desktop and in-session-user counts for a pool — the normative push preview (HLD §15)."""
    machines = [m for m in _fetch_all(client, _MACHINES)
                if (m.get("desktop_pool_id") or m.get("desktop_id") or m.get("pool_id")) == pool_id]
    sessions = [s for s in _fetch_all(client, _SESSIONS)
                if (s.get("desktop_pool_id") or s.get("desktop_id") or s.get("pool_id")) == pool_id]
    users = sorted({sanitize(str(s.get("user_name") or ""), 200) for s in sessions if s.get("user_name")})
    # Count is complete; the name list is capped so a large pool's preview stays compact.
    blast = {"affected_desktops": len(machines), "in_session_users": len(users), "users": users[:20]}
    if len(users) > 20:
        blast["users_note"] = f"showing 20 of {len(users)}"
    return blast


def push_image(
    client: HorizonClient,
    *,
    pool_id: str,
    stop_on_error: bool = True,
    logoff_policy: str = "WAIT_FOR_LOGOFF",
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Apply the pending image to an instant-clone pool — RECREATES EVERY DESKTOP in it.

    Highest blast radius in the family. The preview states affected-desktop and
    in-session-user counts (HLD §15); confirm=True schedules the apply.
    """
    if logoff_policy.upper() not in {"WAIT_FOR_LOGOFF", "FORCE_LOGOFF"}:
        raise PoolError("logoff_policy must be WAIT_FOR_LOGOFF or FORCE_LOGOFF.")
    pool = _require_pool(client, pool_id)
    blast = _pool_blast(client, pool_id)
    if not confirm:
        return {
            "action": "preview", "operation": "apply-image", "pool": pool,
            "blast_radius": blast,
            "hint": f"This recreates {blast['affected_desktops']} desktop(s), affecting "
                    f"{blast['in_session_users']} logged-in user(s). Re-run with confirm=True to schedule.",
        }
    body = {"stop_on_first_error": stop_on_error, "logoff_policy": logoff_policy.upper()}
    client.post(f"{_BASE}/{pool_id}/action/apply-image", json_data=body)
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="pool_push_image", resource=pool_id,
                         parameters={"affected_desktops": blast["affected_desktops"],
                                     "in_session_users": blast["in_session_users"],
                                     "logoff_policy": logoff_policy.upper()}, result="ok")
    return {"action": "apply-image", "pool": pool, "blast_radius": blast,
            "hint": f"Track progress with task_status(pool_id='{pool_id}')."}
