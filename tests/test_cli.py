# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

import pytest

from template_tool import __version__, cli
from template_tool.client import VcfOpsClient

from .conftest import FakeResponse


@pytest.fixture
def wired(monkeypatch, ops_session):
    """Route the CLI's client through the fake session and set the environment."""
    original = VcfOpsClient.__init__

    def init(self, *args, **kwargs):
        kwargs["session"] = ops_session
        original(self, *args, **kwargs)

    monkeypatch.setattr(VcfOpsClient, "__init__", init)
    monkeypatch.setenv("VCFOPS_HOST", "ops.rainpole.io")
    monkeypatch.setenv("VCFOPS_USER", "svc-tool")
    monkeypatch.setenv("VCFOPS_PASSWORD", "pw")
    return ops_session


def test_about_is_offline(capsys):
    assert cli.main(["--output", "json", "about"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["version"] == __version__
    assert out["projectPage"].startswith("https://djonko.dev/projects/")


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out


def test_check_success(wired, capsys):
    assert cli.main(["check"]) == 0
    assert "VCF Operations 9.1.1" in capsys.readouterr().out


def test_check_json(wired, capsys):
    assert cli.main(["--output", "json", "check"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["vcfOperations"] == "9.1.1"


def test_check_unsupported_version_exit_code(wired, capsys):
    wired.routes[("GET", "/suite-api/api/versions/current")] = FakeResponse(
        200, {"major": 9, "minor": 0, "minorMinor": 2}
    )
    assert cli.main(["check"]) == 5
    assert "baseline" in capsys.readouterr().err


def test_permission_denied_exit_code(wired, capsys):
    wired.routes[("GET", "/suite-api/api/versions/current")] = FakeResponse(403, {})
    assert cli.main(["check"]) == 4
    err = capsys.readouterr().err
    assert "docs/permissions.md" in err


def test_insecure_warns(wired, capsys):
    assert cli.main(["--insecure", "check"]) == 0
    assert "TLS verification is disabled" in capsys.readouterr().err
    assert wired.verify is False


def test_ca_bundle_is_used(wired):
    assert cli.main(["--ca-bundle", "/etc/ssl/ops-ca.pem", "check"]) == 0
    assert wired.verify == "/etc/ssl/ops-ca.pem"


def test_missing_password_without_tty(monkeypatch, capsys):
    monkeypatch.setenv("VCFOPS_HOST", "ops.rainpole.io")
    monkeypatch.setenv("VCFOPS_USER", "svc-tool")
    monkeypatch.delenv("VCFOPS_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["check"]) == 2


def test_password_is_not_a_flag():
    options = {a for action in cli.build_parser()._actions for a in action.option_strings}
    assert not any("pass" in o for o in options)
