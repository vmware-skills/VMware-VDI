"""Machine MCP tools (2 read / 3 write). Optional[X] signatures (踩坑 #33)."""

from __future__ import annotations

from typing import Optional

from vmware_policy import vmware_tool

from vmware_vdi.mcp_server._shared import _audit, _get_connection, _safe_error, _target_name, mcp


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def machine_list(
    pool: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    target: Optional[str] = None,
) -> dict:
    """[READ] List Horizon desktop machines, filtered by pool id / state. Paginated.

    Each item: id, name, pool_id, state (AVAILABLE/CONNECTED/AGENT_UNREACHABLE/PROVISIONING/
    ERROR/MAINTENANCE/…), assigned user, agent_version, base_image. Verify pair for the
    machine write tools.

    Args:
        pool: Filter to one desktop-pool id.
        state: Filter by machine state (e.g. AGENT_UNREACHABLE, ERROR).
        limit: Page size (default 50).
        offset: Page offset.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.machines import list_machines

        return list_machines(_get_connection(target), pool=pool, state=state, limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "machine_list")}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def machine_get(machine_id: str, target: Optional[str] = None) -> dict:
    """[READ] Full detail for one Horizon desktop machine by id (teaching 404 on a wrong id)."""
    try:
        from vmware_vdi.ops.machines import get_machine

        return get_machine(_get_connection(target), machine_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "machine_get")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def machine_reset(
    machine_ids: list[str],
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Hard-reset desktop machine(s) — the user loses unsaved state.

    confirm=False previews the blast radius (machine count + assigned users) without acting;
    confirm=True resets. For a graceful in-guest reboot use vmware-aiops (the vCenter VM). Audited.

    Args:
        machine_ids: Machine ids to reset (from machine_list).
        confirm: False previews; True resets.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.machines import reset_machines

        return reset_machines(_get_connection(target), machine_ids=machine_ids, confirm=confirm,
                              audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "machine_reset")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def machine_maintenance(
    machine_ids: list[str],
    enabled: bool,
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Enter (enabled=True) or exit (False) maintenance mode for machine(s).

    Maintenance drains the machine (no new sessions). confirm=False previews; confirm=True applies. Audited.

    Args:
        machine_ids: Machine ids (from machine_list).
        enabled: True enters maintenance; False exits.
        confirm: False previews; True applies.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.machines import set_maintenance

        return set_maintenance(_get_connection(target), machine_ids=machine_ids, enabled=enabled,
                               confirm=confirm, audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "machine_maintenance")}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def machine_remove(
    machine_ids: list[str],
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Remove machine(s) from their pool — for instant clones this DELETES the backing VM.

    confirm=False previews the blast radius; confirm=True removes. Audited.

    Args:
        machine_ids: Machine ids to remove (from machine_list).
        confirm: False previews; True removes.
        target: Horizon target from config.yaml; omit to use the default.
    """
    try:
        from vmware_vdi.ops.machines import remove_machines

        return remove_machines(_get_connection(target), machine_ids=machine_ids, confirm=confirm,
                               audit_logger=_audit, target_name=_target_name(target))
    except Exception as exc:  # noqa: BLE001
        return {"error": _safe_error(exc, "machine_remove")}
