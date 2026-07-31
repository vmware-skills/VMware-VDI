"""Legacy JSON-Lines audit logging for vmware-vdi write operations.

The authoritative audit sink is ``~/.vmware/audit.db`` via vmware_policy (security
HLD §8); this legacy per-skill log is dual-written for back-compat and downgrades
to a stderr warning if it cannot be written (never blocks the operation).
"""

from __future__ import annotations

import getpass
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("vmware-vdi.audit")


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return os.environ.get("USER", "unknown")


class AuditLogger:
    """Appends one JSON-Lines audit entry per write to ``~/.vmware-vdi/audit.log``."""

    def __init__(self, log_file: str = "~/.vmware-vdi/audit.log") -> None:
        self._path = Path(log_file).expanduser()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass

    def log(
        self,
        *,
        target: str,
        operation: str,
        resource: str,
        skill: str = "vdi",
        parameters: dict[str, Any] | None = None,
        result: str = "",
        user: str | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "target": target,
            "operation": operation,
            "resource": resource,
            "skill": skill,
            "parameters": parameters or {},
            "result": result,
            "user": user or _current_user(),
        }
        try:
            existed = self._path.exists()
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if not existed:
                try:
                    os.chmod(self._path, 0o600)
                except OSError:
                    pass
        except OSError as exc:  # audit failure must not block the operation
            _log.warning("Audit write failed (operation still performed): %s", exc)
