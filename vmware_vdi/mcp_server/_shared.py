"""Shared MCP plumbing for the vmware-vdi tool modules.

Tool functions live in ``vmware_vdi/mcp_server/tools/*.py`` grouped by domain and
register onto the single ``mcp`` instance defined here. This module must not import
from the tool packages (they import *from* here) to avoid a circular import.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from vmware_vdi.config import ConfigError
from vmware_vdi.connection import ConnectionManager, VdiApiError
from vmware_vdi.notify.audit import AuditLogger
from vmware_vdi.ops._errors import VdiOpsError

logger = logging.getLogger("vmware_vdi.mcp_server")

mcp = FastMCP("vmware-vdi")

# The shared legacy audit logger for write tools (the authoritative sink is
# ~/.vmware/audit.db via @vmware_tool; this dual-writes for back-compat).
_audit = AuditLogger()

_manager: ConnectionManager | None = None


def _get_connection(target: str | None):
    """Lazy connection-manager helper — one manager per process, client per target."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager.from_config()
    return _manager.connect(target)


def _target_name(target: str | None) -> str:
    """Audit display name for a target (or 'default')."""
    return target or "default"


def _safe_error(exc: Exception, tool: str) -> str:
    """Agent-safe error stringifier: VdiApiError teaching hints pass through; else masked.

    A VdiApiError, an ops-layer refusal (VdiOpsError: pool/session/machine/entitlement
    not-found / empty-match / bad-enum), or a config error (ConfigError, missing
    config.yaml, unknown target) already carries an actionable, sanitized teaching
    message, so it is surfaced verbatim. Any other exception is masked to avoid leaking
    internals, with the full detail going to the server log.
    """
    if isinstance(exc, (VdiApiError, VdiOpsError, ConfigError, FileNotFoundError, ConnectionError, ValueError)):
        return str(exc)
    logger.exception("Unexpected error in tool %s", tool)
    return f"{tool} failed: an unexpected error occurred (see server log)."
