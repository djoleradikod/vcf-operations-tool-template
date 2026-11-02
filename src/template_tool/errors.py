# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Errors with a stable exit code and a hint the operator can act on."""

from __future__ import annotations


class ToolError(Exception):
    """Base class. Each subclass maps to one documented exit code."""

    exit_code = 1
    hint = ""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        if hint is not None:
            self.hint = hint


class ConfigError(ToolError):
    exit_code = 2
    hint = "Run with --help to see the required settings."


class AuthError(ToolError):
    exit_code = 3
    hint = "Check the username, password and --auth-source for the service account."


class PermissionDenied(ToolError):
    exit_code = 4
    hint = (
        "The account authenticated but its role does not allow this call. "
        "See docs/permissions.md for the minimum read-only role."
    )


class UnsupportedVersion(ToolError):
    exit_code = 5
    hint = "See docs/compatibility.md for supported VCF Operations versions."


class TlsError(ToolError):
    exit_code = 6
    hint = (
        "The VCF Operations certificate is not trusted on this machine. "
        "Pass --ca-bundle with your CA chain rather than disabling verification."
    )


class ReadOnlyViolation(ToolError):
    """Raised before any request leaves the machine if it could change state."""

    exit_code = 7
    hint = "This tool is read-only by design. See docs/architecture.md."


class ApiError(ToolError):
    exit_code = 8
    hint = "Run with -v for request details (credentials and tokens are never logged)."
