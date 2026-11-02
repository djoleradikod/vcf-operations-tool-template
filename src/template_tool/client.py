# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""A deliberately read-only client for the VCF Operations Suite API.

Least privilege is enforced in code, not just in documentation:

* Only GET requests are allowed, plus POST to an explicit allowlist of endpoints
  that read (token acquire/release and query endpoints). Anything else raises
  ReadOnlyViolation before a request is sent.
* TLS verification is on by default. Plain HTTP is refused.
* Passwords and tokens are never logged; the token is released on exit.

The client is also careful with the server. Requests are sequential. Overload
responses (429, 502, 503, 504) and failed connections are retried a bounded
number of times with exponential backoff and jitter, and a Retry-After header
from the server is honoured. A read timeout is not retried, because repeating a
slow query adds load to a cluster that is already struggling.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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

# Responses that mean "busy, try again shortly". Every call this client can make
# is read-only, so repeating one is safe.
RETRY_STATUSES = frozenset({429, 502, 503, 504})
BACKOFF_BASE = 1.0  # seconds before the first retry; doubles on each attempt
BACKOFF_CAP = 30.0  # longest wait between two attempts
RETRY_AFTER_LIMIT = 120.0  # if the server asks for a longer pause, stop and say so
MAX_PAGES = 10_000  # guard against a server that ignores the page parameter


@dataclass(frozen=True)
class Page:
    """One page of a paged Suite API list."""

    number: int
    items: list[dict[str, Any]]
    total: int | None


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    """Parse a Retry-After header: either delay-seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (when - now).total_seconds())


def backoff_delay(attempt: int, base: float = BACKOFF_BASE, cap: float = BACKOFF_CAP) -> float:
    """Exponential backoff with jitter: between half and all of min(cap, base * 2**attempt)."""
    ceiling = min(cap, base * (2**attempt))
    return ceiling * (0.5 + random.random() / 2)  # noqa: S311 - jitter, not cryptography


def normalise_host(host: str) -> str:
    """Accept 'ops.example.com' or 'https://ops.example.com[:port]'; refuse plain HTTP."""
    host = (host or "").strip()
    if not host:
        raise ConfigError("No VCF Operations host given (--host, VCFOPS_HOST or a profile).")
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
        max_retries: int = 3,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not username:
            raise ConfigError("No username given (--user, VCFOPS_USER or a profile).")
        if not password:
            raise ConfigError("No password given (VCFOPS_PASSWORD or the interactive prompt).")
        self.base_url = normalise_host(host)
        self._username = username
        self._password = password
        self._auth_source = auth_source
        self._timeout = timeout
        self._token_scheme = token_scheme
        self._max_retries = max(0, max_retries)
        self._sleep = sleep
        self._token: str | None = None
        # verify is passed on every request, not only set on the session: requests
        # lets REQUESTS_CA_BUNDLE and CURL_CA_BUNDLE override Session.verify
        # (psf/requests#3829), which would silently ignore --ca-bundle on machines
        # that set those variables. A per-request value of True still honours them.
        self._verify = verify
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

    def pages(
        self,
        path: str,
        list_key: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 500,
    ) -> Iterator[Page]:
        """Walk a paged GET endpoint such as /resources or /alerts, one page at a time.

        Paging stops at pageInfo.totalCount. If the server does not report a total,
        it stops at the first empty page. A short page is not treated as the end,
        because the server may cap pageSize below the value requested, and stopping
        there would silently truncate the result.
        """
        seen = 0
        for number in range(MAX_PAGES):
            data = self.get(path, {**(params or {}), "page": number, "pageSize": page_size})
            data = data if isinstance(data, dict) else {}
            items = data.get(list_key) or []
            total = (data.get("pageInfo") or {}).get("totalCount")
            total = int(total) if total is not None else None
            yield Page(number, items, total)
            seen += len(items)
            if not items or (total is not None and seen >= total):
                return
        raise ApiError(f"GET {path} returned more than {MAX_PAGES} pages; stopping.")

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
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            last = attempt == attempts - 1
            log.debug("%s %s", method, path)
            try:
                response = self._session.request(
                    method, url, headers=headers, timeout=self._timeout, verify=self._verify, **kwargs
                )
            except requests.exceptions.SSLError as exc:
                raise TlsError(f"TLS verification failed for {self.base_url}.") from exc
            except requests.exceptions.ConnectionError as exc:
                # Includes ConnectTimeout: nothing reached the server, so retrying is cheap.
                if last:
                    raise ApiError(
                        f"Cannot reach {self.base_url}"
                        + (f" after {attempts} attempts." if attempts > 1 else "."),
                        hint="Check DNS, routing, proxy settings (HTTPS_PROXY) and that port 443 is open.",
                    ) from exc
                self._wait(attempt, None, f"{method} {path} could not connect")
                continue
            except requests.exceptions.Timeout as exc:
                raise ApiError(
                    f"{method} {path} timed out after {self._timeout:g}s.",
                    hint="Raise --timeout, or reduce the page size so each request does less work.",
                ) from exc

            status = response.status_code
            log.debug("%s %s -> HTTP %s", method, path, status)
            if status in RETRY_STATUSES:
                headers_in = getattr(response, "headers", None) or {}
                wait = retry_after_seconds(headers_in.get("Retry-After"))
                if wait is not None and wait > RETRY_AFTER_LIMIT:
                    raise ApiError(
                        f"{method} {path} returned HTTP {status}; the server asked clients to wait "
                        f"{wait:.0f}s.",
                        hint="VCF Operations is shedding load. Try again later.",
                    )
                if not last:
                    self._wait(attempt, wait, f"{method} {path} returned HTTP {status}")
                    continue
                raise ApiError(
                    f"{method} {path} returned HTTP {status}"
                    + (f" after {attempts} attempts." if attempts > 1 else "."),
                    hint="VCF Operations is busy, starting or degraded. Check the cluster status, then retry.",
                )
            return self._decode(method, path, response)
        raise AssertionError("unreachable")  # pragma: no cover

    def _wait(self, attempt: int, retry_after: float | None, reason: str) -> None:
        delay = retry_after if retry_after is not None else backoff_delay(attempt)
        log.warning(
            "%s; retrying in %.1fs (attempt %d of %d).",
            reason,
            delay,
            attempt + 2,
            self._max_retries + 1,
        )
        self._sleep(delay)

    @staticmethod
    def _decode(method: str, path: str, response: Any) -> Any:
        status = response.status_code
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
