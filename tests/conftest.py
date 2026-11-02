# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""A fake requests.Session so tests never touch the network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakeResponse:
    status_code: int = 200
    payload: Any = None

    @property
    def content(self) -> bytes:
        return b"" if self.payload is None else json.dumps(self.payload).encode()

    def json(self) -> Any:
        if self.payload is None:
            raise ValueError("no body")
        return self.payload


@dataclass
class FakeSession:
    """Routes (METHOD, path-suffix) to canned responses and records every call."""

    routes: dict[tuple[str, str], FakeResponse] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    verify: Any = True
    error: Exception | None = None

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error:
            raise self.error
        for (m, suffix), response in self.routes.items():
            if m == method and url.endswith(suffix):
                return response
        return FakeResponse(404, {"message": "not found"})


@pytest.fixture
def ops_session() -> FakeSession:
    return FakeSession(
        routes={
            ("POST", "/suite-api/api/auth/token/acquire"): FakeResponse(200, {"token": "tkn-123"}),
            ("POST", "/suite-api/api/auth/token/release"): FakeResponse(200, None),
            ("GET", "/suite-api/api/versions/current"): FakeResponse(
                200, {"releaseName": "VCF Operations 9.1.1", "major": 9, "minor": 1, "minorMinor": 1}
            ),
        }
    )
