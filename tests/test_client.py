# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import requests

from template_tool.client import (
    READ_ONLY_POST_PATHS,
    VcfOpsClient,
    backoff_delay,
    normalise_host,
    retry_after_seconds,
)
from template_tool.errors import (
    ApiError,
    AuthError,
    ConfigError,
    PermissionDenied,
    ReadOnlyViolation,
    TlsError,
)

from .conftest import FakeResponse


def make(session, **kw):
    return VcfOpsClient("ops.rainpole.io", "svc-tool", "pw", session=session, **kw)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("ops.rainpole.io", "https://ops.rainpole.io"),
        ("https://ops.rainpole.io/", "https://ops.rainpole.io"),
        ("https://ops.rainpole.io:8443", "https://ops.rainpole.io:8443"),
    ],
)
def test_normalise_host(given, expected):
    assert normalise_host(given) == expected


@pytest.mark.parametrize("bad", ["", "http://ops.rainpole.io", "https://"])
def test_normalise_host_rejects(bad):
    with pytest.raises(ConfigError):
        normalise_host(bad)


def test_login_version_logout(ops_session):
    with make(ops_session) as client:
        assert client.product_version() == (9, 1, 1)
    methods = [(c["method"], c["url"].rsplit("/api", 1)[1]) for c in ops_session.calls]
    assert methods == [
        ("POST", "/auth/token/acquire"),
        ("GET", "/versions/current"),
        ("POST", "/auth/token/release"),
    ]
    acquire, version, release = ops_session.calls
    assert acquire["json"] == {"username": "svc-tool", "password": "pw", "authSource": "local"}
    assert "Authorization" not in acquire["headers"]
    assert version["headers"]["Authorization"] == "vRealizeOpsToken tkn-123"
    assert release["headers"]["Authorization"] == "vRealizeOpsToken tkn-123"


def test_password_is_dropped_after_login(ops_session):
    client = make(ops_session)
    client.login()
    assert client._password == ""


def test_token_scheme_is_configurable(ops_session):
    with make(ops_session, token_scheme="OpsToken") as client:
        client.get("/versions/current")
    assert ops_session.calls[1]["headers"]["Authorization"] == "OpsToken tkn-123"


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_state_changing_methods_never_leave_the_machine(ops_session, method):
    client = make(ops_session)
    client.login()
    sent = len(ops_session.calls)
    with pytest.raises(ReadOnlyViolation):
        client._request(method, "/resources/123")
    assert len(ops_session.calls) == sent


def test_post_outside_allowlist_is_refused(ops_session):
    client = make(ops_session)
    client.login()
    with pytest.raises(ReadOnlyViolation):
        client._request("POST", "/alertdefinitions")


def test_allowlist_contains_only_auth_and_query_paths():
    for path in READ_ONLY_POST_PATHS:
        assert path.startswith("/auth/token/") or path.endswith("/query"), path


def test_query_endpoint_allowed(ops_session):
    ops_session.routes[("POST", "/suite-api/api/resources/query")] = FakeResponse(200, {"resourceList": []})
    with make(ops_session) as client:
        assert client.query("/resources/query", {"resourceKind": ["VirtualMachine"]}) == {"resourceList": []}


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AuthError), (403, PermissionDenied), (500, ApiError)],
)
def test_http_errors_map_to_exit_codes(ops_session, status, error):
    ops_session.routes[("GET", "/suite-api/api/versions/current")] = FakeResponse(status, {})
    client = make(ops_session)
    client.login()
    with pytest.raises(error):
        client.product_version()


def test_tls_error_has_actionable_hint(ops_session):
    ops_session.error = requests.exceptions.SSLError("certificate verify failed")
    with pytest.raises(TlsError) as info:
        make(ops_session).login()
    assert "--ca-bundle" in info.value.hint


def test_connection_error(ops_session):
    ops_session.error = requests.exceptions.ConnectionError("refused")
    with pytest.raises(ApiError):
        make(ops_session).login()


def test_missing_token_in_response(ops_session):
    ops_session.routes[("POST", "/suite-api/api/auth/token/acquire")] = FakeResponse(200, {})
    with pytest.raises(AuthError):
        make(ops_session).login()


def test_logout_never_masks_the_original_error(ops_session):
    ops_session.routes[("POST", "/suite-api/api/auth/token/release")] = FakeResponse(500, {})
    ops_session.routes[("GET", "/suite-api/api/versions/current")] = FakeResponse(403, {})
    with pytest.raises(PermissionDenied), make(ops_session) as client:
        client.product_version()


