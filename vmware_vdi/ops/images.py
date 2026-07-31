"""Instant-clone image catalog (read). Verified:
    GET /rest/external/v1/base-vms        — golden base VMs
    GET /rest/external/v1/base-snapshots  — snapshots on those base VMs
These are the images pool_push_image can apply.
"""

from __future__ import annotations

from vmware_policy import sanitize

from vmware_vdi.connection import HorizonClient
from vmware_vdi.ops._fetch import fetch_all

_BASE_VMS = "/external/v1/base-vms"
_BASE_SNAPS = "/external/v1/base-snapshots"


def _rows(client: HorizonClient, path: str, params: dict | None = None) -> list[dict]:
    return fetch_all(client, path, params)


def list_images(client: HorizonClient, *, base_vm_id: str | None = None) -> dict:
    """List instant-clone base VMs and their snapshots (the golden-image catalog).

    Optionally scope snapshots to one base_vm_id. Returns {base_vms, snapshots} with counts —
    the images available to pool_push_image.
    """
    base_vms = [
        {"id": b.get("id"), "name": sanitize(str(b.get("name") or ""), 200), "path": sanitize(str(b.get("path") or ""), 300)}
        for b in _rows(client, _BASE_VMS)
    ]
    snap_params = {"base_vm_id": base_vm_id} if base_vm_id else None
    snapshots = [
        {"id": s.get("id"), "name": sanitize(str(s.get("name") or ""), 200),
         "base_vm_id": s.get("base_vm_id"), "path": sanitize(str(s.get("path") or ""), 300)}
        for s in _rows(client, _BASE_SNAPS, snap_params)
    ]
    return {"base_vms": base_vms, "base_vm_count": len(base_vms),
            "snapshots": snapshots, "snapshot_count": len(snapshots)}
