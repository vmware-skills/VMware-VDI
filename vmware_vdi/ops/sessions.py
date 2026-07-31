"""Session operations — the core help-desk surface.

Horizon 8 Connection Server REST endpoints (verified against developer.broadcom.com,
VMware Horizon Server API):

    GET  /rest/inventory/v1/sessions                     — list
    GET  /rest/inventory/v1/sessions/{id}                — get one
    POST /rest/inventory/v1/sessions/action/logoff       — body: [session_id, ...]
    POST /rest/inventory/v1/sessions/action/disconnect   — body: [session_id, ...]
    POST /rest/inventory/v1/sessions/action/send-message — body: {session_ids, message_type, message}

The GET projection uses defensive ``.get()`` across the documented field names; the
mock-shape regression test (``tests/eval/regression/test_sessions.py``) pins them and
must be re-checked against a live Connection Server before first production use
(踩坑 #36 — never trust an API layer written from memory).
"""

from __future__ import annotations

from typing import Any

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient, VdiApiError
from vmware_vdi.ops._errors import VdiOpsError
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._paging import envelope as _envelope

_BASE = "/inventory/v1/sessions"


class SessionError(VdiOpsError):
    """A session operation cannot proceed (e.g. no sessions match a user)."""


def _summary(s: dict) -> dict:
    """High-signal projection of one session. Defensive across documented field names."""
    return {
        "id": s.get("id"),
        "user": sanitize(str(s.get("user_name") or s.get("username") or ""), 200),
        "type": s.get("session_type") or s.get("type"),  # DESKTOP / APPLICATION
        "state": s.get("session_state") or s.get("state"),  # CONNECTED / DISCONNECTED / PENDING
        "protocol": s.get("session_protocol") or s.get("protocol"),  # BLAST / PCOIP / RDP
        "pool_id": s.get("desktop_pool_id") or s.get("desktop_id") or s.get("farm_id") or s.get("pool_id"),
        "machine_id": s.get("machine_id") or s.get("machine_or_rds_server_id"),
        "start_time": s.get("start_time") or s.get("session_start_time"),
    }


def list_sessions(
    client: HorizonClient,
    *,
    user: str | None = None,
    pool: str | None = None,
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List sessions, optionally filtered by user / pool id / state. Paginated envelope."""
    rows = [_summary(s) for s in fetch_all(client, _BASE)]
    if user:
        u = user.lower()
        rows = [r for r in rows if u in (r["user"] or "").lower()]
    if pool:
        rows = [r for r in rows if r["pool_id"] == pool]
    if state:
        st = state.upper()
        rows = [r for r in rows if (r["state"] or "").upper() == st]
    rows.sort(key=lambda r: (r["user"] or "", r["id"] or ""))
    return _envelope(rows, limit=limit, offset=offset)


def get_session(client: HorizonClient, session_id: str) -> dict:
    """One session by id — same projection as session_list. Teaching 404 on a wrong id."""
    return _summary(client.get(f"{_BASE}/{session_id}"))


def _resolve_ids(client: HorizonClient, session_ids: list[str] | None, user: str | None) -> list[dict]:
    """Resolve the target sessions from explicit ids or a user lookup. Refuses an empty match.

    Explicit ids are validated with per-id GETs — no full-estate fetch for a targeted
    logoff. A user lookup needs the full list to substring-match.
    """
    if session_ids:
        found, missing = [], []
        for sid in session_ids:
            try:
                found.append(_summary(client.get(f"{_BASE}/{sid}")))
            except VdiApiError as exc:
                if exc.status_code != 404:
                    raise
                missing.append(sid)
        if missing:
            raise SessionError(
                f"Session id(s) not found: {sanitize(str(missing), 200)}. "
                "Run session_list for current session ids."
            )
        return found
    if user:
        u = user.lower()
        everyone = (_summary(s) for s in fetch_all(client, _BASE))
        matched = [r for r in everyone if u in (r["user"] or "").lower()]
        if not matched:
            raise SessionError(
                f"No active sessions for user matching '{sanitize(user, 100)}'. "
                "Run session_list to see who is connected."
            )
        return matched
    raise SessionError("Provide either session_ids or user to identify the target session(s).")


_DETAIL_CAP = 20


def _blast(targets: list[dict]) -> dict:
    """Blast-radius descriptor stated in every preview and result.

    Counts and affected users are complete; the per-session detail list is capped so a
    mass logoff does not flood the agent's context with hundreds of rows (high-signal
    token budget — Anthropic tool-design principle).
    """
    out = {
        "session_count": len(targets),
        "affected_users": sorted({t["user"] for t in targets if t["user"]}),
        "sessions": [{"id": t["id"], "user": t["user"], "state": t["state"]} for t in targets[:_DETAIL_CAP]],
    }
    if len(targets) > _DETAIL_CAP:
        out["sessions_note"] = f"showing {_DETAIL_CAP} of {len(targets)}"
    return out


def _act(
    client: HorizonClient,
    action: str,
    *,
    session_ids: list[str] | None,
    user: str | None,
    confirm: bool,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Shared preview/confirm/audit flow for logoff & disconnect.

    ``action`` doubles as the POST path verb (…/action/{action}); both POST a bare id array.
    """
    targets = _resolve_ids(client, session_ids, user)
    blast = _blast(targets)
    if not confirm:
        return {
            "action": "preview",
            "operation": action,
            "would_affect": blast,
            "hint": f"Re-run with confirm=True to {action} {blast['session_count']} session(s).",
        }
    ids = [t["id"] for t in targets]
    client.post(f"{_BASE}/action/{action}", json_data=ids)  # body is a bare id array
    if audit_logger is not None:
        audit_logger.log(
            target=target_name, operation=action, resource=",".join(ids),
            parameters={"session_count": blast["session_count"], "users": blast["affected_users"]},
            result="ok",
        )
    return {"action": action, "affected": blast}


def logoff_sessions(
    client: HorizonClient,
    *,
    session_ids: list[str] | None = None,
    user: str | None = None,
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Force-logoff session(s) — kicks the user (profile write-back). Preview unless confirm=True."""
    return _act(
        client, "logoff", session_ids=session_ids, user=user,
        confirm=confirm, audit_logger=audit_logger, target_name=target_name,
    )


def disconnect_sessions(
    client: HorizonClient,
    *,
    session_ids: list[str] | None = None,
    user: str | None = None,
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Disconnect session(s) — state preserved, user can reconnect. Preview unless confirm=True."""
    return _act(
        client, "disconnect", session_ids=session_ids, user=user,
        confirm=confirm, audit_logger=audit_logger, target_name=target_name,
    )


def send_message(
    client: HorizonClient,
    *,
    message: str,
    session_ids: list[str] | None = None,
    user: str | None = None,
    message_type: str = "INFO",
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Send a message to session(s) (e.g. 'maintenance in 10 min'). Low-risk — no confirm gate."""
    valid = {"INFO", "WARNING", "ERROR"}
    if message_type.upper() not in valid:
        raise SessionError(f"message_type must be one of {sorted(valid)} (got '{sanitize(message_type, 40)}').")
    targets = _resolve_ids(client, session_ids, user)
    ids = [t["id"] for t in targets]
    client.post(
        f"{_BASE}/action/send-message",
        json_data={"session_ids": ids, "message_type": message_type.upper(), "message": sanitize(message, 500)},
    )
    if audit_logger is not None:
        audit_logger.log(
            target=target_name, operation="send_message", resource=",".join(ids),
            parameters={"session_count": len(ids), "message_type": message_type.upper()}, result="ok",
        )
    return {"action": "send_message", "sent_to": _blast(targets)}
