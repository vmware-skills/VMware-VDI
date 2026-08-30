"""Horizon Connection Server REST client with token-based authentication.

Authenticates via ``POST /rest/login`` with ``{name, password, domain}`` and
receives an ``access_token`` (short-lived) plus a ``refresh_token``. Subsequent
requests carry ``Authorization: Bearer <access_token>``; a 401 triggers a single
``POST /rest/refresh`` (or full re-login if refresh fails), then the request is
re-issued through the top of the same loop so the retry rides the same
transport-error handling.

All HTTP errors are translated **centrally** here into :class:`VdiApiError`
carrying a teaching message (踩坑 #37) — the ops layer never calls
``raise_for_status()``.

Base URL pattern: https://<connection-server>/rest
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from vmware_vdi.config import AppConfig, TargetConfig, load_config

_log = logging.getLogger("vmware-vdi.connection")

# Transient gateway statuses worth one automatic retry. 4xx client errors are NOT retried.
_TRANSIENT_STATUS = frozenset({502, 503, 504})
_RETRY_DELAY_SEC = 2.0


class VdiApiError(Exception):
    """A Horizon REST call returned an error or failed to connect.

    Carries a teaching message (status + path + how to fix) so users see an
    actionable line, not a raw httpx traceback. ``status_code`` is None for
    transport/timeout failures (no HTTP response was received).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path


def _hint_for_status(status_code: int) -> str:
    """Short, actionable remediation hint for an HTTP error status (path-free — callers name the call)."""
    if status_code == 404:
        return (
            "Verify the id — list the parent collection first (e.g. the "
            "pool_list / session_list / machine_list tools) and copy an exact id."
        )
    if status_code == 400:
        return "Bad request — check the parameters/payload against the tool's parameter descriptions."
    if status_code in (401, 403):
        return (
            "Authentication/authorization failed — check username/domain in "
            "~/.vmware-vdi/config.yaml and VMWARE_VDI_<TARGET>_PASSWORD in "
            "~/.vmware-vdi/.env, plus the Horizon admin role assigned to the account "
            "(a read-only role refuses writes by design)."
        )
    if status_code == 409:
        return "Conflict — the resource is in a state that rejects this action (e.g. a pool mid-push)."
    if status_code == 503:
        return "The Connection Server is starting or a service is not ready — wait and retry."
    if status_code in (502, 504):
        return "The Connection Server is busy or a gateway timed out — retry shortly."
    if status_code >= 500:
        return "Server-side error — retry shortly; check Connection Server health."
    return "Check the request and try again."


def _is_tls_verify_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "certificate" in text or "ssl" in text or "verify" in text


def _transport_hint(exc: Exception) -> str:
    """Remedy for a connection/timeout failure — authored, never interpolating the exception text."""
    if _is_tls_verify_error(exc):
        return (
            "The certificate could not be verified — for a self-signed lab cert set "
            "`verify_ssl: false` for this target in ~/.vmware-vdi/config.yaml."
        )
    return (
        "Check 'host' and 'port' for this target in ~/.vmware-vdi/config.yaml and that "
        "the Connection Server is reachable from this machine."
    )


