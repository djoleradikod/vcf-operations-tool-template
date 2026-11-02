# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Version parsing and the compatibility verdict, driven by tool.yaml (via _meta)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from template_tool import _meta

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(text: str) -> tuple[int, int, int]:
    """Return (major, minor, patch) from text such as '9.1.1', '9.1.1.0' or a release name."""
    match = _VERSION_RE.search(str(text))
    if not match:
        raise ValueError(f"no version number in {text!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def version_from_api(payload: dict[str, Any]) -> tuple[int, int, int]:
    """Read the product version from a /versions/current response.

    Prefers the numeric fields and falls back to the release name, so a field
    rename in a future release degrades gracefully instead of crashing.
    """
    if all(k in payload for k in ("major", "minor")):
        return int(payload["major"]), int(payload["minor"]), int(payload.get("minorMinor", 0))
    for key in ("releaseName", "version", "productVersion"):
        if key in payload:
            return parse_version(payload[key])
    raise ValueError("version response has no recognised version field")


def _matches(pattern: str, version: tuple[int, int, int]) -> bool:
    """'9.1.1' matches exactly, '9.1.x' any patch, '9.x' any minor. Missing parts are 0."""
    parts = str(pattern).lower().split(".")
    for i, have in enumerate(version):
        want = parts[i] if i < len(parts) else "0"
        if want == "x":
            return True
        if int(want) != have:
            return False
    return True


@dataclass(frozen=True)
class Verdict:
    version: tuple[int, int, int]
    baseline: tuple[int, int, int]
    status: str
    notes: str

    @property
    def version_text(self) -> str:
        return ".".join(map(str, self.version))

    @property
    def meets_baseline(self) -> bool:
        return self.version >= self.baseline

    @property
    def ok(self) -> bool:
        return self.meets_baseline and self.status != "unsupported"


def verdict(version: tuple[int, int, int]) -> Verdict:
    """Compare a product version with the baseline and the matrix for this release."""
    baseline = parse_version(_meta.BASELINE)
    for row in _meta.MATRIX:
        if _matches(row["vcf_operations"], version):
            return Verdict(version, baseline, row["status"], row.get("notes", ""))
    status = "untested" if version >= baseline else "unsupported"
    notes = "Newer than any tested release." if version >= baseline else "Below the baseline."
    return Verdict(version, baseline, status, notes)
