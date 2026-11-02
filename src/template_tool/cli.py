# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Command-line entry point.

Settings come from flags, VCFOPS_* environment variables and named profiles in a
shared file (see config.py). Secrets are read from the environment, a
password_command or an interactive prompt, never from a command-line flag, so
they do not end up in shell history or process listings.

Global options work before or after the command name, so both
`template-tool --output json check` and `template-tool check --output json` work.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from template_tool import __version__, _meta, inventory
from template_tool.client import DEFAULT_TOKEN_SCHEME, VcfOpsClient, normalise_host
from template_tool.compat import verdict
from template_tool.config import (
    ENV_PREFIX,
    Settings,
    default_config_path,
    load_config,
    resolve,
    run_password_command,
)
from template_tool.errors import ConfigError, ToolError, UnsupportedVersion
from template_tool.output import FORMATS, emit_record, emit_rows

PROG = "template-tool"

# Settings that can come from a flag, the environment or a profile.
SETTING_FLAGS = ("host", "user", "auth_source", "ca_bundle", "timeout", "token_scheme", "page_size")


def _add_common(parser: argparse.ArgumentParser, *, top: bool) -> None:
    """Options shared by every command.

    They are added to the main parser and to each sub-command, so they can be
    given before or after the command name. On sub-commands the default is
    SUPPRESS, which stops an option that was not repeated after the command from
    overwriting the value given before it.
    """

    def default(value: object) -> object:
        return value if top else argparse.SUPPRESS

    conn = parser.add_argument_group("connection (flag > environment > profile)")
    conn.add_argument(
        "--profile",
        default=default(None),
        metavar="NAME",
        help="named profile from the config file [VCFOPS_PROFILE]",
    )
    conn.add_argument("--config", default=default(None), metavar="PATH", help="profile file [VCFOPS_CONFIG]")
    conn.add_argument(
        "--host", default=default(None), metavar="FQDN", help="VCF Operations FQDN [VCFOPS_HOST]"
    )
    conn.add_argument(
        "--user", default=default(None), metavar="ACCOUNT", help="read-only service account [VCFOPS_USER]"
    )
    conn.add_argument(
        "--auth-source",
        default=default(None),
        metavar="NAME",
        help="authentication source for directory accounts (default: local) [VCFOPS_AUTH_SOURCE]",
    )
    tls = conn.add_mutually_exclusive_group()
    tls.add_argument(
        "--ca-bundle",
        default=default(None),
        metavar="PEM",
        help="CA chain that signed the VCF Operations certificate [VCFOPS_CA_BUNDLE]",
    )
    tls.add_argument(
        "--insecure",
        action="store_true",
        default=default(False),
        help="skip TLS verification for this run (labs only; prints a warning)",
    )
    conn.add_argument(
        "--timeout", type=float, default=default(None), metavar="SECONDS", help="per request (default: 30)"
    )
    conn.add_argument("--token-scheme", default=default(None), help=argparse.SUPPRESS)

    out = parser.add_argument_group("output")
    out.add_argument("-o", "--output", choices=FORMATS, default=default("text"), help="default: text")
    out.add_argument(
        "-v", "--verbose", action="store_true", default=default(False), help="debug logging (no secrets)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=f"{_meta.DISPLAY_NAME}: {_meta.SUMMARY}",
        epilog=f"Docs: {_meta.PROJECT_PAGE}  |  Not affiliated with Broadcom. Read-only by design.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_common(parser, top=True)

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def command(name: str, help_text: str, examples: str = "") -> argparse.ArgumentParser:
        p = sub.add_parser(
            name,
            help=help_text,
            description=help_text,
            epilog=f"examples:\n{examples}" if examples else None,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        _add_common(p, top=False)
        return p

    command(
        "check",
        "connect, confirm the account works and the version is supported",
        f"  {PROG} check --profile prod\n  {PROG} check -o json   # for monitoring scripts",
    )

    inv = command(
        "inventory",
        "list objects with their kind, adapter and health",
        f"  {PROG} inventory --resource-kind VirtualMachine --limit 20\n"
        f"  {PROG} inventory --adapter-kind VMWARE --resource-kind HostSystem -o csv > hosts.csv\n"
        f"  {PROG} inventory --name web -o json | jq '.resources[].name'",
    )
    filters = inv.add_argument_group("filters")
    filters.add_argument("--adapter-kind", metavar="KIND", help="for example VMWARE")
    filters.add_argument(
        "--resource-kind",
        metavar="KIND",
        action="append",
        default=[],
        help="for example VirtualMachine; repeat for several kinds",
    )
    filters.add_argument("--name", metavar="TEXT", help="object name filter, passed to the Suite API")
    inv.add_argument("--limit", type=int, metavar="N", help="stop after N objects")
    inv.add_argument(
        "--page-size", type=int, metavar="N", help="objects per request (default: 500) [VCFOPS_PAGE_SIZE]"
    )

    command("profiles", "list the profiles in the config file (no connection)")
    command("about", "show the tool version and its compatibility baseline (no connection)")
    return parser


# --------------------------------------------------------------------- settings


def _config_path(args: argparse.Namespace) -> Path:
    return Path(args.config).expanduser() if args.config else default_config_path()


def _settings(args: argparse.Namespace) -> Settings:
    config = load_config(_config_path(args))
    flags = {key: getattr(args, key, None) for key in SETTING_FLAGS}
    return resolve(flags, config, args.profile)


def _password(settings: Settings, host: str) -> str:
    password = os.environ.get(f"{ENV_PREFIX}PASSWORD")
    if password:
        return password
    if settings.password_command:
        return run_password_command(settings.password_command)
    if not sys.stdin.isatty():
        raise ConfigError(
            "No password: there is no terminal to prompt on.",
            hint="Set VCFOPS_PASSWORD, or password_command in the profile, for unattended runs.",
        )
    return getpass.getpass(f"Password for {settings.user} at {host}: ")


def _client(args: argparse.Namespace, settings: Settings) -> VcfOpsClient:
    """Validate everything that can be checked locally before asking for a password."""
    if not settings.host:
        raise ConfigError(
            "No VCF Operations host. Use --host, VCFOPS_HOST or a profile.",
            hint=f"`{PROG} profiles` lists the profiles in {_config_path(args)}.",
        )
    host = normalise_host(settings.host)
    if not settings.user:
        raise ConfigError("No username. Use --user, VCFOPS_USER or a profile.")
    if args.insecure:
        print("WARNING: TLS verification is disabled. Use --ca-bundle outside a lab.", file=sys.stderr)
        verify: bool | str = False
    elif settings.ca_bundle:
        if not Path(settings.ca_bundle).is_file():
            raise ConfigError(f"CA bundle not found: {settings.ca_bundle}")
        verify = settings.ca_bundle
    else:
        verify = True
    return VcfOpsClient(
        host,
        settings.user,
        _password(settings, host),
        auth_source=settings.auth_source,
        verify=verify,
        timeout=settings.timeout,
        token_scheme=settings.token_scheme or DEFAULT_TOKEN_SCHEME,
        max_retries=settings.max_retries,
    )


# --------------------------------------------------------------------- commands


def cmd_about(args: argparse.Namespace) -> int:
    config_path = _config_path(args)
    payload = {
        "tool": _meta.DISPLAY_NAME,
        "version": __version__,
        "baseline": _meta.BASELINE,
        "projectPage": _meta.PROJECT_PAGE,
        "configFile": str(config_path),
        "configFound": config_path.is_file(),
    }
    found = "" if payload["configFound"] else " (not found)"
    emit_record(
        args.output,
        payload,
        [
            f"{_meta.DISPLAY_NAME} {__version__}",
            f"Supports VCF Operations {_meta.BASELINE} and later",
            f"Profiles: {config_path}{found}",
            f"Docs: {_meta.PROJECT_PAGE}",
        ],
    )
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args))
    selected = args.profile or os.environ.get(f"{ENV_PREFIX}PROFILE") or config.default_profile
    rows = [
        {
            "name": name,
            "host": values.get("host", ""),
            "user": values.get("user", ""),
            "authSource": values.get("auth_source", "local"),
            "selected": name == selected,
        }
        for name, values in sorted(config.profiles.items())
    ]
    if not config.exists and args.output == "text":
        print(f"No profile file at {config.path}.")
        print("Copy examples/config.toml from the repository there, or set VCFOPS_CONFIG.")
        return 0
    emit_rows(
        args.output,
        rows,
        (
            ("name", "Profile"),
            ("host", "Host"),
            ("user", "User"),
            ("authSource", "Auth source"),
            ("selected", "Selected"),
        ),
        key="profiles",
        meta={"configFile": str(config.path), "defaultProfile": config.default_profile},
        footer=f"File: {config.path}",
        empty=f"{config.path} defines no profiles.",
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    settings = _settings(args)
    client = _client(args, settings)
    with client:
        result = verdict(client.product_version())

    payload = {
        "host": client.base_url,
        "profile": settings.profile,
        "vcfOperations": result.version_text,
        "baseline": _meta.BASELINE,
        "status": result.status,
        "notes": result.notes,
        "ok": result.ok,
    }
    if not result.ok:
        mark = "FAIL"
    elif result.status == "untested":
        mark = "WARN"
        print(
            f"WARNING: VCF Operations {result.version_text} has not been tested with this release. "
            "Please report the result: see docs/compatibility.md.",
            file=sys.stderr,
        )
    else:
        mark = " OK "
    via = f" (profile {settings.profile})" if settings.profile else ""
    emit_record(
        args.output,
        payload,
        [
            f"[ OK ] Authenticated to {client.base_url} as {settings.user}{via}",
            f"[ OK ] VCF Operations {result.version_text}",
            f"[{mark}] Compatibility: {result.status} ({result.notes})",
        ],
    )
    if not result.ok:
        raise UnsupportedVersion(
            f"VCF Operations {result.version_text} is not supported "
            f"(baseline {_meta.BASELINE}, status {result.status})."
        )
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    if args.limit is not None and args.limit < 1:
        raise ConfigError("--limit must be 1 or more.")
    settings = _settings(args)
    filters = inventory.Filters(
        adapter_kind=args.adapter_kind,
        resource_kinds=tuple(args.resource_kind),
        name=args.name,
    )
    with _client(args, settings) as client:
        found = inventory.collect(client, filters, page_size=settings.page_size, limit=args.limit)

    shown = len(found.rows)
    if found.truncated:
        footer = f"Showing {shown} of {found.total} objects. Raise --limit or narrow the filters."
    else:
        footer = f"{shown} object{'s' if shown != 1 else ''}."
    emit_rows(
        args.output,
        found.rows,
        inventory.COLUMNS,
        key="resources",
        meta={"host": client.base_url, "count": shown, "totalCount": found.total},
        footer=footer,
        empty="No objects matched. If you expected some, check the filters and the account's scope.",
    )
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "check": cmd_check,
    "inventory": cmd_inventory,
    "profiles": cmd_profiles,
    "about": cmd_about,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.command:
        parser.print_help()
        return 2
    try:
        return COMMANDS[args.command](args)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if exc.hint:
            print(f"hint:  {exc.hint}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
