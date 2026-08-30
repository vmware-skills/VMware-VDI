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


from vmware_policy import describe_tool_parameters

# The docstrings in the tool modules imported above are the schema.
# `describe_tool_parameters` copies each `Args:` entry into the JSON schema an
# agent actually reads, and closes the object. Without it every parameter
# reaches the model as a bare name and a type, which is how a wrong guess
# becomes an unfiltered result or a silent zero-row answer instead of an error
# (real-hardware round, 2026-08-30). It runs here, after the imports that
# register the tools, because there is nothing to describe before them.
_DESCRIBED_PARAMS = describe_tool_parameters(mcp._tool_manager._tools)


def main() -> None:
    """Console-script entry point: serve the registered tools over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
