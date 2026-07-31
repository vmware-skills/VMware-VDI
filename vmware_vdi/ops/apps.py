"""Application-pool operations (read). Verified: GET /rest/inventory/v1/application-pools."""

from __future__ import annotations

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._paging import envelope as _envelope

_BASE = "/inventory/v1/application-pools"


def _summary(a: dict) -> dict:
    return {
        "id": a.get("id"),
        "name": sanitize(str(a.get("name") or a.get("display_name") or ""), 200),
        "farm_id": a.get("farm_id"),
        "enabled": a.get("enabled"),
        "executable_path": sanitize(str(a.get("executable_path") or ""), 300),
    }


def list_application_pools(client: HorizonClient, *, limit: int = 50, offset: int = 0) -> dict:
    """List published application pools with farm, enabled state, executable path. Paginated envelope."""
    rows = [_summary(a) for a in fetch_all(client, _BASE)]
    rows.sort(key=lambda r: r["name"] or "")
    return _envelope(rows, limit=limit, offset=offset)
