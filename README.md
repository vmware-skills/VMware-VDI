<!-- mcp-name: io.github.zw008/vmware-vdi -->

# VMware VDI (Horizon)

**AI-powered intelligent operations for VMware / Omnissa Horizon VDI** — manage desktop pools, RDS farms,
published apps, **user sessions**, desktop machines, entitlements, instant-clone images, and Horizon
events/health/statistics through the **Horizon 8 Connection Server REST API**. Ships as both an **MCP
server** (for AI agents) and a **CLI** (for help-desk and scripting). Part of the
[VMware skill family](#companion-skills).

> **Disclaimer**: Community-maintained open-source project, **not affiliated with, endorsed by, or
> sponsored by VMware, Inc., Broadcom Inc., or Omnissa, LLC.** "VMware", "Horizon", and "Omnissa" are
> trademarks of their respective owners. Source is publicly auditable under the MIT license.

> **Status: v1.0.0 (beta).** REST endpoints are verified against the official Horizon Server API;
> GET-response field projections are defensive and pending validation against a live Connection Server
> (a field-name mismatch yields empty results, not a crash — see the [beta note](#beta-note)).

## Why vmware-vdi

Every other VMware family skill stops at the vСenter VM. **A Horizon desktop pool sits *on* those VMs** —
so `vmware-aiops` can reset the backing VM, but it cannot see a *user session*, log a user off, disable a
*pool*, or push a golden image. `vmware-vdi` fills exactly that day-2 VDI gap — "who is stuck on a broken
desktop", "log this user off so their profile unlocks", "why is this pool not provisioning", "push the
patched image to Finance tonight" — with the family's **governed-ops harness**: every write is audited,
previews its blast radius, and is authorized by the Horizon account's own RBAC role.

## Capabilities — 27 MCP tools (16 read / 11 write)

| Category | Tools |
|----------|-------|
| **Monitoring** | health summary · session list/get · machine list/get · event list |
| **Statistics** | session concurrency stats · per-pool utilization |
| **Management** | pool list/get · farm list · app-pool list · entitlement list · image list · AD search · pool enable/disable · entitlement add/remove |
| **Ops actions** | session logoff / disconnect / message · machine reset / maintenance / remove |
| **Tasks** | task status · **image push** · task cancel |

Reads are strictly non-destructive. Writes **preview their blast radius**, double-confirm at the CLI, and
are audit-logged to `~/.vmware/audit.db`. `pool_push_image` recreates *every desktop in a pool* — the
highest single-call blast radius in the family — and its preview states affected-desktop and
in-session-user counts before any confirm.

## Quick start

```bash
uv tool install vmware-vdi
vmware-vdi init      # friendly wizard: connect to a Connection Server + discover your pools
vmware-vdi doctor    # verify config / credentials / connectivity
vmware-vdi health    # one-glance VDI health
```

`vmware-vdi init` prompts for the Connection Server host, admin username, AD domain, and password; writes
`~/.vmware-vdi/config.yaml` + a `0600` `.env` (password obfuscated); tests the login; and on success
**discovers your pools, machines, and sessions** with the next commands to try.

## Example workflows

**Help-desk — a user's desktop is stuck**
```bash
vmware-vdi session list --user alice
vmware-vdi machine list --state AGENT_UNREACHABLE
vmware-vdi session logoff --user alice --dry-run   # preview which sessions
vmware-vdi session logoff --user alice             # double-confirm, then logs off + audits
```

**Patch night — push a new golden image**
```bash
vmware-vdi image list
vmware-vdi pool push-image --id pool-fin --dry-run  # BLAST RADIUS: N desktops, M logged-in users
vmware-vdi pool push-image --id pool-fin            # double-confirm; returns a task
vmware-vdi task status --pool pool-fin              # track progress
```

## MCP server

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

## Supported versions

- **VMware Horizon 8.x** (primary) — Connection Server REST API `/rest/v1`.
- **Latest Omnissa Horizon** (2406 / 2412+) — same `/rest/v1` lineage.

## Security

- **Authorization = Horizon RBAC.** The skill does not gate read vs write; point a target at a **read-only
  Horizon admin role** and every write is refused at the Connection Server, un-bypassably.
- **Credentials** live only in `~/.vmware-vdi/.env` (`0600`, obfuscated `b64:` at rest); config files hold
  host/username/domain only. Inject `VMWARE_VDI_<TARGET>_PASSWORD` from a secret manager for real secrecy.
- **TLS** verification on by default. All Connection-Server text is `sanitize()`d against prompt injection.
- **No outbound calls** except to the configured Connection Server — no webhooks, no telemetry.

See [`SECURITY.md`](SECURITY.md) and `skills/vmware-vdi/references/setup-guide.md`.

## Beta note

REST **endpoints** are verified against the official Horizon Server API operation index. GET-response
**field names** (and a few write bodies) are defensive (`.get()` with fallbacks) and **pending validation
against a live Connection Server**. On a field-name mismatch a list reads empty rather than crashing.
First real-Horizon use should run `vmware-vdi init` and confirm the session/machine/pool projections;
please [file an issue](https://github.com/zw008/VMware-VDI/issues) with raw `*_get` output if a projection
looks empty. Quality: 32 regression tests, ruff clean, bandit 0, tool endpoints pinned to a verified spec.

## Companion skills

Part of the VMware skill family — install the modules you need:

- **[vmware-aiops](https://github.com/zw008/VMware-AIops)** — the vCenter VMs backing the desktops (power, snapshot, clone, migrate)
- **[vmware-monitor](https://github.com/zw008/VMware-Monitor)** — read-only vSphere monitoring
- **[vmware-nsx-security](https://github.com/zw008/VMware-NSX-Security)** — desktop network microsegmentation
- **[vmware-aria](https://github.com/zw008/VMware-Aria)** · **[vmware-nsx](https://github.com/zw008/VMware-NSX)** · **[vmware-storage](https://github.com/zw008/VMware-Storage)** · **[vmware-vks](https://github.com/zw008/VMware-VKS)** · **[vmware-avi](https://github.com/zw008/VMware-AVI)** · **[vmware-harden](https://github.com/zw008/VMware-Harden)**

## License

MIT — see [LICENSE](LICENSE).
