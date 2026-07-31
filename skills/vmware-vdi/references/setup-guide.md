# vmware-vdi — Setup Guide

> **Disclaimer**: Community-maintained open-source project, **not affiliated with, endorsed by, or
> sponsored by VMware, Inc., Broadcom Inc., or Omnissa, LLC.**

## 1. Install
```bash
uv tool install vmware-vdi
```

## 2. Connect (friendly wizard)
```bash
vmware-vdi init
```
Prompts for the **Connection Server host**, admin **username**, AD **domain** (blank for a local admin),
**password**, target name, and TLS verification. It writes `~/.vmware-vdi/config.yaml` +
`~/.vmware-vdi/.env` (chmod 600), tests `/rest/login`, and on success **discovers your pools/machines/
sessions** and prints the next commands to try. Re-run with `--force` to add another Connection Server
(existing targets are preserved; the default is repointed to the new one).

Manual config (`~/.vmware-vdi/config.yaml`):
```yaml
default_target: prod
targets:
  prod:
    host: horizon-cs1.example.com
    username: svc-vdi-ro          # a read-only Horizon role for read commands
    domain: ACME                  # AD domain; blank for a local Connection Server admin
    port: 443
    verify_ssl: true              # false only for a self-signed lab cert
```
Password (never in config.yaml): `~/.vmware-vdi/.env`
```
VMWARE_VDI_PROD_PASSWORD=b64:...    # written by `init`; or export it yourself (plaintext auto-obfuscated)
```

## 3. Verify
```bash
vmware-vdi doctor        # config / credentials / connectivity
```

## 4. Supported versions
- **Primary: VMware Horizon 8.x** (Connection Server REST API `/rest/v1`).
- **Latest Omnissa Horizon** (2406/2412+) — same `/rest/v1` lineage.
- Requires the Connection Server REST API enabled (Horizon 8.0+; audit-events since 2106).

## 5. MCP server
```json
{
  "mcpServers": {
    "vmware-vdi": {
      "command": "vmware-vdi",
      "args": ["mcp"],
      "env": { "VMWARE_VDI_CONFIG": "~/.vmware-vdi/config.yaml" }
    }
  }
}
```
Using the installed `vmware-vdi mcp` console script (not `uvx`) avoids a PyPI re-resolve on every launch —
important behind enterprise TLS proxies.

## Security
> **Disclaimer**: not affiliated with VMware/Broadcom/Omnissa.

- **Credentials**: password only in `~/.vmware-vdi/.env` (chmod 600, obfuscated `b64:` at rest —
  obfuscation, not encryption). For real secrecy, inject `VMWARE_VDI_<TARGET>_PASSWORD` from a secret
  manager (Vault / CyberArk / AWS SM / K8s Secret).
- **Authorization = RBAC**: the skill does not gate read vs write itself. Point a target at a **read-only
  Horizon admin role** and every write is refused at the Connection Server, un-bypassably.
- **TLS**: verification on by default; `verify_ssl: false` is per-target, for self-signed labs only.
- **Prompt-injection**: Connection-Server text is `sanitize()`d (truncated + control chars stripped).
- **Audit**: all writes recorded in `~/.vmware/audit.db` (SQLite WAL) via the shared `@vmware_tool` guard.
- **No outbound calls** other than to the configured Connection Server; no webhooks, no telemetry.
