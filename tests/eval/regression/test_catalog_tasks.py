"""Regression evals for app-pools, images, AD search, entitlement writes, pool tasks.

Pins runtime paths ∈ verified spec (踩坑 #36), the verified EntitlementSpec body shape
({id, ad_user_or_group_ids}), pool-scoped task paths, and preview-vs-confirm gating.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spec"))
from horizon_endpoints import ENDPOINTS, normalize  # noqa: E402

from vmware_vdi.ops import apps as A  # noqa: E402
from vmware_vdi.ops import entitlements as E  # noqa: E402
from vmware_vdi.ops import images as I  # noqa: E402
from vmware_vdi.ops import tasks as T  # noqa: E402


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []

    def get(self, path, params=None, *, retries=1):
        self.calls.append(("GET", path, params))
        return {
            "/inventory/v1/application-pools": [{"id": "app-1", "name": "Notepad", "farm_id": "farm-1", "enabled": True}],
            "/external/v1/base-vms": [{"id": "bv-1", "name": "win11-gold"}],
            "/external/v1/base-snapshots": [{"id": "sn-1", "name": "2026-07", "base_vm_id": "bv-1"}],
            "/external/v1/ad-users-or-groups": [{"id": "S-1-5-21-x", "name": "Finance", "group": True, "domain": "ACME"}],
            "/inventory/v1/desktop-pools/pool-fin/tasks": [{"id": "t-1", "type": "PUSH_IMAGE", "state": "RUNNING", "percent_complete": 40}],
            "/inventory/v1/desktop-pools/pool-fin/tasks/t-1": {"id": "t-1", "type": "PUSH_IMAGE", "state": "RUNNING", "percent_complete": 40},
        }.get(path, [])

    def post(self, path, json_data=None, *, retries=1):
        self.calls.append(("POST", path, json_data))
        return {}

    def delete(self, path, json_data=None, *, retries=1):
        self.calls.append(("DELETE", path, json_data))
        return {}


def _assert_spec(c):
    for method, path, _ in c.calls:
        assert (method, normalize(path)) in ENDPOINTS, f"unverified endpoint: {method} {path}"


def test_app_pool_and_image_and_ad_projection():
    c = FakeClient()
    assert A.list_application_pools(c)["items"][0]["name"] == "Notepad"
    imgs = I.list_images(c)
    assert imgs["base_vm_count"] == 1 and imgs["snapshots"][0]["base_vm_id"] == "bv-1"
    ad = E.search_ad(c, "Fin")
    assert ad["principals"][0]["id"] == "S-1-5-21-x" and ad["principals"][0]["type"] == "GROUP"
    _assert_spec(c)


def test_entitle_body_shape_and_preview():
    c = FakeClient()
    with pytest.raises(E.EntitlementError):
        E.entitle(c, pool_id="pool-fin", ad_user_or_group_ids=[], confirm=True)
    prev = E.entitle(c, pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-x"])
    assert prev["action"] == "preview" and not any(m == "POST" for m, _, _ in c.calls)
    out = E.entitle(c, pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-x"], confirm=True)
    assert out["action"] == "entitle"
    post = [(p, b) for m, p, b in c.calls if m == "POST"][0]
    assert post[0] == "/entitlements/v1/desktop-pools"
    assert post[1] == [{"id": "pool-fin", "ad_user_or_group_ids": ["S-1-5-21-x"]}]  # verified EntitlementSpec
    _assert_spec(c)


def test_unentitle_uses_delete_body():
    c = FakeClient()
    E.unentitle(c, pool_id="pool-fin", ad_user_or_group_ids=["S-1-5-21-x"], confirm=True)
    dele = [(p, b) for m, p, b in c.calls if m == "DELETE"][0]
    assert dele == ("/entitlements/v1/desktop-pools", [{"id": "pool-fin", "ad_user_or_group_ids": ["S-1-5-21-x"]}])
    _assert_spec(c)


def test_task_status_one_and_all():
    c = FakeClient()
    one = T.task_status(c, "pool-fin", "t-1")
    assert one["state"] == "RUNNING" and one["progress"] == 40
    allt = T.task_status(c, "pool-fin")
    assert allt["tasks"][0]["id"] == "t-1"
    _assert_spec(c)


def test_task_cancel_preview_then_confirm_path():
    c = FakeClient()
    prev = T.task_cancel(c, pool_id="pool-fin", task_id="t-1")
    assert prev["action"] == "preview" and not any(m == "POST" for m, _, _ in c.calls)
    T.task_cancel(c, pool_id="pool-fin", task_id="t-1", confirm=True)
    post = [p for m, p, _ in c.calls if m == "POST"][0]
    assert post == "/inventory/v1/desktop-pools/pool-fin/tasks/t-1/action/cancel"
    _assert_spec(c)
