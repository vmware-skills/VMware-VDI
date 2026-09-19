"""Entitlement operations (read + write). All endpoints/bodies verified against
developer.broadcom.com (VMware Horizon Server API):

    GET    /rest/entitlements/v1/desktop-pools/{id} — who is entitled to a pool
    POST   /rest/entitlements/v1/desktop-pools      — body: [EntitlementSpec]
    DELETE /rest/entitlements/v1/desktop-pools      — body: [EntitlementSpec]
    GET    /rest/external/v1/ad-users-or-groups     — resolve AD SIDs for entitle

EntitlementSpec = {"id": <pool_id>, "ad_user_or_group_ids": [<SID>, ...]}.
"""

from __future__ import annotations

from typing import Any

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._errors import VdiOpsError
from vmware_vdi.ops._fetch import fetch_all
from vmware_vdi.ops._gate import PREVIEW_HINT, capped, refuse_unless_measured
from vmware_vdi.ops._paging import envelope as _envelope
from vmware_vdi.ops.pools import _require_pool

_BASE = "/entitlements/v1/desktop-pools"
_AD = "/external/v1/ad-users-or-groups"


class EntitlementError(VdiOpsError):
    """An entitlement operation cannot proceed (e.g. no AD principals given)."""


def _summary(e: dict) -> dict:
    return {
        "principal_id": e.get("ad_user_or_group_id") or e.get("id"),
        "principal": sanitize(str(e.get("name") or e.get("display_name") or ""), 200),
        "type": "GROUP" if e.get("group") else (e.get("type") or "USER"),
    }


def list_entitlements(client: HorizonClient, pool_id: str, *, limit: int = 50, offset: int = 0) -> dict:
    """List the AD users/groups entitled to one desktop pool. Paginated envelope.

    A wrong pool id returns a teaching 404 via VdiApiError.
    """
    rows = [_summary(e) for e in fetch_all(client, f"{_BASE}/{pool_id}")]
    rows.sort(key=lambda r: r["principal"] or "")
    return _envelope(rows, limit=limit, offset=offset)


def search_ad(client: HorizonClient, name: str, *, limit: int = 25) -> dict:
    """Resolve AD users/groups by name → their SIDs, for entitle/unentitle (GET ad-users-or-groups).

    Filtered client-side: Horizon's ``filter`` param takes a URL-encoded JSON object, so a
    bare name string would 400 the call.
    """
    out = []
    for p in fetch_all(client, _AD):
        principal = sanitize(str(p.get("name") or p.get("display_name") or ""), 200)
        if not name or name.lower() in principal.lower():
            out.append({
                "id": p.get("id"),  # the SID used by entitle
                "name": principal,
                "type": "GROUP" if p.get("group") else "USER",
                "domain": sanitize(str(p.get("domain") or ""), 100),
            })
    return {"principals": out[:limit], "returned": min(len(out), limit)}


def _spec(pool_id: str, ad_ids: list[str]) -> list[dict]:
    return [{"id": pool_id, "ad_user_or_group_ids": ad_ids}]


def _principals(rows: list) -> set | None:
    ids = [(r.get("ad_user_or_group_id") or r.get("id")) if isinstance(r, dict) else None for r in rows]
    if any(not i for i in ids):
        return None
    return set(ids)


def _read_entitled(client: HorizonClient, pool_id: str) -> set | None:
    """The SIDs currently entitled to ``pool_id``, or None when the answer could not be read.

    Two shapes are accepted: Horizon's ``EntitlementInfo`` (``{"id": <pool>,
    "ad_user_or_group_ids": [...]}``, one object, read whole) and a list of
    per-principal rows (bare, or under ``results``/``items``), which is what
    ``list_entitlements`` projects. A list is paginated like every Horizon
    collection, so it is read with ``fetch_all`` — every page, not the first one:
    a SID entitled on page 2 must not read as *not entitled*. Anything else —
    including a row with no principal id — is *unread*, not *nobody*: an empty set
    would tell the operator that a revoke takes access from no one (形态 #1).
    """
    path = f"{_BASE}/{pool_id}"
    data = client.get(path)
    if isinstance(data, dict):
        ids = data.get("ad_user_or_group_ids")
        if isinstance(ids, list) and all(isinstance(i, str) and i for i in ids):
            return set(ids)
        if not isinstance(data.get("results", data.get("items")), list):
            return None
    elif not isinstance(data, list):
        return None
    return _principals(fetch_all(client, path))


