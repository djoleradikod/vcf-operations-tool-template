# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""Text, JSON and CSV output, shared by every command.

Text is for people at a terminal. JSON and CSV are for pipelines and
spreadsheets, so they carry every field in full and nothing else goes to stdout.
Warnings and progress always go to stderr.
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, TextIO

FORMATS = ("text", "json", "csv")
MAX_CELL = 48  # widest text-table cell before it is shortened; JSON and CSV are never shortened

# A cell that starts with one of these is treated as a formula by Excel and
# LibreOffice. Object names come from vCenter and other sources that many people
# can edit, so a CSV export must not let a name like "=HYPERLINK(...)" run.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

Columns = Sequence[tuple[str, str]]  # (key in the row, heading in text output)


def csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return "" if value is None else value


def _text_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    text = str(value)
    return text if len(text) <= MAX_CELL else text[: MAX_CELL - 3] + "..."


def text_table(rows: Iterable[Mapping[str, Any]], columns: Columns) -> str:
    cells = [[_text_cell(row.get(key)) for key, _ in columns] for row in rows]
    headings = [heading for _, heading in columns]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headings)]

    def line(values: Sequence[str]) -> str:
        return "  ".join(v.ljust(w) for v, w in zip(values, widths, strict=True)).rstrip()

    rule = ["-" * w for w in widths]
    return "\n".join([line(headings), line(rule)] + [line(r) for r in cells])


def _write_csv(rows: Iterable[Mapping[str, Any]], keys: Sequence[str], stream: TextIO) -> None:
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(keys)
    for row in rows:
        writer.writerow([csv_cell(row.get(key)) for key in keys])


def emit_record(
    fmt: str, payload: Mapping[str, Any], lines: Sequence[str], stream: TextIO | None = None
) -> None:
    """One result, such as the outcome of `check`."""
    stream = stream or sys.stdout
    if fmt == "json":
        print(json.dumps(payload, indent=2), file=stream)
    elif fmt == "csv":
        _write_csv([payload], list(payload), stream)
    else:
        print("\n".join(lines), file=stream)


def emit_rows(
    fmt: str,
    rows: Sequence[Mapping[str, Any]],
    columns: Columns,
    *,
    key: str,
    meta: Mapping[str, Any] | None = None,
    footer: str = "",
    empty: str = "Nothing to show.",
    stream: TextIO | None = None,
) -> None:
    """A list of results, such as inventory objects.

    JSON wraps the rows in an object so that metadata (counts, the host) can sit
    next to them: {"host": ..., "count": 2, "<key>": [...]}. CSV has one header
    row with the stable field names, then one row per result.
    """
    stream = stream or sys.stdout
    if fmt == "json":
        print(json.dumps({**(meta or {}), key: list(rows)}, indent=2), file=stream)
    elif fmt == "csv":
        _write_csv(rows, [k for k, _ in columns], stream)
    elif not rows:
        print(empty, file=stream)
    else:
        print(text_table(rows, columns), file=stream)
        if footer:
            print(f"\n{footer}", file=stream)
