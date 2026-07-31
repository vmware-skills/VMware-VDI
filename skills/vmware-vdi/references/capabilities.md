# vmware-vdi — Capabilities

27 MCP tools (16 read / 11 write) over the Horizon 8 Connection Server REST API. Every tool accepts an
optional `target`. Typical response tokens are estimates for a small estate; lists paginate at 50.

## Monitoring (6 read)
| Tool | R/W | Returns | ~tokens |
|------|:---:|---------|:------:|
| `health_summary` | R | session totals by state, problem-machine count, pool enabled/disabled | 80–200 |
| `session_list` | R | id, user, type, state, protocol, pool_id, machine_id, start_time (filter user/pool/state) | 60–500 |
| `session_get` | R | one session's projection | 40–100 |
| `machine_list` | R | id, name, pool_id, state, user, agent_version, base_image (filter pool/state) | 60–500 |
| `machine_get` | R | one machine's projection | 40–100 |
| `event_list` | R | time, severity, type, module, user, machine, message (filter severity) | 100–600 |

## Statistics (2 read)
| Tool | R/W | Returns | ~tokens |
|------|:---:|---------|:------:|
| `session_stats` | R | current concurrent, by-state, by-protocol, top pools | 80–200 |
| `pool_utilization` | R | per-pool total/available/in-use/error + utilization % | 80–300 |

## Management (7 read / 2 write)
| Tool | R/W | Notes | ~tokens |
|------|:---:|-------|:------:|
| `pool_list` / `pool_get` | R | pools: type, enabled, assignment | 60–300 |
| `farm_list` | R | RDS farms: type, enabled, server count | 40–200 |
| `app_pool_list` | R | published apps: farm, enabled, executable | 40–300 |
| `entitlement_list` | R | AD principals entitled to a pool | 40–300 |
| `image_list` | R | instant-clone base VMs + snapshots | 60–400 |
| `ad_user_search` | R | resolve AD name → SID (for `entitlement_add`) | 40–200 |
| `pool_set_enabled` | W | enable/disable pool (idempotent, preview) | 40–120 |
| `entitlement_add` / `entitlement_remove` | W | grant/revoke pool access by SID (preview) | 40–120 |

## Ops actions (6 write) — help-desk
| Tool | R/W | Risk | Blast radius |
|------|:---:|:----:|--------------|
| `session_send_message` | W | low | informational, no disruption |
| `session_disconnect` | W | medium | one session, state preserved |
| `session_logoff` | W | high | kicks the user (profile write-back) |
| `machine_maintenance` | W | medium | drains a machine (no new sessions) |
| `machine_reset` | W | high | hard reset — user loses unsaved state |
| `machine_remove` | W | high | removes from pool; deletes VM for instant clones |

## Tasks (1 read / 2 write)
| Tool | R/W | Notes |
|------|:---:|-------|
| `task_status` | R | pool-scoped task status/progress (or all tasks for the pool) |
| `pool_push_image` | W | **critical** — apply pending image; recreates EVERY desktop; preview states affected desktops + in-session users |
| `task_cancel` | W | cancel a running pool task (applied work is not rolled back) |

**Beta note (踩坑 #36)**: REST endpoints are verified against the official Horizon Server API operation
index. GET-response *field names* are defensive (`.get()` with fallbacks) and pending validation against a
live Connection Server — a mismatch yields empty results, not a crash. First real-Horizon use should
confirm the `session`/`machine`/`pool` projections and the `apply-image` / entitlement bodies.
