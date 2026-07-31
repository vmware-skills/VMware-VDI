"""Verified Horizon 8 Connection Server REST endpoints this skill may call.

Source of truth: developer.broadcom.com VMware Horizon Server API. Every path a
runtime ops call hits must be in ``ENDPOINTS`` — the regression tests exercise the
ops against a recording fake client and assert the recorded (method, path) is here,
so a path written from memory (踩坑 #36) fails CI instead of 404-ing in production.

Path templates use ``{id}`` for a single path parameter.
"""

# (method, path-template). Every entry verified against developer.broadcom.com
# (VMware Horizon Server API operation index) — see the comment on each group.
ENDPOINTS = {
    # auth
    ("POST", "/login"),
    ("POST", "/refresh"),
    ("POST", "/logout"),
    # sessions
    ("GET", "/inventory/v1/sessions"),
    ("GET", "/inventory/v1/sessions/{id}"),
    ("POST", "/inventory/v1/sessions/action/logoff"),
    ("POST", "/inventory/v1/sessions/action/disconnect"),
    ("POST", "/inventory/v1/sessions/action/send-message"),
    # machines
    ("GET", "/inventory/v1/machines"),
    ("GET", "/inventory/v1/machines/{id}"),
    ("DELETE", "/inventory/v1/machines/{id}"),
    ("POST", "/inventory/v1/machines/action/reset"),
    ("POST", "/inventory/v1/machines/action/enter-maintenance"),
    ("POST", "/inventory/v1/machines/action/exit-maintenance"),
    # desktop pools
    ("GET", "/inventory/v1/desktop-pools"),
    ("GET", "/inventory/v1/desktop-pools/{id}"),
    ("POST", "/inventory/v1/desktop-pools/action/enable"),
    ("POST", "/inventory/v1/desktop-pools/action/disable"),
    ("POST", "/inventory/v1/desktop-pools/{id}/action/apply-image"),
    # farms (read)
    ("GET", "/inventory/v1/farms"),
    ("GET", "/inventory/v1/farms/{id}"),
    # application pools (read)
    ("GET", "/inventory/v1/application-pools"),
    # base images (read)
    ("GET", "/external/v1/base-vms"),
    ("GET", "/external/v1/base-snapshots"),
    # AD users/groups (read — resolve SIDs for entitlement)
    ("GET", "/external/v1/ad-users-or-groups"),
    # entitlements (read + write)
    ("GET", "/entitlements/v1/desktop-pools/{id}"),
    ("POST", "/entitlements/v1/desktop-pools"),
    ("DELETE", "/entitlements/v1/desktop-pools"),
    # pool tasks (read + cancel) — image-push / long ops are pool-scoped
    ("GET", "/inventory/v1/desktop-pools/{id}/tasks"),
    ("GET", "/inventory/v1/desktop-pools/{id}/tasks/{id}"),
    ("POST", "/inventory/v1/desktop-pools/{id}/tasks/{id}/action/cancel"),
    # audit events
    ("GET", "/external/v1/audit-events"),
    # doctor connectivity probe
    ("GET", "/monitor/v1/connection-servers"),
}

# Collections whose ``/{value}`` segment (when not an action verb) is a path id.
_ID_PARENTS = frozenset(
    {"sessions", "machines", "desktop-pools", "farms", "application-pools", "ad-users-or-groups", "tasks"}
)


def normalize(path: str) -> str:
    """Collapse a concrete path's single id segment to ``{id}`` for template matching."""
    parts = path.split("/")
    out = []
    for i, p in enumerate(parts):
        if i > 0 and parts[i - 1] in _ID_PARENTS and p and p != "action":
            out.append("{id}")
        else:
            out.append(p)
    return "/".join(out)
