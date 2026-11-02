# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from template_tool import config
from template_tool.config import ConfigFile, load_config, resolve, run_password_command
from template_tool.errors import ConfigError

PROFILES = """
default_profile = "lab"

[profiles.lab]
host = "ops-lab.rainpole.io"
user = "svc-vcfops-ro"
ca_bundle = "~/certs/rainpole-ca.pem"

[profiles.prod]
host = "ops.rainpole.io"
user = "svc-vcfops-ro"
auth_source = "rainpole.io"
timeout = 60
max_retries = 5
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(PROFILES)
    return path


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


# -- locating the file -------------------------------------------------------


def test_config_path_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("VCFOPS_CONFIG", str(tmp_path / "x.toml"))
    assert config.default_config_path() == tmp_path / "x.toml"


def test_config_path_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("VCFOPS_CONFIG")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.default_config_path() == tmp_path / "vcfops" / "config.toml"


def test_config_path_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("VCFOPS_CONFIG")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.default_config_path() == tmp_path / "vcfops" / "config.toml"


# -- loading and validation --------------------------------------------------


def test_missing_file_is_not_an_error(tmp_path):
    loaded = load_config(tmp_path / "absent.toml")
    assert not loaded.exists
    assert loaded.profiles == {}


def test_loads_profiles(config_file):
    loaded = load_config(config_file)
    assert loaded.default_profile == "lab"
    assert sorted(loaded.profiles) == ["lab", "prod"]


@pytest.mark.parametrize("key", ["password", "PASSWORD", "token", "secret"])
def test_secrets_are_refused(tmp_path, key):
    path = write(tmp_path, f'[profiles.lab]\nhost = "ops.rainpole.io"\n{key} = "x"\n')
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert "Secrets do not belong" in str(info.value)
    assert "password_command" in info.value.hint


@pytest.mark.parametrize("key", ["insecure", "verify"])
def test_tls_cannot_be_turned_off_in_a_profile(tmp_path, key):
    path = write(tmp_path, f"[profiles.lab]\n{key} = false\n")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert "ca_bundle" in info.value.hint


def test_unknown_key_lists_known_keys(tmp_path):
    path = write(tmp_path, '[profiles.lab]\nhots = "typo"\n')
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert "hots" in str(info.value)
    assert "host" in info.value.hint


@pytest.mark.parametrize("line", ['timeout = "fast"', "page_size = true", "host = 42"])
def test_wrong_types_are_refused(tmp_path, line):
    with pytest.raises(ConfigError, match="wrong type"):
        load_config(write(tmp_path, f"[profiles.lab]\n{line}\n"))


@pytest.mark.parametrize(
    "text",
    [
        "profiles = 3\n",
        "[profiles]\nlab = 3\n",
        'default_profile = "missing"\n[profiles.lab]\nhost = "ops.rainpole.io"\n',
        "this is not toml",
    ],
)
def test_malformed_files_are_refused(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


# -- precedence --------------------------------------------------------------


def test_default_profile_is_used(config_file):
    settings = resolve({}, load_config(config_file))
    assert settings.profile == "lab"
    assert settings.host == "ops-lab.rainpole.io"
    assert settings.auth_source == "local"
    assert settings.ca_bundle == str(Path("~/certs/rainpole-ca.pem").expanduser())
    assert settings.page_size == 500


def test_flag_beats_environment_beats_profile(monkeypatch, config_file):
    loaded = load_config(config_file)
    monkeypatch.setenv("VCFOPS_HOST", "ops-env.rainpole.io")
    assert resolve({}, loaded).host == "ops-env.rainpole.io"
    assert resolve({"host": "ops-flag.rainpole.io"}, loaded).host == "ops-flag.rainpole.io"


def test_profile_selected_by_argument_or_environment(monkeypatch, config_file):
    loaded = load_config(config_file)
    assert resolve({}, loaded, "prod").timeout == 60.0
    monkeypatch.setenv("VCFOPS_PROFILE", "prod")
    settings = resolve({}, loaded)
    assert (settings.profile, settings.auth_source, settings.max_retries) == ("prod", "rainpole.io", 5)


def test_unknown_profile(config_file, tmp_path):
    with pytest.raises(ConfigError, match="'nope' is not defined"):
        resolve({}, load_config(config_file), "nope")
    with pytest.raises(ConfigError, match="file not found"):
        resolve({}, ConfigFile(tmp_path / "absent.toml"), "lab")


def test_no_profile_and_no_file_gives_defaults(tmp_path):
    settings = resolve({}, ConfigFile(tmp_path / "absent.toml"))
    assert settings.profile is None
    assert settings.host is None
    assert settings.timeout == 30.0
    assert settings.max_retries == 3


@pytest.mark.parametrize(
    ("variable", "value"),
    [("VCFOPS_TIMEOUT", "soon"), ("VCFOPS_PAGE_SIZE", "1.5"), ("VCFOPS_MAX_RETRIES", "many")],
)
def test_bad_numbers_from_environment(monkeypatch, tmp_path, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ConfigError, match="Invalid number"):
        resolve({}, ConfigFile(tmp_path / "absent.toml"))


@pytest.mark.parametrize(
    "flags", [{"timeout": 0.0}, {"page_size": 0}, {"page_size": 50_000}, {"timeout": 3600.0}]
)
def test_out_of_range_values(tmp_path, flags):
    with pytest.raises(ConfigError, match="must be between"):
        resolve(flags, ConfigFile(tmp_path / "absent.toml"))


# -- password_command --------------------------------------------------------


def _python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_password_command_returns_first_line():
    assert run_password_command(_python("print('s3cret'); print('ignored')")) == "s3cret"


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (_python("import sys; sys.exit(3)"), "exited with status 3"),
        (_python("pass"), "printed nothing"),
        ("/nonexistent/secret-tool lookup vcfops", "failed to run"),
    ],
)
def test_password_command_failures(command, message):
    with pytest.raises(ConfigError, match=message):
        run_password_command(command)