def test_requires_credentials(ops_session):
    with pytest.raises(ConfigError):
        VcfOpsClient("ops.rainpole.io", "", "pw", session=ops_session)
    with pytest.raises(ConfigError):
        VcfOpsClient("ops.rainpole.io", "svc", "", session=ops_session)


def test_tls_verification_on_by_default(ops_session):
    make(ops_session)
    assert ops_session.verify is True


# -- retries and backoff -----------------------------------------------------

VERSION = "/suite-api/api/versions/current"
VERSION_OK = FakeResponse(200, {"major": 9, "minor": 1, "minorMinor": 1})


def retrying(session, max_retries=3):
    sleeps: list[float] = []
    client = make(session, max_retries=max_retries, sleep=sleeps.append)
    client.login()
    return client, sleeps


def test_busy_server_is_retried_with_backoff(ops_session):
    ops_session.routes[("GET", VERSION)] = [FakeResponse(503, {}), FakeResponse(502, {}), VERSION_OK]
    client, sleeps = retrying(ops_session)
    assert client.product_version() == (9, 1, 1)
    assert len(ops_session.calls_to(VERSION)) == 3
    assert len(sleeps) == 2
    assert 0.5 <= sleeps[0] <= 1.0
    assert 1.0 <= sleeps[1] <= 2.0


def test_retry_after_is_honoured(ops_session):
    ops_session.routes[("GET", VERSION)] = [FakeResponse(429, {}, {"Retry-After": "7"}), VERSION_OK]
    client, sleeps = retrying(ops_session)
    client.product_version()
    assert sleeps == [7.0]


def test_long_retry_after_gives_up_at_once(ops_session):
    ops_session.routes[("GET", VERSION)] = FakeResponse(503, {}, {"Retry-After": "900"})
    client, sleeps = retrying(ops_session)
    with pytest.raises(ApiError, match="wait 900s"):
        client.product_version()
    assert sleeps == []
    assert len(ops_session.calls_to(VERSION)) == 1


def test_retries_are_bounded(ops_session):
    ops_session.routes[("GET", VERSION)] = FakeResponse(503, {})
    client, sleeps = retrying(ops_session, max_retries=2)
    with pytest.raises(ApiError, match="after 3 attempts") as info:
        client.product_version()
    assert len(ops_session.calls_to(VERSION)) == 3
    assert len(sleeps) == 2
    assert "busy" in info.value.hint


def test_retries_can_be_turned_off(ops_session):
    ops_session.routes[("GET", VERSION)] = FakeResponse(503, {})
    client, sleeps = retrying(ops_session, max_retries=0)
    with pytest.raises(ApiError, match=r"HTTP 503\.$"):
        client.product_version()
    assert sleeps == []


def test_client_errors_are_not_retried(ops_session):
    ops_session.routes[("GET", VERSION)] = FakeResponse(404, {})
    client, sleeps = retrying(ops_session)
    with pytest.raises(ApiError):
        client.product_version()
    assert sleeps == []


def test_failed_connection_is_retried(ops_session):
    ops_session.routes[("GET", VERSION)] = [requests.exceptions.ConnectionError("reset"), VERSION_OK]
    client, sleeps = retrying(ops_session)
    assert client.product_version() == (9, 1, 1)
    assert len(sleeps) == 1


def test_connection_error_after_all_attempts(ops_session):
    ops_session.routes[("GET", VERSION)] = requests.exceptions.ConnectTimeout("no route")
    client, _ = retrying(ops_session, max_retries=1)
    with pytest.raises(ApiError, match="after 2 attempts"):
        client.product_version()


def test_read_timeout_is_not_retried(ops_session):
    ops_session.routes[("GET", VERSION)] = requests.exceptions.ReadTimeout("slow")
    client, sleeps = retrying(ops_session)
    with pytest.raises(ApiError, match="timed out") as info:
        client.product_version()
    assert sleeps == []
    assert "--timeout" in info.value.hint


def test_tls_failure_is_not_retried(ops_session):
    ops_session.routes[("GET", VERSION)] = requests.exceptions.SSLError("bad chain")
    client, sleeps = retrying(ops_session)
    with pytest.raises(TlsError):
        client.product_version()
    assert sleeps == []


