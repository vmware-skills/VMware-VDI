"""Shared list-envelope helper for the ops layer.

Every ``*_list`` op returns this envelope (not a bare array) so an agent reads rows
from ``items`` and checks ``truncated`` before concluding a listing is complete —
empty ``items`` with ``truncated: false`` means checked-and-none, not a failure.
"""

from __future__ import annotations


def envelope(items: list[dict], *, limit: int, offset: int) -> dict:
    total = len(items)
    page = items[offset : offset + limit]
    return {
        "items": page,
        "returned": len(page),
        "limit": limit,
        "offset": offset,
        "total": total,
        "truncated": offset + limit < total,
        "hint": "" if offset + limit >= total else f"{total - offset - limit} more — raise offset/limit.",
    }
