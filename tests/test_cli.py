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


def test_ca_bundle_is_used(wired, tmp_path):
    bundle = tmp_path / "ops-ca.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n")
    assert cli.main(["--ca-bundle", str(bundle), "check"]) == 0
    assert wired.verify == str(bundle)


def test_missing_ca_bundle_fails_before_any_request(wired, capsys):
    assert cli.main(["--ca-bundle", "/nonexistent/ca.pem", "check"]) == 2
    assert "CA bundle not found" in capsys.readouterr().err
    assert wired.calls == []


def test_missing_password_without_tty(monkeypatch, capsys):
    monkeypatch.setenv("VCFOPS_HOST", "ops.rainpole.io")
    monkeypatch.setenv("VCFOPS_USER", "svc-tool")
    monkeypatch.delenv("VCFOPS_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["check"]) == 2


def test_password_is_not_a_flag():
    options = {a for action in cli.build_parser()._actions for a in action.option_strings}
    assert not any("pass" in o for o in options)


def test_untested_version_warns_but_succeeds(wired, capsys):
    wired.routes[("GET", "/suite-api/api/versions/current")] = FakeResponse(
        200, {"major": 9, "minor": 9, "minorMinor": 0}
    )
    assert cli.main(["check"]) == 0
    captured = capsys.readouterr()
    assert "[WARN] Compatibility: untested" in captured.out
    assert "has not been tested" in captured.err


# -- options, profiles and passwords -----------------------------------------


def test_options_work_after_the_command(wired, capsys):
    assert cli.main(["check", "--output", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_option_before_the_command_survives(wired, capsys):
    assert cli.main(["-o", "json", "check"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_check_csv(wired, capsys):
    assert cli.main(["check", "-o", "csv"]) == 0
    header, row = capsys.readouterr().out.strip().splitlines()
    assert header.startswith("host,profile,vcfOperations")
    assert "9.1.1" in row


@pytest.fixture
def profile_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(
        'default_profile = "lab"\n'
        '[profiles.lab]\nhost = "ops-lab.rainpole.io"\nuser = "svc-lab"\n'
        '[profiles.prod]\nhost = "ops.rainpole.io"\nuser = "svc-prod"\nauth_source = "rainpole.io"\n'
    )
    monkeypatch.setenv("VCFOPS_CONFIG", str(path))
    return path


@pytest.fixture
def profile_wired(wired, monkeypatch, profile_file):
    monkeypatch.delenv("VCFOPS_HOST")
    monkeypatch.delenv("VCFOPS_USER")
    return wired


def test_check_uses_the_default_profile(profile_wired, capsys):
    assert cli.main(["check"]) == 0
    out = capsys.readouterr().out
    assert "https://ops-lab.rainpole.io as svc-lab (profile lab)" in out


def test_profile_flag_selects_another_profile(profile_wired, capsys):
    assert cli.main(["check", "--profile", "prod", "-o", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["host"], out["profile"]) == ("https://ops.rainpole.io", "prod")
    acquire = profile_wired.calls_to("/auth/token/acquire")[0]
    assert acquire["json"]["authSource"] == "rainpole.io"


def test_flag_overrides_profile(profile_wired, capsys):
    assert cli.main(["--host", "ops-dr.rainpole.io", "check"]) == 0
    assert "https://ops-dr.rainpole.io" in capsys.readouterr().out


def test_profiles_command(profile_file, capsys):
    assert cli.main(["profiles"]) == 0
    out = capsys.readouterr().out
    assert "ops-lab.rainpole.io" in out
    assert "rainpole.io" in out
    assert str(profile_file) in out


def test_profiles_json_marks_the_selected_profile(profile_file, capsys):
    assert cli.main(["profiles", "--profile", "prod", "-o", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["defaultProfile"] == "lab"
    assert {p["name"]: p["selected"] for p in out["profiles"]} == {"lab": False, "prod": True}


def test_profiles_without_a_file(capsys):
    assert cli.main(["profiles"]) == 0
    assert "No profile file" in capsys.readouterr().out


def test_about_reports_the_profile_file(profile_file, capsys):
    assert cli.main(["about", "-o", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["configFile"] == str(profile_file)
    assert out["configFound"] is True


def test_missing_host_fails_before_the_password_prompt(monkeypatch, capsys):
    def no_prompt(*_):
        raise AssertionError("should not prompt")

    monkeypatch.setattr("getpass.getpass", no_prompt)
    assert cli.main(["check"]) == 2
    err = capsys.readouterr().err
    assert "No VCF Operations host" in err
    assert "profiles" in err


def test_missing_user(monkeypatch, capsys):
    monkeypatch.setenv("VCFOPS_HOST", "ops.rainpole.io")
    assert cli.main(["check"]) == 2
    assert "No username" in capsys.readouterr().err


def test_password_command_is_used(profile_wired, monkeypatch, profile_file):
    import sys

    monkeypatch.delenv("VCFOPS_PASSWORD")
    profile_file.write_text(
        '[profiles.lab]\nhost = "ops-lab.rainpole.io"\nuser = "svc-lab"\n'
        f'password_command = \'"{sys.executable}" -c "print(42)"\'\n'
    )
    assert cli.main(["--profile", "lab", "check"]) == 0
    assert profile_wired.calls_to("/auth/token/acquire")[0]["json"]["password"] == "42"


def test_prompts_on_a_terminal(wired, monkeypatch):
    monkeypatch.delenv("VCFOPS_PASSWORD")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda prompt: "typed")
    assert cli.main(["check"]) == 0
    assert wired.calls_to("/auth/token/acquire")[0]["json"]["password"] == "typed"


def test_secret_in_profile_is_refused(profile_file, wired, capsys):
    profile_file.write_text('[profiles.lab]\nhost = "ops.rainpole.io"\npassword = "x"\n')
    assert cli.main(["--profile", "lab", "check"]) == 2
    assert wired.calls == []


# -- inventory ---------------------------------------------------------------

RESOURCES = "/suite-api/api/resources"


def vm(name, health="GREEN", identifier=None):
    return {
        "identifier": identifier or f"id-{name}",
        "resourceKey": {"name": name, "adapterKindKey": "VMWARE", "resourceKindKey": "VirtualMachine"},
        "resourceHealth": health,
    }


def page(items, total):
    return FakeResponse(200, {"pageInfo": {"totalCount": total}, "resourceList": items})


def test_inventory_table(wired, capsys):
    wired.routes[("GET", RESOURCES)] = page([vm("app-01"), vm("db-01", "YELLOW")], 2)
    assert cli.main(["inventory", "--resource-kind", "VirtualMachine", "--adapter-kind", "VMWARE"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].split() == ["Name", "Kind", "Adapter", "Health", "ID"]
    assert "db-01" in out
    assert "YELLOW" in out
    assert out.rstrip().endswith("2 objects.")
    params = wired.calls_to(RESOURCES)[0]["params"]
    assert params["resourceKind"] == ["VirtualMachine"]
    assert params["adapterKind"] == "VMWARE"


def test_inventory_json(wired, capsys):
    wired.routes[("GET", RESOURCES)] = page([vm("app-01")], 1)
    assert cli.main(["inventory", "-o", "json", "--name", "app"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 1
    assert out["resources"][0] == {
        "name": "app-01",
        "resourceKind": "VirtualMachine",
        "adapterKind": "VMWARE",
        "health": "GREEN",
        "identifier": "id-app-01",
    }
    assert wired.calls_to(RESOURCES)[0]["params"]["name"] == "app"


def test_inventory_csv_neutralises_formulas(wired, capsys):
    wired.routes[("GET", RESOURCES)] = page([vm("=HYPERLINK(1)"), vm("plain")], 2)
    assert cli.main(["inventory", "-o", "csv"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "name,resourceKind,adapterKind,health,identifier"
    assert lines[1].startswith("'=HYPERLINK(1)")
    assert lines[2].startswith("plain,")


def test_inventory_limit_stops_early(wired, capsys):
    wired.routes[("GET", RESOURCES)] = page([vm("a"), vm("b")], 40)
    assert cli.main(["inventory", "--limit", "2"]) == 0
    assert "Showing 2 of 40 objects" in capsys.readouterr().out
    calls = wired.calls_to(RESOURCES)
    assert len(calls) == 1
    assert calls[0]["params"]["pageSize"] == 2


def test_inventory_long_names_are_shortened_in_text_only(wired, capsys):
    long_name = "x" * 80
    wired.routes[("GET", RESOURCES)] = page([vm(long_name)], 1)
    assert cli.main(["inventory"]) == 0
    assert "x" * 45 + "..." in capsys.readouterr().out
    assert cli.main(["inventory", "-o", "json"]) == 0
    assert long_name in capsys.readouterr().out


def test_inventory_empty(wired, capsys):
    wired.routes[("GET", RESOURCES)] = page([], 0)
    assert cli.main(["inventory"]) == 0
    assert "No objects matched" in capsys.readouterr().out


def test_inventory_rejects_a_bad_limit(wired, capsys):
    assert cli.main(["inventory", "--limit", "0"]) == 2
    assert wired.calls == []


def test_inventory_page_size_from_environment(wired, monkeypatch):
    monkeypatch.setenv("VCFOPS_PAGE_SIZE", "250")
    wired.routes[("GET", RESOURCES)] = page([vm("a")], 1)
    assert cli.main(["inventory"]) == 0
    assert wired.calls_to(RESOURCES)[0]["params"]["pageSize"] == 250


def test_inventory_permission_denied(wired, capsys):
    wired.routes[("GET", RESOURCES)] = FakeResponse(403, {})
    assert cli.main(["inventory"]) == 4
    assert wired.calls_to("/auth/token/release")
