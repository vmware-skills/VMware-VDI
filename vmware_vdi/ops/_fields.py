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
