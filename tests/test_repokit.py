# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Checks for the parts of scripts/repokit.py that tool authors configure in tool.yaml."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("yaml")

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repokit.py"
_SPEC = importlib.util.spec_from_file_location("repokit", _PATH)
repokit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repokit)


@pytest.fixture
def meta():
    return copy.deepcopy(repokit.load_meta())


def test_default_boundary_in_header(meta):
    meta.pop("boundary", None)
    assert repokit.DEFAULT_BOUNDARY in repokit.block_header(meta)
    assert repokit.project_card(meta)["boundary"] == repokit.DEFAULT_BOUNDARY


def test_custom_boundary_replaces_the_default(meta):
    meta["boundary"] = "It reads from SDDC Manager and\n  opens TLS connections. It never writes."
    header = repokit.block_header(meta)
    assert "It reads from SDDC Manager and opens TLS connections. It never writes." in header
    assert repokit.DEFAULT_BOUNDARY not in header
    assert "not affiliated with" in header
    assert repokit.project_card(meta)["boundary"].startswith("It reads from SDDC Manager")


def test_architecture_override(meta):
    meta["architecture"] = 'flowchart LR\n  tool["Script"] --> sddc["SDDC Manager API"]\n'
    block = repokit.block_architecture(meta)
    assert block == '```mermaid\nflowchart LR\n  tool["Script"] --> sddc["SDDC Manager API"]\n```'


def test_default_architecture_per_kind(meta):
    meta.pop("architecture", None)
    assert "VCF Operations Suite API" in repokit.block_architecture(meta)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("architecture", "tool --> api", "must be a Mermaid diagram"),
        ("architecture", "flowchart LR\n```\n", "must not contain"),
        ("architecture", 42, "must be a Mermaid diagram"),
        ("boundary", "   ", "non-empty sentence"),
        ("boundary", ["a list"], "non-empty sentence"),
    ],
)
def test_invalid_overrides_are_errors(meta, key, value, message):
    meta[key] = value
    errors, _ = repokit.validate_meta(meta)
    assert any(message in e for e in errors), errors


def test_long_boundary_is_a_warning(meta):
    meta["boundary"] = "word " * 80
    errors, warnings = repokit.validate_meta(meta)
    assert not [e for e in errors if "boundary" in e]
    assert any("boundary is over 300" in w for w in warnings)
