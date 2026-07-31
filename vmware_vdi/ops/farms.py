"""RDS farm operations (read).

Verified endpoints (developer.broadcom.com operation index):

    GET /rest/inventory/v1/farms      — list
    GET /rest/inventory/v1/farms/{id} — get one

Farm enable/disable and add-rds-servers are deferred until their request-body shapes
are verified against a live Connection Server (踩坑 #36 — no guessed API bodies).
"""

from __future__ import annotations

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._paging import envelope as _envelope

_BASE = "/inventory/v1/farms"


def _summary(f: dict) -> dict:
    return {
        "id": f.get("id"),
        "name": sanitize(str(f.get("name") or f.get("display_name") or ""), 200),
        "type": f.get("type") or f.get("source"),  # AUTOMATED / MANUAL
        "enabled": f.get("enabled"),
        "rds_server_count": f.get("rds_server_count") or len(f.get("rds_server_ids") or []),
    }


def list_farms(client: HorizonClient, *, limit: int = 50, offset: int = 0) -> dict:
    """List RDS farms with type, enabled state, and server count. Paginated envelope."""
    rows = [_summary(f) for f in fetch_all(client, _BASE)]
    rows.sort(key=lambda r: r["name"] or "")
    return _envelope(rows, limit=limit, offset=offset)
