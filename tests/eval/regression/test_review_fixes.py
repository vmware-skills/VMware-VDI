"""Regression evals for the Fable-5 code-review fixes (2026-07-31).

Each test reproduces the exact scenario that triggered the original defect, so a
re-introduction fails here (踩坑 #40 — verify a fix with the bug's own trigger).
"""

from __future__ import annotations

import base64

import pytest

from vmware_vdi.config import ConfigError, TargetConfig
from vmware_vdi.connection import HorizonClient
from vmware_vdi.mcp_server._shared import _safe_error
from vmware_vdi.ops import entitlements as E
from vmware_vdi.ops import pools as P
from vmware_vdi.ops._fetch import fetch_all


def test_c1_verify_ssl_false_constructs_without_urllib3():
    """C1: a self-signed-cert target must build a client, not ModuleNotFoundError('urllib3')."""
    client = HorizonClient(TargetConfig(host="cs.lab", username="admin", verify_ssl=False), "pw")
    assert client is not None


def test_h2_ops_and_config_errors_pass_through_safe_error():
    """H2: ops teaching refusals + config errors reach the agent verbatim, not 'unexpected error'."""
    from vmware_vdi.ops.machines import MachineError
    from vmware_vdi.ops.sessions import SessionError

    for exc in (
        SessionError("No active sessions for alice. Run session_list."),
        P.PoolError("Pool id 'x' not found. Run pool_list."),
        MachineError("Machine id(s) not found."),
        ConfigError("Password not found. Set environment variable: VMWARE_VDI_LAB_PASSWORD"),
        FileNotFoundError("Config file not found: ~/.vmware-vdi/config.yaml"),
    ):
        out = _safe_error(exc, "tool")
        assert "unexpected error" not in out
        assert out == str(exc)
    # a genuinely unexpected error is still masked
    assert "unexpected error" in _safe_error(RuntimeError("boom"), "tool")


class _FakeClient:
    def __init__(self, pages):
        self._pages = pages  # dict[path] -> list OR callable(params)->list
        self.calls = []

    def get(self, path, params=None, *, retries=1):
        self.calls.append((path, dict(params or {})))
        v = self._pages.get(path, [])
        return v(params) if callable(v) else v

    def post(self, path, json_data=None, *, retries=1):
        self.calls.append((path, json_data))
        return {}


def test_h3_push_image_counts_users_when_session_uses_desktop_pool_id():
    """H3: sessions keyed by `desktop_pool_id` must still be counted in the push blast radius."""
    c = _FakeClient({
        "/inventory/v1/desktop-pools": [{"id": "pool-fin", "name": "Fin", "enabled": True}],
        "/inventory/v1/desktop-pools/pool-fin": {"id": "pool-fin", "name": "Fin", "enabled": True},
        "/inventory/v1/machines": [{"id": "m-1", "desktop_pool_id": "pool-fin", "state": "CONNECTED"}],
        # session carries desktop_pool_id (NOT desktop_id) — the field the old code missed
        "/inventory/v1/sessions": [{"id": "s-1", "desktop_pool_id": "pool-fin", "user_name": "ACME\\alice"}],
    })
    prev = P.push_image(c, pool_id="pool-fin")
    assert prev["blast_radius"]["affected_desktops"] == 1
    assert prev["blast_radius"]["in_session_users"] == 1  # was 0 before the fix


def test_h4_fetch_all_paginates_beyond_one_page():
    """H4: a collection larger than one page must be fetched fully, not silently truncated."""
    def pager(params):
        page, size = params["page"], params["size"]
        total = 2500
        start = (page - 1) * size
        return [{"id": i} for i in range(start, min(start + size, total))]

    c = _FakeClient({"/x": pager})
    rows = fetch_all(c, "/x", page_size=1000)
    assert len(rows) == 2500  # 3 pages (1000 + 1000 + 500)
    assert len(c.calls) == 3


def test_n1_fetch_all_non_paginating_server_no_duplication():
    """N1: a server that ignores page/size (re-returns its full list) must not loop/duplicate.

    Was the fix's own regression: a ≥page_size list looked 'full' every page → ~100x dupes,
    inflating pool_push_image's blast preview by the same factor.
    """
    full = [{"id": i} for i in range(1000)]  # exactly page_size, same list every request
    c = _FakeClient({"/x": lambda params: full})
    rows = fetch_all(c, "/x", page_size=1000)
    assert len(rows) == 1000  # deduped by id — not 100_000
    assert len({r["id"] for r in rows}) == 1000
    assert len(c.calls) == 2  # page 1 (all new) + page 2 (nothing new → stop), not 100


def test_blast_radius_detail_list_is_capped():
    """Optimization: a mass operation keeps counts complete but caps the detail list."""
    from vmware_vdi.ops import machines as M
    from vmware_vdi.ops import sessions as S

    many = [{"id": f"s-{i}", "user": f"u{i}", "state": "CONNECTED"} for i in range(50)]
    b = S._blast(many)
    assert b["session_count"] == 50                 # count complete
    assert len(b["affected_users"]) == 50           # users complete
    assert len(b["sessions"]) == 20                 # detail capped
    assert b["sessions_note"] == "showing 20 of 50"

    mm = [{"id": f"m-{i}", "name": f"n{i}", "state": "ERROR", "user": ""} for i in range(30)]
    mb = M._blast(mm)
    assert mb["machine_count"] == 30 and len(mb["machines"]) == 20
    assert mb["machines_note"] == "showing 20 of 30"


def test_l1_entitlement_non_group_is_user():
    """L1: a non-group principal must project as USER, not None."""
    assert E._summary({"id": "s-1", "name": "alice"})["type"] == "USER"
    assert E._summary({"id": "g-1", "name": "Domain Users", "group": True})["type"] == "GROUP"


def test_h1_write_env_sets_os_environ(tmp_path, monkeypatch):
    """H1: init's _write_env must populate os.environ so the same-process connect() sees it."""
    from vmware_vdi import init_wizard

    monkeypatch.setattr(init_wizard, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(init_wizard, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("VMWARE_VDI_LAB_PASSWORD", raising=False)

    key = init_wizard._write_env("lab", "S3cr3t!")
    assert key == "VMWARE_VDI_LAB_PASSWORD"
    import os

    assert os.environ[key].startswith("b64:")
    assert base64.b64decode(os.environ[key][4:]).decode() == "S3cr3t!"
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
