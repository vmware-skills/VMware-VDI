from unittest.mock import Mock
import pytest
from vmware_vdi.ops import _fetch
from vmware_vdi.ops._errors import VdiOpsError

@pytest.mark.parametrize("payload", [{"error": "fixture-secret"}, {"results": None, "items": []}, "login page"])
def test_unknown_collection_is_not_a_complete_empty_inventory(payload):
    client = Mock()
    client.get.return_value = payload
    with pytest.raises(VdiOpsError, match="collection") as exc:
        _fetch.fetch_all(client, "/fixture")
    assert "fixture-secret" not in str(exc.value)

def test_page_budget_cannot_turn_an_incomplete_inventory_into_complete():
    client = Mock()
    client.get.side_effect = lambda path, params: [{"id": str(params["page"])}]
    old = _fetch._MAX_PAGES
    _fetch._MAX_PAGES = 2
    try:
        with pytest.raises(VdiOpsError, match="incomplete"):
            _fetch.fetch_all(client, "/fixture", page_size=1)
    finally:
        _fetch._MAX_PAGES = old
    assert client.get.call_count == 2

from test_mcp_writes_state_blast_radius import fresh_policy, horizon
from vmware_vdi.mcp_server.tools.pool import push_desktop_pool_image

def test_confirm_and_occupancy_override_cannot_write_after_malformed_inventory(horizon):
    original = horizon.get
    def get(path, params=None, **kwargs):
        if path == "/inventory/v1/machines":
            return {"error": "fixture-secret"}
        return original(path, params, **kwargs)
    horizon.get = get
    out = push_desktop_pool_image(pool_id="pool-fin", confirm=True, acknowledge_unknown_occupancy=True)
    assert "error" in out and "collection" in out["error"]
    assert "fixture-secret" not in str(out)
    assert not horizon.writes()
