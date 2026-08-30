"""Shared field projections across ops modules.

Horizon reports the desktop-pool id of a machine/session row under several
documented field names. Centralising the fallback chain keeps every module's
projection — and the push-image blast radius — in agreement. The chain is
deliberately defensive pending live-server validation (踩坑 #36).
"""

from __future__ import annotations

from typing import Any


def pool_id_of(row: dict) -> Any:
    """Desktop-pool id of a machine or session row, across documented field-name variants."""
    return row.get("desktop_pool_id") or row.get("desktop_id") or row.get("pool_id")


#: Session-row keys that can carry the identity of the person in the session, most
#: human-readable first. ``user_id`` is the one a Horizon 8 Connection Server
#: actually sends: the documented ``SessionInfo`` model (developer.broadcom.com,
#: VMware Horizon Server API — "Get Session Info") lists ``user_id``, "Unique SID
#: of the user logged into the session", and has **no** ``user_name`` field. The
#: readable names are kept ahead of it because other rows in this API (and the
#: global-sessions variant) do carry them, and a SID is a poor thing to show an
#: operator when a name is available.
#: ``broker_user_id`` is deliberately absent: it names the brokering account, not
#: the person on the desktop, and reading it as the occupant would attribute a
#: session to the wrong user.
_USER_KEYS = ("user_name", "username", "user", "user_id")


def user_of(row: dict) -> str:
    """Identity of the person in a session row, or ``""`` when the row names nobody.

    Returns the raw value; callers sanitize at their own output boundary.

    The empty string means *this row identifies nobody*, which is not the same as
    *nobody is there* — a caller counting occupancy must keep the two apart
    (形态 #1). See ``pools._pool_blast``.
    """
    for key in _USER_KEYS:
        value = row.get(key)
        if value:
            return str(value)
    return ""
