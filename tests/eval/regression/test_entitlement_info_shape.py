"""The documented EntitlementInfo object is not an empty collection."""

import pytest

from vmware_vdi.ops.entitlements import EntitlementError, _read_entitled, list_entitlements


class Client:
    def __init__(self, payload):
        self.payload = payload

    def get(self, path, params=None):
        assert path == "/entitlements/v1/desktop-pools/pool-1"
        if isinstance(self.payload, list) and params:
            start = (params["page"] - 1) * params["size"]
            return self.payload[start:start + params["size"]]
        return self.payload


def test_documented_object_lists_sids_without_inventing_principal_type():
    client = Client({"id": "pool-1", "ad_user_or_group_ids": ["S-1-2", "S-1-1"]})
    out = list_entitlements(client, "pool-1")
    assert out["total"] == 2
    assert {r["principal_id"] for r in out["items"]} == {"S-1-1", "S-1-2"}
    assert {r["type"] for r in out["items"]} == {"UNKNOWN"}
    assert _read_entitled(client, "pool-1") == {"S-1-1", "S-1-2"}


def test_documented_empty_object_is_empty():
    assert list_entitlements(Client({"id": "pool-1", "ad_user_or_group_ids": []}), "pool-1")["total"] == 0


@pytest.mark.parametrize("payload", [
    {"id": "pool-1"}, {"ad_user_or_group_ids": [None]}, {"unexpected": []},
    [{"id": []}], [{"id": 123}],
])
def test_unreadable_response_is_not_reported_as_no_entitlements(payload):
    with pytest.raises(EntitlementError, match="could not be read"):
        list_entitlements(Client(payload), "pool-1")
    assert _read_entitled(Client(payload), "pool-1") is None


def test_legacy_principal_rows_remain_paginated_and_keep_names():
    rows = [{"id": f"S-1-{i}", "name": f"group-{i:04d}", "group": True} for i in range(1500)]
    out = list_entitlements(Client(rows), "pool-1", limit=10, offset=1000)
    assert out["total"] == 1500 and len(out["items"]) == 10
    assert out["items"][0]["principal"] == "group-1000"
    assert out["items"][0]["type"] == "GROUP"
