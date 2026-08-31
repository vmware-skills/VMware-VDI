## v1.0.6 — the test suite runs on a non-UTF-8 machine, and the guardrail tests with it


**The suite now runs on a cp936 machine.** Round 3 of the VCF 9 field testing ran
on Windows Server 2025 with locale cp936. Across the family four repos' suites --
1687 tests -- never executed at all, dying at collection reading our own UTF-8
sources, and 101 more failed the same way. Most of those were the tests that
verify the destructive-operation guardrails: the guardrails were fine, the tests
that check them could not open a file. On the UTF-8 CI every one of them was
green. A security test that cannot run is not a security test.

Every text read and write here names its encoding now, `tests/` included -- the
previous round fixed only the package, which is why this came back. A gate in
`family_smoke` scans both trees by AST, and the whole family's suites were re-run
under an ASCII locale to confirm: 15 of 15 green, from 1 of 15.

**`--help` no longer dies on a console that cannot encode it.** On any console
whose encoding cannot carry the characters in our own help text, `--help` exited
with a `UnicodeEncodeError` traceback -- unavailable exactly on the machines
where it is most needed. Four repos were affected; the handler is now relaxed in
all fifteen so a glyph degrades instead of killing the command.

**Its environment resolver no longer answers for other skills.**
`set_environment_resolver` wrote one process-global slot and twelve servers
registered into it at import time, so the last one won for all of them --
measured taking a `freeze-production-writes` rule from DENY to ALLOW on another
skill's production target. Registration is keyed by skill now (requires
vmware-policy 1.12.0).

**Unknown tool arguments are refused instead of dropped.** The schema declared
`additionalProperties: false` and the runtime accepted them anyway, so a filter
argument whose name a model guessed wrong returned the *unfiltered* result with
nothing to indicate anything had been discarded. Fixed in vmware-policy 1.12.0
and in force here.

Requires vmware-policy 1.12.0.

## v1.0.5 — the guard on the most destructive call was reading a field that does not exist

The guard on the family's most destructive operation was measuring nothing.
`pool_push_image` counts users in session before pushing an image to every
desktop in a pool, and it read `user_name` — a field the Horizon API does not
have. The real one is `user_id`. Every pool looked unoccupied, and all five
existing tests mocked the non-existent field.

Occupancy that cannot be determined is no longer reported as zero: it is
`unknown`, and an unknown occupancy refuses `confirm=True` rather than pushing
through it, with an explicit override that lands in the audit row.

Eight write tools also still turned a login 404 into "Pool not found, run
pool_list" — the circular advice the previous release removed from the read
path, alive on the write path.

**The `vmware-policy` floor moves to >=1.11.0.** Policy 1.11.0 stops the engine
failing open: on a host whose locale is not UTF-8, reading `rules.yaml` raised a
decode error that was swallowed, and a `freeze-production-writes` rule came back
ALLOW. No new API is used here, so the floor could have stayed — it is raised
because leaving it low means a user resolving 1.10.0 keeps the permissive engine
and the fix never reaches them. One behaviour travels with it: on a host whose
rules file cannot be read, operations move from all-allowed to all-denied.
`VMWARE_POLICY_DISABLED=1` is checked above the rules, so the escape hatch does
not itself depend on them loading.

Also in this release: the suite no longer appends to the operator's real
`~/.vmware/audit.db`. It held over 30,000 rows dominated by tool names nobody
had invoked, including 1,400 entries for a destructive operation that never
happened — an audit trail carrying test fiction cannot answer the question it is
kept for.

## v1.0.4 — the schema an agent reads now carries the descriptions

Parameter descriptions reach the JSON schema for the first time. An MCP client
sees the schema, not the docstring, and this repo's coverage of `description`
and `additionalProperties` was 0% — while nearly every parameter was already
described in an `Args:` block no client ever receives.

Measured on a real VCF 9.1 estate, the gap produced a silent failure with no
error at any stage: a parameter name guessed wrong is discarded and the tool
returns the full unfiltered result; a value guessed wrong (`power_state=
"running"`) returns 0 rows where there were 11.

vmware-policy 1.10.0's `describe_tool_parameters` copies what is already
written, so the docstring is now load-bearing and the two cannot drift apart. It
removes the `Args:` block from the description once copied — both travel in
every `tools/list` response, so leaving it bills the same sentences twice
against the manifest's token budget. `additionalProperties` is closed: an open
schema is room for a model to invent arguments that are then silently
discarded, which is the other half of the same failure.

**The `vmware-policy` floor moves to >=1.10.0.** Older releases have no
`describe_tool_parameters`, and resolving one gives an ImportError at server
start rather than a missing feature.


## v1.0.3 — two messages that sent you in a circle

Found against a real VCF 9.1 estate.

**A 404 on login was diagnosed as a bad object id.** The remedy printed was
"list the parent collection first (e.g. the pool_list / session_list /
machine_list tools) and copy an exact id". A login has no id, and `pool_list`
logs in first — it is the call that just failed. Following the advice
reproduced the error, one API call per lap. On `POST /rest/login` a 404 means
nothing answers at that path: wrong host or port, or a Connection Server that
predates the REST API entirely (it is Horizon 8; Horizon 7 has no `/rest`),
which is the most common real cause and is now what the message says. 405 gets
the same treatment, since a proxy that forwards the path but not the method
answers that.

**`doctor` reported "Config file missing" while reading the real config.** With
`VMWARE_VDI_CONFIG` naming a perfectly good file, the config check looked at the
default path, announced it was missing, and told the user to copy
`config.example.yaml` to `~/.vmware-vdi/` — in the same report that went on to
list the real file's three targets. Following that advice creates a second
config which is then ignored. The precedence now lives in one
`resolve_config_path` that every check uses.

Also: `server.json` never started the MCP server — it carried only the package
identifier, so a registry client composed `uvx vmware-vdi`, which runs the CLI
and exits.

Still beta in substance: the REST endpoints are verified against the official
Horizon Server API, but GET response field names and a few write bodies remain
defensive, pending a real Connection Server.

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