def test_non_json_body(ops_session):
    class Html(FakeResponse):
        def json(self):
            raise ValueError("not json")

    ops_session.routes[("GET", VERSION)] = Html(200, "<html>")
    client, _ = retrying(ops_session)
    with pytest.raises(ApiError, match="did not return JSON"):
        client.product_version()


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("", None), ("5", 5.0), (" 2.5 ", 2.5), ("-3", 0.0), ("soon", None)],
)
def test_retry_after_seconds(header, expected):
    assert retry_after_seconds(header) == expected


def test_retry_after_http_date():
    now = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    later = (now + timedelta(seconds=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert retry_after_seconds(later, now=now) == 30.0
    assert retry_after_seconds("Mon, 02 Nov 2026 11:00:00", now=now) == 0.0


def test_backoff_is_capped():
    assert all(0.5 <= backoff_delay(0) <= 1.0 for _ in range(50))
    assert all(15.0 <= backoff_delay(10) <= 30.0 for _ in range(50))


# -- paging ------------------------------------------------------------------

RESOURCES = "/suite-api/api/resources"


def resource_page(names, total):
    return FakeResponse(
        200,
        {
            "pageInfo": {"totalCount": total, "page": 0, "pageSize": len(names)},
            "resourceList": [{"identifier": n, "resourceKey": {"name": n}} for n in names],
        },
    )


def test_pages_until_total_count(ops_session):
    ops_session.routes[("GET", RESOURCES)] = [resource_page(["a", "b"], 3), resource_page(["c"], 3)]
    with make(ops_session) as client:
        pages = list(
            client.pages("/resources", "resourceList", {"resourceKind": ["VirtualMachine"]}, page_size=2)
        )
    assert [len(p.items) for p in pages] == [2, 1]
    sent = [c["params"] for c in ops_session.calls_to(RESOURCES)]
    assert sent == [
        {"resourceKind": ["VirtualMachine"], "page": 0, "pageSize": 2},
        {"resourceKind": ["VirtualMachine"], "page": 1, "pageSize": 2},
    ]


def test_short_page_is_not_the_end_when_total_says_otherwise(ops_session):
    # The server capped pageSize at 2 although 5 was asked for.
    ops_session.routes[("GET", RESOURCES)] = [resource_page(["a", "b"], 3), resource_page(["c"], 3)]
    with make(ops_session) as client:
        items = [i for p in client.pages("/resources", "resourceList", page_size=5) for i in p.items]
    assert len(items) == 3


def test_without_total_paging_stops_at_an_empty_page(ops_session):
    ops_session.routes[("GET", RESOURCES)] = [
        FakeResponse(200, {"resourceList": [{"identifier": "a"}]}),
        FakeResponse(200, {"resourceList": []}),
    ]
    with make(ops_session) as client:
        pages = list(client.pages("/resources", "resourceList"))
    assert [p.total for p in pages] == [None, None]
    assert len(ops_session.calls_to(RESOURCES)) == 2


def test_paging_has_an_upper_bound(ops_session, monkeypatch):
    monkeypatch.setattr("template_tool.client.MAX_PAGES", 3)
    ops_session.routes[("GET", RESOURCES)] = FakeResponse(200, {"resourceList": [{"identifier": "same"}]})
    with make(ops_session) as client, pytest.raises(ApiError, match="more than 3 pages"):
        list(client.pages("/resources", "resourceList"))


@pytest.mark.parametrize("verify", [True, False, "/etc/ssl/ops-ca.pem"])
def test_verify_is_sent_with_every_request(ops_session, verify):
    with make(ops_session, verify=verify) as client:
        client.product_version()
    assert [c["verify"] for c in ops_session.calls] == [verify] * 3


def test_ca_bundle_beats_requests_ca_bundle_environment(monkeypatch):
    """Regression: REQUESTS_CA_BUNDLE must not override an explicit --ca-bundle."""
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/etc/ssl/corporate.pem")
    session = requests.Session()
    merged = session.merge_environment_settings(
        "https://ops.rainpole.io", {}, None, "/etc/ssl/ops-ca.pem", None
    )
    assert merged["verify"] == "/etc/ssl/ops-ca.pem"
    merged = session.merge_environment_settings("https://ops.rainpole.io", {}, None, True, None)
    assert merged["verify"] == "/etc/ssl/corporate.pem"
