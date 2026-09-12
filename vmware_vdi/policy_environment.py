"""Tell vmware-policy which environment a target belongs to, on every surface.

Environment-scoped policy rules ("freeze-production-writes") need this skill's
own config to know which environment a target is in; vmware-policy cannot read
it. The lookup used to be registered in mcp_server/server.py, which the CLI
never imports, so @guarded CLI writes -- which go through the same guard() --
could never match an environment rule (verified 2026-09-11: after importing
only the CLI, no resolver was registered). Importing this module registers the
lookup; the MCP server and the CLI entry point both import it.
"""

from __future__ import annotations

from vmware_policy import mtime_cached_loader, set_environment_resolver, skill_name

from vmware_vdi.config import CONFIG_FILE, load_config

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
