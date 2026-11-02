# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Command-line entry point.

Secrets are read from the environment or an interactive prompt, never from a
command-line flag, so they do not end up in shell history or process listings.
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from collections.abc import Sequence

from template_tool import __version__, _meta
from template_tool.client import DEFAULT_TOKEN_SCHEME, VcfOpsClient
from template_tool.compat import verdict
from template_tool.errors import ConfigError, ToolError, UnsupportedVersion

ENV_PREFIX = "VCFOPS_"


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"{ENV_PREFIX}{name}", default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="template-tool",
        description=f"{_meta.DISPLAY_NAME}: {_meta.SUMMARY}",
        epilog=(f"Docs: {_meta.PROJECT_PAGE}  |  Not affiliated with Broadcom. Read-only by design."),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--host", default=_env("HOST"), help="VCF Operations FQDN [VCFOPS_HOST]")
    parser.add_argument("--user", default=_env("USER"), help="service account [VCFOPS_USER]")
    parser.add_argument(
        "--auth-source",
        default=_env("AUTH_SOURCE", "local"),
        help="authentication source name (default: local) [VCFOPS_AUTH_SOURCE]",
    )
    tls = parser.add_mutually_exclusive_group()
    tls.add_argument(
        "--ca-bundle",
        default=_env("CA_BUNDLE"),
        help="PEM file with the CA chain that signed VCF Operations [VCFOPS_CA_BUNDLE]",
    )
    tls.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (labs only; prints a warning)",
    )
    parser.add_argument("--timeout", type=float, default=float(_env("TIMEOUT", "30")))
    parser.add_argument(
        "--token-scheme",
        default=_env("TOKEN_SCHEME", DEFAULT_TOKEN_SCHEME),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--output", choices=("text", "json"), default="text")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser("check", help="connect, confirm the account works and the version is supported")
    sub.add_parser("about", help="show the tool version and its compatibility baseline (offline)")
    return parser


def _password() -> str:
    password = _env("PASSWORD")
    if password:
        return password
    if not sys.stdin.isatty():
        raise ConfigError("Set VCFOPS_PASSWORD; there is no terminal to prompt on.")
    return getpass.getpass("VCF Operations password: ")


def _emit(args: argparse.Namespace, payload: dict, lines: list[str]) -> None:
    if args.output == "json":
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(lines))


def cmd_about(args: argparse.Namespace) -> int:
    payload = {
        "tool": _meta.DISPLAY_NAME,
        "version": __version__,
        "baseline": _meta.BASELINE,
        "projectPage": _meta.PROJECT_PAGE,
    }
    _emit(
        args,
        payload,
        [
            f"{_meta.DISPLAY_NAME} {__version__}",
            f"Supports VCF Operations {_meta.BASELINE} and later",
            f"Docs: {_meta.PROJECT_PAGE}",
        ],
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    if args.insecure:
        print("WARNING: TLS verification is disabled. Use --ca-bundle outside a lab.", file=sys.stderr)
    verify: bool | str = False if args.insecure else (args.ca_bundle or True)
    client = VcfOpsClient(
        args.host,
        args.user or "",
        _password(),
        auth_source=args.auth_source,
        verify=verify,
        timeout=args.timeout,
        token_scheme=args.token_scheme,
    )
    with client:
        result = verdict(client.product_version())

    payload = {
        "host": client.base_url,
        "vcfOperations": result.version_text,
        "baseline": _meta.BASELINE,
        "status": result.status,
        "notes": result.notes,
        "ok": result.ok,
    }
    mark = " OK " if result.ok else "FAIL"
    _emit(
        args,
        payload,
        [
            f"[ OK ] Authenticated to {client.base_url}",
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


COMMANDS = {"check": cmd_check, "about": cmd_about}


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