class HorizonClient:
    """REST client for a single Horizon Connection Server."""

    def __init__(self, target: TargetConfig, password: str, username: str | None = None) -> None:
        self._target = target
        self._base_url = f"https://{target.host}:{target.port}/rest"
        self._password = password
        self._username = username or target.username
        self._access_token: str | None = None
        self._refresh_token: str | None = None

        # httpx honours verify=False directly and emits no urllib3 InsecureRequestWarning,
        # so there is nothing to silence — importing urllib3 here (not a dependency) only
        # crashed every self-signed-cert target.
        self._client = httpx.Client(
            base_url=self._base_url,
            verify=target.verify_ssl,
            timeout=httpx.Timeout(30.0),
        )

    # --- auth ---------------------------------------------------------------

    def _login(self) -> None:
        """Acquire access + refresh tokens via POST /rest/login.

        Auth errors are translated to VdiApiError here (runs at connect time and
        on refresh-failure fallback), so a wrong password (401) or bad domain
        (400) never leaks a raw httpx traceback.
        """
        payload = {"name": self._username, "password": self._password, "domain": self._target.domain}
        attempt = 0
        while True:
            try:
                resp = self._client.post("/login", json=payload, headers={"Accept": "application/json"})
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in _TRANSIENT_STATUS and attempt < 1:
                    attempt += 1
                    time.sleep(_RETRY_DELAY_SEC)
                    continue
                if status in (404, 405):
                    # _hint_for_status is written for resource calls, where 404
                    # genuinely means "wrong id". Reached from here it told the
                    # user to run pool_list and copy an id — a login has no id,
                    # and pool_list logs in first, so it is the call that just
                    # failed. Following the advice reproduced the error
                    # (2026-08-30). On the login endpoint the same status means
                    # nothing answers at that path. Kept terse: the MCP layer
                    # renders exceptions through sanitize(str(exc), 300), and a
                    # longer message loses its own closing remedy.
                    hint = (
                        f"Nothing answers at {self._base_url}/login — not a "
                        f"credential problem. Check host and port in config.yaml, "
                        f"and that this is a Horizon 8 Connection Server (the "
                        f"/rest API does not exist on Horizon 7)."
                    )
                else:
                    hint = _hint_for_status(status)
                raise VdiApiError(
                    f"Horizon login failed (HTTP {status}). {hint}",
                    status_code=status,
                    method="POST",
                    path="/login",
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < 1:  # one transient retry, matching _request()
                    attempt += 1
                    time.sleep(_RETRY_DELAY_SEC)
                    continue
                raise VdiApiError(
                    f"Horizon login could not connect. {_transport_hint(exc)} "
                    f"Then run 'vmware-vdi doctor'. Configured host: {self._target.host}.",
                    method="POST",
                    path="/login",
                ) from exc
        data = resp.json() if resp.content else {}
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        if not self._access_token:
            raise VdiApiError(
                "Horizon login returned no access_token — verify the Connection Server version "
                "exposes the /rest API (Horizon 8.x).",
                method="POST",
                path="/login",
            )

    def _refresh(self) -> bool:
        """Try POST /rest/refresh; return True on success, False to fall back to full login."""
        if not self._refresh_token:
            return False
        try:
            resp = self._client.post("/refresh", json={"refresh_token": self._refresh_token})
            resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError):
            return False
        data = resp.json() if resp.content else {}
        token = data.get("access_token")
        if token:
            self._access_token = token
            return True
        return False

    def _reauth(self) -> None:
        """Refresh the access token, or full re-login if refresh is unavailable/expired."""
        if not self._refresh():
            self._login()

    def _headers(self) -> dict[str, str]:
        if self._access_token is None:
            self._login()
        return {"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"}

    # --- request ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retries: int = 1,
    ) -> httpx.Response:
        """Send one request, recovering from auth and transient failures.

        (1) transport/timeout and transient gateway statuses (502/503/504) retry
        once after a short delay; (2) a 401/403 triggers one token re-auth, then
        re-issues through the top of the loop so the retry is covered by the same
        transport-error handling; (3) any remaining error status is translated to
        a VdiApiError with a teaching message. 4xx client errors are NOT retried.
        """
        attempt = 0
        reauthed = False
        while True:
            try:
                resp = self._client.request(
                    method, path, headers=self._headers(), params=params, json=json_data
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < retries:
                    attempt += 1
                    time.sleep(_RETRY_DELAY_SEC)
                    continue
                raise VdiApiError(
                    f"Horizon request could not connect. {_transport_hint(exc)} "
                    f"Then run 'vmware-vdi doctor'. Configured host: {self._target.host}. "
                    f"Failing call: {method} {path}",
                    method=method,
                    path=path,
                ) from exc

            if resp.status_code in (401, 403) and not reauthed:
                _log.info("Auth error on %s %s, re-authenticating...", method, path)
                self._reauth()
                reauthed = True
                continue

            if resp.status_code in _TRANSIENT_STATUS and attempt < retries:
                attempt += 1
                time.sleep(_RETRY_DELAY_SEC)
                continue

            if resp.status_code >= 400:
                raise VdiApiError(
                    f"Horizon returned HTTP {resp.status_code}. {_hint_for_status(resp.status_code)} "
                    f"Run 'vmware-vdi doctor' if every call to this target fails. "
                    f"Failing call: {method} {path}",
                    status_code=resp.status_code,
                    method=method,
                    path=path,
                )
            return resp

    def get(self, path: str, params: dict[str, Any] | None = None, *, retries: int = 1) -> Any:
        """GET → parsed JSON (list or dict). Pass retries=0 for probes where an error status is the answer."""
        resp = self._request("GET", path, params=params, retries=retries)
        return resp.json() if resp.content else {}

    def post(self, path: str, json_data: dict[str, Any] | None = None, *, retries: int = 1) -> Any:
        resp = self._request("POST", path, json_data=json_data, retries=retries)
        return resp.json() if resp.content else {}

    def put(self, path: str, json_data: dict[str, Any] | None = None, *, retries: int = 1) -> Any:
        resp = self._request("PUT", path, json_data=json_data, retries=retries)
        return resp.json() if resp.content else {}

    def delete(self, path: str, json_data: dict[str, Any] | None = None, *, retries: int = 1) -> Any:
        resp = self._request("DELETE", path, json_data=json_data, retries=retries)
        return resp.json() if resp.content else {}

    def close(self) -> None:
        """Log out (best-effort) and close the HTTP connection pool."""
        if self._refresh_token:
            try:
                self._client.post("/logout", json={"refresh_token": self._refresh_token})
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError):
                pass
        self._client.close()


class ConnectionManager:
    """Manages connections to multiple Horizon Connection Server targets."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._clients: dict[str, HorizonClient] = {}

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> ConnectionManager:
        return cls(config or load_config())

    def connect(self, target_name: str | None = None) -> HorizonClient:
        """Get or create a HorizonClient for the named target (or the default)."""
        name = target_name or self._config.default_target
        if not name:
            configured = ", ".join(self._config.targets.keys())
            raise ValueError(
                f"No target specified and no default target configured. "
                f"Configured targets: {configured or '(none)'}. Pass target=<name>, "
                f"or set 'default_target' in ~/.vmware-vdi/config.yaml."
            )

        if name in self._clients:
            return self._clients[name]

        target_cfg = self._config.get_target(name)
        if target_cfg is None:
            available = ", ".join(self._config.targets.keys())
            raise ValueError(
                f"Target '{name}' not found. Available: {available or '(none)'}. "
                f"Add a '{name}' entry under 'targets:' in ~/.vmware-vdi/config.yaml."
            )

        # Resolve both halves of the credential together — a username left behind
        # by a rotation would pair with the new password and fail.
        password = target_cfg.get_password(name)
        username = target_cfg.get_username(name)
        client = HorizonClient(target_cfg, password, username)
        self._clients[name] = client
        return client

    def disconnect(self, target_name: str) -> None:
        if target_name in self._clients:
            self._clients[target_name].close()
            del self._clients[target_name]
