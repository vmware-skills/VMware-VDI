"""The confirmation gate shared by every destructive VDI write (HLD §7, revised 2026-09-16).

Three levels, one vocabulary (``confirm: bool = False``):

* L1 — every response, preview or acting, carries a ``blast_radius`` dict: the
  object's identity, counts, identifiers up to a cap, ``blockers`` and
  ``unmeasured``.
* L2 — ``confirm=False`` measures and changes nothing.
* L3 — ``confirm=True`` is refused, with a teaching error, when a blocker is
  present or anything the blast radius depends on could not be read. An
  unmeasured blast radius is not a small one: a field that failed to read and a
  field that read as "nothing there" must not reach the same decision (形态 #1).

The ops functions own the gate, not the MCP wrappers, so the CLI's confirmed
call goes through the same refusal the MCP tool does.
"""

from __future__ import annotations

from vmware_vdi.ops._errors import VdiOpsError

#: Identifiers listed individually in a blast radius; the counts cover the rest.
ID_CAP = 20

#: The preview hint. It tells the agent what to do with the preview, and does not
#: read as an invitation to pass ``confirm=True`` on its own.
PREVIEW_HINT = (
    "Nothing was changed. Show blast_radius to the user; re-run with confirm=True "
    "only after they agree to it."
)


class GateRefusedError(VdiOpsError):
    """``confirm=True`` refused: a blocker is present or the blast radius is unmeasured."""


def capped(ids: list, cap: int = ID_CAP) -> list:
    """The first ``cap`` identifiers; the caller reports the full count beside them."""
    return list(ids[:cap])


def refuse_unless_measured(tool: str, subject: str, radius: dict, next_step: str) -> None:
    """Raise :class:`GateRefusedError` if ``radius`` has a blocker or an unmeasured field.

    ``next_step`` names what the operator can do to make the measurement possible;
    a refusal that only says "no" teaches the caller to route around it.
    """
    if radius["blockers"]:
        raise GateRefusedError(
            f"{tool} refused for {subject}: {' '.join(radius['blockers'])} Nothing was changed."
        )
    if radius["unmeasured"]:
        raise GateRefusedError(
            f"{tool} refused for {subject}: could not read {', '.join(radius['unmeasured'])}, "
            f"so what this call would affect is unknown. Nothing was changed. {next_step}"
        )
