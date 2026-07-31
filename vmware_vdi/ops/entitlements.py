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
from vmware_vdi.ops._paging import envelope as _envelope

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
    if not confirm:
        return {"action": "preview", "would_entitle": change, "hint": "Re-run with confirm=True to grant."}
    client.post(_BASE, json_data=_spec(pool_id, ad_user_or_group_ids))
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="entitlement_add", resource=pool_id,
                         parameters={"principals": len(ad_user_or_group_ids)}, result="ok")
    return {"action": "entitle", "entitled": change}


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
    if not confirm:
        return {"action": "preview", "would_unentitle": change, "hint": "Re-run with confirm=True to revoke."}
    client.delete(_BASE, json_data=_spec(pool_id, ad_user_or_group_ids))
    if audit_logger is not None:
        audit_logger.log(target=target_name, operation="entitlement_remove", resource=pool_id,
                         parameters={"principals": len(ad_user_or_group_ids)}, result="ok")
    return {"action": "unentitle", "unentitled": change}
