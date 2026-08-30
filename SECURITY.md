# Security Policy

## Disclaimer
Community-maintained open-source project, **not affiliated with, endorsed by, or sponsored by VMware,
Inc., Broadcom Inc., or Omnissa, LLC.** "VMware", "Horizon", and "Omnissa" are trademarks of their
respective owners.

## Reporting Vulnerabilities
Please open a GitHub private security advisory at https://github.com/vmware-skills/VMware-VDI/security/advisories
or email the maintainer. Do not file public issues for security reports.

## Security Design

### Credential Management
- Passwords live only in `~/.vmware-vdi/.env` (chmod 600), obfuscated to `b64:` at rest (obfuscation, not
  encryption; defeats casual grep / shoulder-surfing). Config files hold host/username/domain only.
- Per-target env vars `VMWARE_VDI_<TARGET>_PASSWORD` can be injected from a secret manager.
- Username + password are resolved together on every call so a rotated credential never half-updates.

### Authorization — delegated to Horizon RBAC
The skill ships full read+write and does not gate read-vs-write itself. Point a target at a read-only
Horizon admin role and every write is refused at the Connection Server, un-bypassably — the one place the
control cannot be stepped around by a shell.

### Destructive-operation safety
`session_logoff`, `machine_reset`, `machine_remove`, `pool_set_enabled` (disable), `entitlement_remove`,
`pool_push_image`, and `task_cancel` preview their blast radius, require CLI double-confirmation, and
support `--dry-run`. `pool_push_image` (recreates every desktop in a pool) reports affected-desktop and
in-session counts before any confirm, and reports whether occupancy could be established at all: when
session rows cannot be attributed to a pool or farm the count is a lower bound, so the confirm is
refused rather than passed on an unverified zero. The override
(`--acknowledge-unknown-occupancy` / `acknowledge_unknown_occupancy=true`) is audited.

### SSL/TLS Verification
On by default. `verify_ssl: false` is per-target and intended only for self-signed lab certificates.

### Transitive Dependencies
Runtime deps: httpx, typer, rich, pyyaml, python-dotenv, mcp, and `vmware-policy` (the family's shared
audit/policy harness). No urllib3, no requests.

### Prompt Injection Protection
All Connection-Server-supplied text is passed through `vmware_policy.sanitize()` (truncation +
C0/C1 control-character stripping) before it reaches the model.

## Static Analysis
```bash
uvx bandit -r vmware_vdi/     # 0 issues at all severities as of v1.0.0
```

## Supported Versions
| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ (beta) |
