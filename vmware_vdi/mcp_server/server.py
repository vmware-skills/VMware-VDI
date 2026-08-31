"""vmware-vdi MCP server (stdio) — thin entrypoint.

The ``mcp`` instance and shared helpers live in ``vmware_vdi/mcp_server/_shared.py``.
This module imports the per-domain tool modules (so their ``@mcp.tool`` decorators
run and register onto ``mcp``), re-exports the shared plumbing for historical import
paths, and exposes ``main()``.

Lives inside the package namespace (``vmware_vdi.mcp_server``) so two family packages
never collide on a top-level ``mcp_server`` import (踩坑 #41).
"""

from __future__ import annotations

# Shared plumbing — re-exported so `from vmware_vdi.mcp_server.server import mcp, _get_connection, ...`
# (and monkeypatch targets) keep resolving.
from vmware_vdi.mcp_server._shared import (  # noqa: F401
    _audit,
    _get_connection,
    _safe_error,
    _target_name,
    logger,
    mcp,
)

# Import tool modules for their registration side effect.
from vmware_vdi.mcp_server.tools import (  # noqa: F401
    catalog,
    entitlement,
    farm,
    machine,
    monitor,
    pool,
    session,
    task,
)

__all__ = ["_audit", "_get_connection", "_safe_error", "_target_name", "main", "mcp"]


from vmware_vdi.config import CONFIG_FILE, load_config
from vmware_policy import (
    describe_tool_parameters,
    mtime_cached_loader,
    set_environment_resolver,
    skill_name,
)

# The docstrings in the tool modules imported above are the schema.
# `describe_tool_parameters` copies each `Args:` entry into the JSON schema an
# agent actually reads, and closes the object. Without it every parameter
# reaches the model as a bare name and a type, which is how a wrong guess
# becomes an unfiltered result or a silent zero-row answer instead of an error
# (real-hardware round, 2026-08-30). It runs here, after the imports that
# register the tools, because there is nothing to describe before them.
_DESCRIBED_PARAMS = describe_tool_parameters(mcp._tool_manager._tools)


# ── environment resolver ─────────────────────────────────────────────────────
#
# Policy rules scope by environment ("irreversible work in production needs a
# second person"), and vmware_policy cannot read this skill's config itself —
# registering this lookup is what lets those rules fire at all. Without it every
# target reads as undeclared and no environment-scoped rule ever matches.
#
# This skill's config has carried `environment_for` since it shipped; the
# registration was simply never wired, and the family gate that should have
# caught it did not list this repo. Both are fixed together (2026-08-30).
_cached_config = mtime_cached_loader("VMWARE_VDI_CONFIG", CONFIG_FILE, load_config)


def _environment_for(target: str | None) -> str:
    """The environment label for ``target``, or "" when it cannot be read.

    An unreadable config means *undeclared*, not *production*: guessing the
    strict label here would refuse work the operator never scoped, and guessing
    the loose one would be the fail-open this family keeps finding. Undeclared
    is the honest answer and the one vmware_policy documents.
    """
    try:
        return _cached_config().environment_for(target)
    except Exception:  # noqa: BLE001 — an unreadable config means "undeclared"
        return ""


# Keyed by skill: the registry used to be one process-global slot, and a
# bare `import` of any sibling's server module replaced whichever resolver
# was there -- measured turning a freeze-production-writes rule from DENY
# to ALLOW. Keyed, a resolver only ever answers for its own skill, so
# registering at import time is safe again.
set_environment_resolver(_environment_for, skill=skill_name(__name__))


def main() -> None:
    """Console-script entry point: serve the registered tools over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
