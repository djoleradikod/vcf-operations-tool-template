# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from template_tool import _meta
from template_tool.compat import _matches, parse_version, verdict, version_from_api


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("9.1.1", (9, 1, 1)),
        ("9.1", (9, 1, 0)),
        ("9.1.1.0", (9, 1, 1)),
        ("VCF Operations 9.1.1 Build 24000000", (9, 1, 1)),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def test_parse_version_rejects_garbage():
    with pytest.raises(ValueError):
        parse_version("unknown")


def test_version_from_api_prefers_numeric_fields():
    assert version_from_api({"major": 9, "minor": 2, "minorMinor": 0, "releaseName": "x 9.1.1"}) == (9, 2, 0)


def test_version_from_api_falls_back_to_release_name():
    assert version_from_api({"releaseName": "VCF Operations 9.1.1"}) == (9, 1, 1)


def test_version_from_api_without_fields():
    with pytest.raises(ValueError):
        version_from_api({})


@pytest.mark.parametrize(
    ("pattern", "version", "hit"),
    [
        ("9.1.1", (9, 1, 1), True),
        ("9.1.1", (9, 1, 2), False),
        ("9.1.x", (9, 1, 7), True),
        ("9.x", (9, 4, 0), True),
        ("9.0.x", (9, 1, 0), False),
        ("9.1", (9, 1, 0), True),
    ],
)
def test_matches(pattern, version, hit):
    assert _matches(pattern, version) is hit


def test_baseline_is_supported():
    result = verdict(parse_version(_meta.BASELINE))
    assert result.meets_baseline
    assert result.ok


def test_below_baseline_is_not_ok():
    result = verdict((9, 0, 2))
    assert not result.meets_baseline
    assert not result.ok


def test_newer_unlisted_release_is_untested_but_allowed():
    result = verdict((99, 0, 0))
    assert result.status == "untested"
    assert result.ok
    assert result.version_text == "99.0.0"
