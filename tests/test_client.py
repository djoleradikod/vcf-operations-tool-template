# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
import requests

from template_tool.client import READ_ONLY_POST_PATHS, VcfOpsClient, normalise_host
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