def _radius(client: HorizonClient, pool_id: str, ad_ids: list[str], operation: str) -> dict:
    """L1 for entitlement writes: the pool, the principals, and whose access actually changes."""
    pool = _require_pool(client, pool_id)
    entitled = _read_entitled(client, pool_id)
    radius: dict[str, Any] = {
        "operation": operation,
        "pool_id": pool_id,
        "pool_name": pool["name"],
        "principal_count": len(ad_ids),
        "principal_ids": capped(ad_ids),
        "blockers": [],
        "unmeasured": [] if entitled is not None else ["current entitlements of the pool"],
    }
    if entitled is None:
        return radius
    if operation == "entitle":
        new = [i for i in ad_ids if i not in entitled]
        radius.update(already_entitled=capped([i for i in ad_ids if i in entitled]),
                      newly_entitled=capped(new), newly_entitled_count=len(new))
    else:
        losing = [i for i in ad_ids if i in entitled]
        radius.update(losing_access=capped(losing), losing_access_count=len(losing),
                      not_entitled=capped([i for i in ad_ids if i not in entitled]))
    return radius


def _refuse_unmeasured(tool: str, radius: dict) -> None:
    refuse_unless_measured(
        tool, f"pool '{radius['pool_name'] or sanitize(radius['pool_id'], 100)}'", radius,
        "Run entitlement_list for the pool; retry once it lists who is entitled.",
    )


def entitle(
    client: HorizonClient,
    *,
    pool_id: str,
    ad_user_or_group_ids: list[str],
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Grant pool access to AD user/group SID(s) (from search_ad). Preview unless confirm=True."""
    if not ad_user_or_group_ids:
        raise EntitlementError("Provide ad_user_or_group_ids (SIDs from search_ad).")
    change = {"pool_id": pool_id, "ad_user_or_group_ids": ad_user_or_group_ids}
    radius = _radius(client, pool_id, ad_user_or_group_ids, "entitle")
    if not confirm:
        return {"action": "preview", "would_entitle": change, "blast_radius": radius, "hint": PREVIEW_HINT}
    _refuse_unmeasured("entitlement_add", radius)
    client.post(_BASE, json_data=_spec(pool_id, ad_user_or_group_ids))
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="entitlement_add", resource=pool_id,
                         parameters={"principals": len(ad_user_or_group_ids)}, result="ok")
    return {"action": "entitle", "entitled": change, "blast_radius": radius}


def unentitle(
    client: HorizonClient,
    *,
    pool_id: str,
    ad_user_or_group_ids: list[str],
    confirm: bool = False,
    audit_logger: Any = None,
    target_name: str = "",
) -> dict:
    """Revoke pool access from AD user/group SID(s). Preview unless confirm=True."""
    if not ad_user_or_group_ids:
        raise EntitlementError("Provide ad_user_or_group_ids (SIDs from entitlement_list).")
    change = {"pool_id": pool_id, "ad_user_or_group_ids": ad_user_or_group_ids}
    radius = _radius(client, pool_id, ad_user_or_group_ids, "unentitle")
    if not confirm:
        return {"action": "preview", "would_unentitle": change, "blast_radius": radius, "hint": PREVIEW_HINT}
    _refuse_unmeasured("entitlement_remove", radius)
    client.delete(_BASE, json_data=_spec(pool_id, ad_user_or_group_ids))
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="entitlement_remove", resource=pool_id,
                         parameters={"principals": len(ad_user_or_group_ids)}, result="ok")
    return {"action": "unentitle", "unentitled": change, "blast_radius": radius}
