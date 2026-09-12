"""Session-wide sandbox: the suite must not touch the operator's real files.

Installed at *import* time, not in a fixture. ``vmware_vdi.cli`` and
``vmware_vdi.mcp_server.server`` each build an ``AuditLogger()`` at module
scope. That constructor resolves ``~/.vmware-vdi/audit.log`` and holds it
on the instance; the directory is created lazily on the first write, but the
path is already decided. A fixture — even a session-scoped autouse one — runs
after collection has imported every test module and, with them, those modules.
By the time a fixture could redirect ``HOME``, the path is fixed.

Two variables, because the skill writes two audit trails:

* ``OPS_HOME`` moves ``vmware_policy``'s shared ``audit.db`` (and the policy,
  budget and undo state beside it). ``vmware_policy.paths.ops_home()`` reads it
  on every call and defaults to ``~/.vmware``.
* ``HOME`` moves ``~/.vmware-vdi/audit.log``, the per-skill JSON Lines log,
  whose default path is a ``~``-relative string and so ignores ``OPS_HOME``.

This repo got the sandbox late (2026-09-11). The first test here to run a
CLI write through ``@guarded`` — the deny-rule test in
``test_cli_writes_guarded.py`` — wrote a ``session_logoff denied`` row into the
operator's real ``~/.vmware/audit.db`` on every run: 14 rows in one day, from
the author's runs and from review runs, before anyone noticed. The other
suites in this family had the sandbox; this one had never needed it, which is
not the same as being protected.

See ``tests/eval/regression/test_audit_isolation.py``, which asserts this
sandbox is in place so a future test cannot quietly do without it.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

from vmware_policy.audit import reset_engine

# The operator's real home, captured before the redirect. The regression test
# expresses "not the real audit database" against this.
REAL_HOME = Path(os.path.expanduser("~"))

SANDBOX_HOME = Path(tempfile.mkdtemp(prefix="vmware-vdi-tests-"))

os.environ["HOME"] = str(SANDBOX_HOME)
os.environ["OPS_HOME"] = str(SANDBOX_HOME / ".vmware")
# expanduser() consults USERPROFILE on Windows and, on POSIX, falls back to the
# password database when HOME is unset; keep every spelling pointing here so the
# sandbox holds on the family's Windows test host too.
os.environ["USERPROFILE"] = str(SANDBOX_HOME)

# vmware_policy's audit engine is a lazily built singleton keyed to the path it
# first resolved. Nothing should have built one this early, but a stale binding
# would silently send every write back to the real file, so clear it. Imported
# unguarded on purpose: vmware_policy is a hard dependency of this skill, and a
# swallowed ImportError here would leave the sandbox half-installed and quiet.
reset_engine()

atexit.register(shutil.rmtree, SANDBOX_HOME, True)
