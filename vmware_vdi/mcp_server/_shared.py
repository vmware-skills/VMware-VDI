"""Shared MCP plumbing for the vmware-vdi tool modules.

Tool functions live in ``vmware_vdi/mcp_server/tools/*.py`` grouped by domain and
register onto the single ``mcp`` instance defined here. This module must not import
from the tool packages (they import *from* here) to avoid a circular import.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from vmware_vdi import __version__
from vmware_vdi.config import ConfigError, load_config
from vmware_vdi.connection import ConnectionManager, VdiApiError
from vmware_vdi.notify.audit import AuditLogger
from vmware_vdi.ops._errors import VdiOpsError

logger = logging.getLogger("vmware_vdi.mcp_server")

#: Written from this skill's own SKILL.md description — no capability is claimed
#: here that the tool set does not have.
_BASE_INSTRUCTIONS = (
    "VMware/Omnissa Horizon VDI operations through the Connection Server REST "
    "API: desktop pools, RDS farms and published apps, user sessions, desktop "
    "machines, entitlements, Horizon events/health/statistics, and instant-clone "
    "image push."
)

_TARGET_RULE = (
    " Choosing a target: every tool that reaches Horizon takes `target`, and "
    "each target is one Horizon/Omnissa Connection Server. Choose it from what "
    "the user asked. If the request does not say which Connection Server to use, "
    "ask the user which one before querying. Say which `target` answered in the "
    "answer."
)


def _target_instructions() -> str:
    """Server instructions that name the configured targets and how to choose one.

    ``initialize`` hands the client this text, and for a skill whose every tool
    takes ``target`` it is the only place a client learns which Connection Servers exist.
    Without it the model calls tools with no target, silently gets the default,
    and answers confidently about the wrong system — on 2026-09-15 Monitor's
    default was a standalone ESXi host, and "how many VMs does the vCenter have"
    was answered from that host.

    Built at run time so it cannot drift from the operator's file, and never
    raises: a missing config is the normal state before ``vmware-vdi init`` and must
    not stop the server from starting — the tools report that error themselves,
    with the remedy.

    All three branches keep the ``Configured targets:`` sentence. A client shown
    no listing cannot tell "this skill has no targets" from "this skill could not
    read them", and the first reading is the one that produces a confident answer
    about a system nobody chose. The gate probes under an empty HOME for exactly
    this reason: with the operator's config present, the branch that omits the
    listing is unreachable.
    """
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — instructions are advisory, startup is not
        # Only the exception's *type*: its text quotes the config path.
        detail = f"could not be read ({type(exc).__name__}) — run `vmware-vdi doctor`"
    else:
        entries = []
        for name, t in cfg.targets.items():
            # ``domain`` only when set: it is what tells two Connection Servers in
            # different AD domains apart, and an empty one is noise.
            extra = f", domain {t.domain}" if t.domain else ""
            default = ", default" if name == cfg.default_target else ""
            entries.append(f"{name} ({t.host}{extra}{default})")
        listed = "; ".join(entries)
        detail = listed or (
            "none yet — add one under `targets:` in ~/.vmware-vdi/config.yaml"
        )
    return f"{_BASE_INSTRUCTIONS} Configured targets: {detail}.{_TARGET_RULE}"


mcp = FastMCP("vmware-vdi", instructions=_target_instructions())

# FastMCP takes no version argument and leaves the lowlevel server's at
# None, which makes `initialize` answer with the MCP SDK's version rather
# than ours. Set it so a client can tell which release it is talking to.
mcp._mcp_server.version = __version__

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
