# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""A deliberately read-only client for the VCF Operations Suite API.

Least privilege is enforced in code, not just in documentation:

* Only GET requests are allowed, plus POST to an explicit allowlist of endpoints
  that read (token acquire/release and query endpoints). Anything else raises
  ReadOnlyViolation before a request is sent.
* TLS verification is on by default. Plain HTTP is refused.
* Passwords and tokens are never logged; the token is released on exit.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit

import requests

from template_tool import __version__
from template_tool.compat import version_from_api
from template_tool.errors import (
    ApiError,
    AuthError,
    ConfigError,
    PermissionDenied,
    ReadOnlyViolation,
    TlsError,
)

log = logging.getLogger(__name__)

API_ROOT = "/suite-api/api"

# POST endpoints that do not change state. Extend deliberately, one path at a
# time, and only for endpoints that read. Paths are relative to API_ROOT.
READ_ONLY_POST_PATHS = frozenset(
    {
        "/auth/token/acquire",
        "/auth/token/release",
        "/resources/query",
        "/resources/stats/query",
    }
)

# The Suite API accepts this scheme on current releases. It is configurable so a
# future rename is a flag, not a code change.
DEFAULT_TOKEN_SCHEME = "vRealizeOpsToken"  # noqa: S105 - a header scheme name, not a secret


def normalise_host(host: str) -> str:
    """Accept 'ops.example.com' or 'https://ops.example.com[:port]'; refuse plain HTTP."""
    host = (host or "").strip()
    if not host:
        raise ConfigError("No VCF Operations host given (--host or VCFOPS_HOST).")
    if "://" not in host:
        host = f"https://{host}"
    parts = urlsplit(host.rstrip("/"))
    if parts.scheme != "https":
        raise ConfigError("Only HTTPS is supported. Credentials are never sent over plain HTTP.")
    if not parts.hostname:
        raise ConfigError(f"Cannot read a host name from {host!r}.")
    return f"https://{parts.netloc}"


class VcfOpsClient:
    """Use as a context manager so the session token is always released."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        auth_source: str = "local",
        verify: bool | str = True,
        timeout: float = 30.0,
        token_scheme: str = DEFAULT_TOKEN_SCHEME,
        session: requests.Session | None = None,
    ) -> None:
        if not username:
            raise ConfigError("No username given (--user or VCFOPS_USER).")
        if not password:
            raise ConfigError("No password given (VCFOPS_PASSWORD or the interactive prompt).")
        self.base_url = normalise_host(host)
        self._username = username
        self._password = password
        self._auth_source = auth_source
        self._timeout = timeout
        self._token_scheme = token_scheme
        self._token: str | None = None
        self._session = session or requests.Session()
        self._session.verify = verify
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": f"template-tool/{__version__}",
            }
        )

    # -- context management -------------------------------------------------

    def __enter__(self) -> VcfOpsClient:
        self.login()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.logout()

    # -- authentication -----------------------------------------------------

    def login(self) -> None:
        body = {
            "username": self._username,
            "password": self._password,
            "authSource": self._auth_source,
        }
        data = self._request("POST", "/auth/token/acquire", json=body, authenticated=False)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise AuthError("The token response did not contain a token.")
        self._token = token
        self._password = ""  # not needed again; do not keep it in memory longer than necessary
        log.debug("Session token acquired (value not logged).")

    def logout(self) -> None:
        if not self._token:
            return
        try:
            self._request("POST", "/auth/token/release")
            log.debug("Session token released.")
        except Exception as exc:  # noqa: BLE001 - best effort; never mask the real error
            log.debug("Token release failed: %s", type(exc).__name__)
        finally:
            self._token = None

    # -- read operations ----------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def query(self, path: str, body: dict[str, Any]) -> Any:
        """POST to a read-only query endpoint from READ_ONLY_POST_PATHS."""
        return self._request("POST", path, json=body)

    def product_version(self) -> tuple[int, int, int]:
        return version_from_api(self.get("/versions/current"))

    # -- transport ----------------------------------------------------------

    def _request(self, method: str, path: str, *, authenticated: bool = True, **kwargs: Any) -> Any:
        method = method.upper()
        if not path.startswith("/"):
            path = f"/{path}"
        if method != "GET" and not (method == "POST" and path in READ_ONLY_POST_PATHS):
            raise ReadOnlyViolation(f"Refusing {method} {path}: not on the read-only allowlist.")

        headers = {}
        if authenticated:
            if not self._token:
                raise AuthError("Not logged in.")
            headers["Authorization"] = f"{self._token_scheme} {self._token}"

        url = f"{self.base_url}{API_ROOT}{path}"
        log.debug("%s %s", method, path)
        try:
            response = self._session.request(method, url, headers=headers, timeout=self._timeout, **kwargs)
        except requests.exceptions.SSLError as exc:
            raise TlsError(f"TLS verification failed for {self.base_url}.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ApiError(
                f"Cannot reach {self.base_url}.",
                hint="Check DNS, routing, proxy settings (HTTPS_PROXY) and that port 443 is open.",
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ApiError(f"{method} {path} timed out after {self._timeout}s.") from exc

        status = response.status_code
        log.debug("%s %s -> HTTP %s", method, path, status)
        if status == 401:
            raise AuthError("VCF Operations rejected the credentials or the session token.")
        if status == 403:
            raise PermissionDenied(f"The service account may not call {method} {path}.")
        if status >= 400:
            raise ApiError(f"{method} {path} returned HTTP {status}.")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(f"{method} {path} did not return JSON.") from exc
