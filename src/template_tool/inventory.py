# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""The `inventory` command's logic: list objects with their kind, adapter and health.

This module is the worked example of where tool logic lives. The client knows
how to talk to the Suite API; this module knows which calls to make and what a
row of output contains; cli.py wires arguments to it; output.py formats it.
Replace or extend it with the logic of your own tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from template_tool.client import VcfOpsClient

COLUMNS = (
    ("name", "Name"),
    ("resourceKind", "Kind"),
    ("adapterKind", "Adapter"),
    ("health", "Health"),
    ("identifier", "ID"),
)


@dataclass(frozen=True)
class Filters:
    """Filters passed to GET /resources. Empty values are not sent."""

    adapter_kind: str | None = None
    resource_kinds: tuple[str, ...] = ()
    name: str | None = None

    def params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.adapter_kind:
            params["adapterKind"] = self.adapter_kind
        if self.resource_kinds:
            params["resourceKind"] = list(self.resource_kinds)
        if self.name:
            params["name"] = self.name
        return params


@dataclass
class Inventory:
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int | None = None  # what the server reported; may exceed len(rows) when --limit is used

    @property
    def truncated(self) -> bool:
        return self.total is not None and self.total > len(self.rows)


def to_row(resource: dict[str, Any]) -> dict[str, Any]:
    """Flatten one ResourceDto into the columns above. Missing fields become empty strings."""
    key = resource.get("resourceKey") or {}
    return {
        "name": key.get("name", ""),
        "resourceKind": key.get("resourceKindKey", ""),
        "adapterKind": key.get("adapterKindKey", ""),
        "health": resource.get("resourceHealth", ""),
        "identifier": resource.get("identifier", ""),
    }


def collect(
    client: VcfOpsClient,
    filters: Filters,
    *,
    page_size: int = 500,
    limit: int | None = None,
) -> Inventory:
    """Read matching objects page by page, stopping early once `limit` rows are collected."""
    if limit is not None:
        page_size = max(1, min(page_size, limit))
    result = Inventory()
    for page in client.pages("/resources", "resourceList", filters.params(), page_size=page_size):
        result.total = page.total if page.total is not None else result.total
        for resource in page.items:
            result.rows.append(to_row(resource))
            if limit is not None and len(result.rows) >= limit:
                return result
    if result.total is None:
        result.total = len(result.rows)
    return result
