"""Shared base for ops-layer teaching errors.

Every ops module's error (SessionError, PoolError, …) inherits from VdiOpsError so the
MCP `_safe_error` and CLI `cli_errors` can pass their carefully-authored, sanitized
teaching messages straight through to the user instead of masking them as an
"unexpected error" (the family's v1.8.4 lesson — see security HLD §8 / 踩坑 audit-truth).
"""

from __future__ import annotations


class VdiOpsError(Exception):
    """Base for all ops-layer refusals that carry an actionable teaching message."""
