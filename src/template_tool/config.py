# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Connection settings: command-line flags, environment, and a shared profile file.

Operators usually look after more than one VCF Operations deployment (a lab, a
pre-production cluster, production). Typing the host, account and CA bundle on
every run invites mistakes, so settings can live in named profiles in one TOML
file that every "<Tool> for VCF Operations" project reads:

    default_profile = "lab"

    [profiles.lab]
    host = "ops-lab.rainpole.io"
    user = "svc-vcfops-ro"
    ca_bundle = "~/.config/vcfops/rainpole-ca.pem"

    [profiles.prod]
    host = "ops.rainpole.io"
    user = "svc-vcfops-ro"
    auth_source = "rainpole.io"
    password_command = "pass show vcfops/prod"

Precedence, highest first: command-line flag, VCFOPS_* environment variable,
selected profile, built-in default. Passwords are never read from the file; use
VCFOPS_PASSWORD, the interactive prompt, or password_command, which runs a
secret-manager command and reads the first line it prints.

There is deliberately no setting to turn off TLS verification. --insecure is
accepted only on the command line, so skipping verification is a visible
decision made on each run rather than something a file does silently.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10 in CI
    import tomli as tomllib

from template_tool.errors import ConfigError

ENV_PREFIX = "VCFOPS_"
PROFILE_KEYS = {
    "host": str,
    "user": str,
    "auth_source": str,
    "ca_bundle": str,
    "timeout": (int, float),
    "token_scheme": str,
    "password_command": str,
    "page_size": int,
    "max_retries": int,
}
FORBIDDEN_KEYS = {"password", "passwd", "token", "secret"}
DEFAULTS: dict[str, Any] = {
    "auth_source": "local",
    "timeout": 30.0,
    "page_size": 500,
    "max_retries": 3,
}
PASSWORD_COMMAND_TIMEOUT = 30
LIMITS = {"timeout": (1.0, 600.0), "page_size": (1, 10_000), "max_retries": (0, 10)}


def default_config_path() -> Path:
    """VCFOPS_CONFIG, else the platform's per-user config directory."""
    override = os.environ.get(f"{ENV_PREFIX}CONFIG")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "vcfops" / "config.toml"


@dataclass
class ConfigFile:
    path: Path
    default_profile: str | None = None
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def exists(self) -> bool:
        return self.path.is_file()


def load_config(path: Path | None = None) -> ConfigFile:
    """Read and validate the profile file. A missing file is not an error."""
    path = path or default_config_path()
    if not path.is_file():
        return ConfigFile(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc

    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigError(f"{path}: [profiles] must be a table.")
    for name, values in profiles.items():
        if not isinstance(values, dict):
            raise ConfigError(f"{path}: profile '{name}' must be a table.")
        for key, value in values.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise ConfigError(
                    f"{path}: profile '{name}' contains '{key}'. Secrets do not belong in this file.",
                    hint="Use VCFOPS_PASSWORD, the interactive prompt, or password_command.",
                )
            if key in {"insecure", "verify", "verify_ssl"}:
                raise ConfigError(
                    f"{path}: profile '{name}' sets '{key}'. TLS verification cannot be turned off in a profile.",
                    hint="Set ca_bundle to your CA chain. --insecure is accepted only on the command line.",
                )
            if key not in PROFILE_KEYS:
                raise ConfigError(
                    f"{path}: profile '{name}' has unknown setting '{key}'.",
                    hint=f"Known settings: {', '.join(sorted(PROFILE_KEYS))}.",
                )
            if not isinstance(value, PROFILE_KEYS[key]) or isinstance(value, bool):
                raise ConfigError(f"{path}: '{key}' in profile '{name}' has the wrong type.")
    default = data.get("default_profile")
    if default is not None and default not in profiles:
        raise ConfigError(f"{path}: default_profile '{default}' is not defined under [profiles].")
    return ConfigFile(path, default, profiles)


@dataclass(frozen=True)
class Settings:
    """The resolved connection settings for one run."""

    profile: str | None
    host: str | None
    user: str | None
    auth_source: str
    ca_bundle: str | None
    timeout: float
    token_scheme: str | None
    password_command: str | None
    page_size: int
    max_retries: int


def resolve(flags: dict[str, Any], config: ConfigFile, profile: str | None = None) -> Settings:
    """Merge flags, environment, profile and defaults, in that order of precedence."""
    name = profile or os.environ.get(f"{ENV_PREFIX}PROFILE") or config.default_profile
    if name and name not in config.profiles:
        where = config.path if config.exists else f"{config.path} (file not found)"
        raise ConfigError(f"Profile '{name}' is not defined in {where}.")
    values = config.profiles.get(name, {}) if name else {}

    def pick(key: str) -> Any:
        if flags.get(key) is not None:
            return flags[key]
        env = os.environ.get(f"{ENV_PREFIX}{key.upper()}")
        if env:
            return env
        if key in values:
            return values[key]
        return DEFAULTS.get(key)

    ca_bundle = pick("ca_bundle")
    try:
        settings = Settings(
            profile=name,
            host=pick("host"),
            user=pick("user"),
            auth_source=str(pick("auth_source")),
            ca_bundle=str(Path(ca_bundle).expanduser()) if ca_bundle else None,
            timeout=float(pick("timeout")),
            token_scheme=pick("token_scheme"),
            password_command=pick("password_command"),
            page_size=int(pick("page_size")),
            max_retries=int(pick("max_retries")),
        )
    except ValueError as exc:
        raise ConfigError(f"Invalid number in settings: {exc}") from exc
    for key, (low, high) in LIMITS.items():
        value = getattr(settings, key)
        if not low <= value <= high:
            raise ConfigError(f"{key} must be between {low:g} and {high:g}, not {value:g}.")
    return settings


def run_password_command(command: str) -> str:
    """Run a secret-manager command without a shell and return the first line it prints.

    On Windows the command line is handed to the process as written, because
    Windows programs parse their own arguments. Elsewhere it is split with shell
    quoting rules. Either way no shell is involved, so pipes and variables in the
    command are not expanded; wrap them in a script if you need them.
    """
    try:
        argv: str | list[str] = command if os.name == "nt" else shlex.split(command)
        result = subprocess.run(  # noqa: S603 - the operator's own configured command, no shell
            argv,
            capture_output=True,
            text=True,
            timeout=PASSWORD_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ConfigError(f"password_command failed to run: {type(exc).__name__}.") from exc
    if result.returncode != 0:
        raise ConfigError(f"password_command exited with status {result.returncode}.")
    password = result.stdout.splitlines()[0].strip() if result.stdout.strip() else ""
    if not password:
        raise ConfigError("password_command printed nothing.")
    return password
