## v1.0.2 — two wrong numbers: the server's own version, and the advertised tool count

Both defects were invisible to the test suites and both were user-facing.

- **The MCP server reported the SDK's version as its own.** `FastMCP` accepts no
  `version` argument and leaves the lowlevel server's at `None`; with it `None`
  the SDK answers `initialize` with its OWN version. Every skill in the family
  therefore told its client it was mcp 1.29.1 — a number that exists for no
  package here, and one that would change with an SDK bump and no code change of
  ours. Verified end to end rather than by reading: unset the field and a probe
  server reports the installed SDK's version; set it and it reports ours.

Also new: this repo is installable as a Claude Code plugin
(`/plugin install vmware-vdi@vmware-skills`). The skill and its MCP server arrive in
one step; nothing is duplicated, the manifest points at the existing `skills/`
tree. family_smoke gained three gates — the server's reported version, the plugin
manifest's agreement with pyproject, and the advertised tool count against the
live registration.

## v1.0.1 — moved to vmware-skills org + MCP Registry namespace io.github.vmware-skills/vmware-vdi

Repo transferred from github.com/zw008 to github.com/vmware-skills (redirects preserve old links).
MCP Registry server renamed to `io.github.vmware-skills/*`; the old `io.github.zw008/*` entry is deprecated.
All in-repo links updated. No functional code change on this line beyond the org move.

## v1.0.0 (beta) — first release

The family's 14th skill: **vmware-vdi** — VMware/Omnissa Horizon VDI intelligent operations through the
Horizon 8 Connection Server REST API. Independent version line (not aligned to the family's 1.8.x).

**27 MCP tools (16 read / 11 write)** + full CLI parity, across monitoring / statistics / management /
ops-actions / tasks:
- **Sessions** — list/get, logoff, disconnect, send-message (help-desk core).
- **Machines** — list/get, reset, enter/exit maintenance, remove.
- **Pools** — list/get, enable/disable, **push-image** (recreates every desktop; highest blast radius in
  the family — preview states affected-desktop + in-session-user counts).
- **Monitoring & statistics** — one-glance health, session stats, pool utilization, audit events.
- **Catalog & access** — farms, application pools, instant-clone images, AD search, entitlement
  list/add/remove.
- **Tasks** — pool-scoped task status + cancel (image push / provisioning).

**Governance (family harness)**: every write goes through `@vmware_tool`/`@guarded` → `~/.vmware/audit.db`;
destructive CLI writes double-confirm + `--dry-run`; Connection-Server text is `sanitize()`d; authorization
is delegated to the Horizon admin role (a read-only role refuses writes at the server, un-bypassably).

**Friendly onboarding**: `vmware-vdi init` connects to a Connection Server and discovers your pools,
machines, and sessions with next-step hints.

**Supported**: Horizon 8.x (primary) and the latest Omnissa Horizon (2406/2412+); same `/rest/v1` API.

### Beta caveat (please read)
REST **endpoints** are verified against the official Horizon Server API operation index. GET-response
**field names** and a few write bodies are defensive (`.get()` with fallbacks) and **pending validation
against a live Connection Server** — on a field-name mismatch a list reads empty rather than crashing.
First production use should run `vmware-vdi init` on a real Horizon 8 and confirm the session/machine/pool
projections and the apply-image / entitlement bodies; please file an issue with raw `*_get` output if a
projection looks empty. Quality: 32 regression tests, ruff clean, bandit 0 issues, tool endpoints pinned
to a verified spec set.