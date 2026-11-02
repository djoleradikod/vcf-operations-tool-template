#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
"""repokit: keeps a "<Tool> for VCF Operations" repository consistent.

tool.yaml is the single source of truth. Everything a reader sees in more than
one place (name, compatibility, permissions, licence, links) is generated from it.

Commands
  render [--check]           regenerate README/doc blocks, banners, LICENSE/NOTICE, package metadata
  check [--strict]           every repository rule; CI runs this, releases run --strict
  init --name NAME [...]     turn a fresh copy of the template into a named tool
  licence {Apache-2.0,MIT}   switch the licence everywhere (files, headers, metadata, badge)
  bump VERSION               set the version and cut the CHANGELOG section
  verify-tag TAG             release gate: tag, version and changelog agree
  release-notes VERSION      print GitHub release notes for a version
  project-json [-o FILE]     write the djonko.dev project card
  bundle [--outdir DIR]      add PowerShell/management-pack assets to a release
  privacy [PATH ...]         scan for personal data, secrets and unpublishable material
  meta FIELD                 print one field (for workflows), e.g. display_name

Requires PyYAML (installed with the dev extras: pip install -e ".[dev]").
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit('repokit needs PyYAML: pip install -e ".[dev]"')

ROOT = Path(os.environ.get("REPOKIT_ROOT", Path(__file__).resolve().parent.parent))
SUFFIX = "for VCF Operations"
PROJECTS_URL = "https://djonko.dev/projects/"
LICENCES = {"Apache-2.0", "MIT"}
STATUSES = {
    "tested": "Tested",
    "supported": "Supported",
    "untested": "Untested",
    "unsupported": "Not supported",
}
KINDS = {"script", "agent", "management-pack"}
MP_APPROACHES = {"none", "mp-builder", "integration-sdk"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".cfg",
    ".ini",
    ".svg",
    ".sh",
    ".ps1",
    ".psm1",
    ".psd1",
    ".html",
    ".css",
    ".js",
    ".mjs",
    ".csv",
    "",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}


# --------------------------------------------------------------------------- io


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def repo_files() -> list[Path]:
    """Tracked files when git is available, otherwise a filtered walk."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode()
        files = [ROOT / p for p in out.split("\0") if p]
        if files:
            return sorted(f for f in files if f.is_file())
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        found.extend(Path(dirpath) / f for f in filenames)
    return sorted(found)


def text_files() -> list[Path]:
    return [p for p in repo_files() if p.suffix.lower() in TEXT_SUFFIXES and _is_text(p)]


def _is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        return False


# --------------------------------------------------------------------- metadata


def load_meta() -> dict[str, Any]:
    meta = yaml.safe_load(read(ROOT / "tool.yaml"))
    meta["display_name"] = f"{meta['name']} {SUFFIX}"
    gh = meta["github"]
    meta["owner_repo"] = f"{gh['owner']}/{gh['repo']}"
    meta["project_page"] = f"{PROJECTS_URL}{meta['slug']}"
    if meta.get("template"):
        # The template repository links to itself and to the projects index, so its
        # own README has no dead badges or links. `init` switches to the real values.
        meta["owner_repo"] = meta["template_repository"]
        meta["project_page"] = PROJECTS_URL
    meta["repo_url"] = f"https://github.com/{meta['owner_repo']}"
    return meta


def validate_meta(meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    need = [
        "name",
        "slug",
        "package",
        "kind",
        "summary",
        "description",
        "version",
        "licence",
        "copyright_year",
        "author",
        "github",
        "compatibility",
        "permissions",
        "topics",
    ]
    errors += [f"tool.yaml: missing '{k}'" for k in need if k not in meta]
    if errors:
        return errors, warnings

    name = str(meta["name"]).strip()
    if re.match(r"(?i)^vcf\b", name):
        errors.append(f"naming: '{name}' starts with 'VCF'. Use '<Tool> {SUFFIX}', never 'VCF <Tool>'.")
    if name.lower().endswith(SUFFIX.lower()):
        errors.append(f"naming: put the short name in tool.yaml; '{SUFFIX}' is added for you.")
    if not SLUG.match(meta["slug"]):
        errors.append(f"tool.yaml: slug '{meta['slug']}' must be lowercase-kebab-case.")
    if meta["package"] != meta["slug"].replace("-", "_"):
        errors.append("tool.yaml: package must be the slug with '-' replaced by '_'.")
    if meta["kind"] not in KINDS:
        errors.append(f"tool.yaml: kind must be one of {sorted(KINDS)}.")
    approach = (meta.get("management_pack") or {}).get("approach", "none")
    if approach not in MP_APPROACHES:
        errors.append(f"tool.yaml: management_pack.approach must be one of {sorted(MP_APPROACHES)}.")
    if meta["kind"] == "management-pack" and approach == "none":
        errors.append("tool.yaml: a management pack must choose mp-builder or integration-sdk.")
    if not SEMVER.match(str(meta["version"])):
        errors.append(f"tool.yaml: version '{meta['version']}' is not semantic (1.2.3 or 1.2.3-rc.1).")
    if meta["licence"] not in LICENCES:
        errors.append(f"tool.yaml: licence must be one of {sorted(LICENCES)}.")
    if len(str(meta["summary"])) > 160:
        warnings.append("tool.yaml: summary is over 160 characters; it is used as the GitHub description.")
    for topic in meta["topics"]:
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,49}$", str(topic)):
            errors.append(f"tool.yaml: topic '{topic}' is not a valid GitHub topic.")

    compat = meta["compatibility"]
    try:
        baseline = _ver(compat["baseline"])
        if baseline < (9, 1, 1):
            errors.append("compatibility: baseline below 9.1.1 breaks the family-wide rule.")
    except (KeyError, ValueError):
        errors.append("compatibility: baseline must be a version such as 9.1.1.")
    rows = compat.get("matrix") or []
    if not rows:
        errors.append("compatibility: the matrix needs at least one row.")
    for i, row in enumerate(rows, 1):
        for key in ("release", "vcf_operations", "status"):
            if key not in row:
                errors.append(f"compatibility row {i}: missing '{key}'.")
        if row.get("status") not in STATUSES:
            errors.append(f"compatibility row {i}: status must be one of {sorted(STATUSES)}.")
    version = str(meta["version"]).split("-")[0].split(".")
    current = f"{version[0]}.{version[1]}.x" if len(version) >= 2 else ""
    if rows and not any(str(r.get("release")) in (current, str(meta["version"])) for r in rows):
        warnings.append(
            f"compatibility: no matrix row for release {current}. Add the versions you tested, newest first."
        )
    if not any(r.get("status") == "tested" for r in rows):
        warnings.append("compatibility: no row is 'tested'. Test against at least one release.")

    perms = meta["permissions"]
    for key in ("summary", "account", "role", "privileges", "not_required", "network"):
        if key not in perms:
            errors.append(f"permissions: missing '{key}'.")
    text = json.dumps(perms).lower()
    if re.search(r"\badmin(istrator)?\b", perms.get("role", "").lower()) or '"access": "write"' in text:
        errors.append("permissions: the role must be read-only and never admin.")
    if any(p.get("example") for p in perms.get("privileges", [])):
        msg = "permissions: privileges still marked 'example: true'. Confirm them on a real deployment."
        warnings.append(msg)
    return errors, warnings


def _ver(text: Any) -> tuple[int, int, int]:
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", str(text))
    if not m:
        raise ValueError(text)
    return int(m[1]), int(m[2]), int(m[3] or 0)


# ------------------------------------------------------------------ generation


def shield(text: str) -> str:
    return text.replace("-", "--").replace("_", "__").replace(" ", "%20").replace("+", "%2B")


def block_header(m: dict[str, Any]) -> str:
    owner_repo = m["owner_repo"]
    badges = [
        (
            f"https://img.shields.io/github/v/release/{owner_repo}?sort=semver&display_name=tag&label=release",
            "Latest release",
            f"{m['repo_url']}/releases/latest",
        ),
        (
            f"{m['repo_url']}/actions/workflows/ci.yml/badge.svg",
            "CI",
            f"{m['repo_url']}/actions/workflows/ci.yml",
        ),
        (
            f"https://img.shields.io/badge/{shield('VCF Operations')}-{shield(m['compatibility']['baseline'] + '+')}-0f766e",
            f"VCF Operations {m['compatibility']['baseline']} or later",
            "docs/compatibility.md",
        ),
        (
            f"https://img.shields.io/badge/licence-{shield(m['licence'])}-1d4ed8",
            f"Licence {m['licence']}",
            "LICENSE",
        ),
    ]
    if m["kind"] != "management-pack":
        py = str(m["compatibility"].get("python", ">=3.10")).lstrip(">=")
        badges.append(
            (
                f"https://img.shields.io/badge/python-{shield(py + '+')}-334155",
                f"Python {py} or later",
                "pyproject.toml",
            )
        )
    badge_html = "\n  ".join(
        f'<a href="{href}"><img alt="{escape(alt)}" src="{src}"></a>' for src, alt, href in badges
    )
    return f"""<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="{escape(m["display_name"])}" src="docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  {badge_html}
</p>

<p align="center">
  <b><a href="{m["project_page"]}">Project page</a></b> ·
  <a href="docs/">Documentation</a> ·
  <a href="{m["repo_url"]}/releases">Releases</a> ·
  <a href="{m["repo_url"]}/issues/new/choose">Report an issue</a>
</p>

{m["display_name"]}. {m["summary"]}

It reads from VCF Operations and never writes to it, and it runs under a read-only service account.
This is an independent community project. It is not affiliated with, endorsed by or supported by Broadcom."""


def block_compat(m: dict[str, Any], *, full: bool = False) -> str:
    c = m["compatibility"]
    rows = c["matrix"] if full else [r for r in c["matrix"] if r["release"] == c["matrix"][0]["release"]]
    lines = [
        f"The baseline is VCF Operations {c['baseline']} or later. {' '.join(str(c['baseline_reason']).split())}",
        "",
        "| Tool release | VCF Operations | VCF | Status | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['release']} | {r['vcf_operations']} | {r.get('vcf', '')} | "
            f"{STATUSES[r['status']]} | {r.get('notes', '')} |"
        )
    if not full:
        lines += [
            "",
            "The status definitions, the full history and the support policy are in "
            "[docs/compatibility.md](docs/compatibility.md). If you run the tool on a version that is not "
            f"listed, please [file a compatibility report]({m['repo_url']}/issues/new?template=compatibility_report.yml); "
            "that is how rows move from untested to supported.",
        ]
    return "\n".join(lines)


def block_permissions(m: dict[str, Any], *, link: bool = True) -> str:
    p = m["permissions"]
    lines = [
        f"{p['summary']}",
        "",
        "| Item | Requirement |",
        "| --- | --- |",
        f"| Account | {p['account']} |",
        f"| Role | {p['role']} |",
    ]
    if p.get("scope"):
        lines.append(f"| Scope | {p['scope']} |")
    lines += [
        "",
        "The role needs these permissions and no others:",
        "",
        "| Area | Access | Why it is needed |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {x['area']} | {x['access']} | {x['reason']} |" for x in p["privileges"]]
    lines += [
        "",
        "The tool does not need any of the following. Treat a request for them as a bug.",
        "",
        *[f"- {x}" for x in p["not_required"]],
        "",
        "Network flows:",
        "",
        "| From | To | Port | Purpose |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {n['from']} | {n['to']} | {n['port']} | {n['purpose']} |" for n in p["network"]]
    if link:
        lines += [
            "",
            "How to create the service account and role: [docs/permissions.md](docs/permissions.md).",
        ]
    return "\n".join(lines)


def block_architecture(m: dict[str, Any]) -> str:
    approach = (m.get("management_pack") or {}).get("approach", "none")
    if m["kind"] == "management-pack" and approach == "mp-builder":
        diagram = """flowchart LR
  subgraph ops["VCF Operations 9.1.1+"]
    mpb["Management Pack Builder design"] --> pak["Installed management pack"]
  end
  proxy["Cloud proxy / collector"] -- "HTTPS, read-only account" --> target["Target system API"]
  pak -. runs on .-> proxy
  proxy -- "metrics, properties, relationships" --> ops"""
    elif m["kind"] == "management-pack":
        diagram = """flowchart LR
  subgraph ops["VCF Operations 9.1.1+"]
    pak["Management pack (.pak)"]
  end
  subgraph proxy["Cloud proxy"]
    adapter["Python adapter container"]
  end
  pak -. deploys .-> adapter
  adapter -- "HTTPS, read-only account" --> target["Target system API"]
  adapter -- "objects, metrics, events" --> ops"""
    elif m["kind"] == "agent":
        diagram = """flowchart LR
  agent["Agent (scheduled, read-only service account)"] -- "HTTPS 443, GET + read-only queries" --> api["VCF Operations Suite API 9.1.1+"]
  agent --> out["Findings: report / JSON / alerts you route"]
  api -. "nothing is written back" .-> agent"""
    else:
        diagram = """flowchart LR
  you["Operator workstation or jump host"] --> tool["Script"]
  tool -- "HTTPS 443, GET + read-only queries" --> api["VCF Operations Suite API 9.1.1+"]
  tool --> out["Report: terminal / JSON / CSV"]
  api -. "nothing is written back" .-> tool"""
    return f"```mermaid\n{diagram}\n```"


def block_footer(m: dict[str, Any]) -> str:
    return (
        f"## Licence and trademarks\n\n"
        f"{m['display_name']} is released under the [{m['licence']} licence](LICENSE). "
        f"Copyright {m['copyright_year']} {m['author']['name']}.\n\n"
        f"This is an independent community project by [{m['author']['name']}]({m['author']['url']}). "
        "It is not affiliated with, endorsed by or supported by Broadcom. VMware, VMware Cloud "
        "Foundation, VCF and VCF Operations are trademarks of Broadcom Inc. and/or its subsidiaries, "
        "used here only to describe compatibility. For product issues, contact Broadcom support.\n\n"
        f"<sub>More tools and write-ups at [djonko.dev]({m['author']['url']}) · "
        f"[{m['display_name']} project page]({m['project_page']})</sub>"
    )


def meta_module(m: dict[str, Any]) -> str:
    matrix = [
        {
            "release": r["release"],
            "vcf_operations": str(r["vcf_operations"]),
            "status": r["status"],
            "notes": r.get("notes", ""),
        }
        for r in m["compatibility"]["matrix"]
    ]
    return (
        f"# SPDX-FileCopyrightText: {m['copyright_year']} {m['author']['name']}\n"
        f"# SPDX-License-Identifier: {m['licence']}\n"
        '"""Generated by scripts/repokit.py render from tool.yaml. Do not edit by hand."""\n\n'
        f"NAME = {m['name']!r}\n"
        f"DISPLAY_NAME = {m['display_name']!r}\n"
        f"SLUG = {m['slug']!r}\n"
        f"SUMMARY = {' '.join(str(m['summary']).split())!r}\n"
        f"PROJECT_PAGE = {m['project_page']!r}\n"
        f"REPOSITORY = {m['repo_url']!r}\n"
        f"BASELINE = {str(m['compatibility']['baseline'])!r}\n"
        f"MATRIX = {json.dumps(matrix, indent=4, ensure_ascii=False)}\n"
    )


def licence_text(m: dict[str, Any]) -> str:
    text = read(ROOT / "licenses" / f"{m['licence']}.txt")
    return text.replace("{year}", str(m["copyright_year"])).replace("{holder}", m["author"]["name"])


def notice_text(m: dict[str, Any]) -> str:
    return (
        f"{m['display_name']}\n"
        f"Copyright {m['copyright_year']} {m['author']['name']}\n\n"
        f"This product is licensed under the Apache License, Version 2.0 (see LICENSE).\n"
        f"Project page: {m['project_page']}\n\n"
        "Independent community project. Not affiliated with, endorsed by or supported by Broadcom.\n"
        "VMware, VMware Cloud Foundation, VCF and VCF Operations are trademarks of Broadcom Inc.\n"
        "and/or its subsidiaries.\n"
    )


def banner_svg(m: dict[str, Any], *, dark: bool, height: int = 320) -> str:
    bg1, bg2 = ("#0b1220", "#0f2a33") if dark else ("#f8fafc", "#e6f4f1")
    ink, sub, muted = ("#f1f5f9", "#5eead4", "#94a3b8") if dark else ("#0f172a", "#0f766e", "#475569")
    line, node = ("#1e3a44", "#2dd4bf") if dark else ("#cbe7e1", "#0f766e")
    summary = textwrap.wrap(" ".join(str(m["summary"]).split()), 74)[:2]
    summary_svg = "".join(
        f'<text x="72" y="{214 + i * 30}" font-size="21" fill="{muted}">{escape(s)}</text>'
        for i, s in enumerate(summary)
    )
    pts = [(1010, 70), (1120, 120), (1060, 210), (1180, 245), (930, 170), (1210, 80), (1240, 185)]
    edges = [(0, 1), (1, 2), (2, 3), (0, 4), (4, 2), (1, 5), (3, 6), (2, 6)]
    graph = "".join(
        f'<line x1="{pts[a][0]}" y1="{pts[a][1]}" x2="{pts[b][0]}" y2="{pts[b][1]}" stroke="{line}" stroke-width="2"/>'
        for a, b in edges
    ) + "".join(
        f'<circle cx="{x}" cy="{y}" r="{9 if i == 2 else 6}" fill="{node}" opacity="{1 if i == 2 else 0.75}"/>'
        for i, (x, y) in enumerate(pts)
    )
    title_size = 60 if len(m["name"]) <= 22 else 46
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-label="{escape(m["display_name"])}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="{height}" rx="{20 if height == 320 else 0}" fill="url(#bg)"/>
  <g transform="translate(0 {(height - 320) // 2})">
  <rect x="40" y="56" width="6" height="208" rx="3" fill="{sub}"/>
  <g font-family="Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif">
    <text x="72" y="84" font-size="15" letter-spacing="3" fill="{muted}">{escape(m["author"]["name"].upper())} · TOOLS FOR VCF OPERATIONS</text>
    <text x="72" y="146" font-size="{title_size}" font-weight="700" fill="{ink}">{escape(m["name"])}</text>
    <text x="72" y="182" font-size="27" font-weight="600" fill="{sub}">{SUFFIX}</text>
    {summary_svg}
    <text x="1208" y="292" font-size="15" text-anchor="end" fill="{muted}">{escape(m["project_page"].removeprefix("https://"))}</text>
  </g>
  <g>{graph}</g>
  </g>
</svg>
"""


def social_svg(m: dict[str, Any]) -> str:
    """1280x640 social preview: the light banner on a full-bleed canvas."""
    return banner_svg(m, dark=False, height=640)


def project_card(m: dict[str, Any]) -> dict[str, Any]:
    p = m["permissions"]
    return {
        "schema": 1,
        "name": m["name"],
        "displayName": m["display_name"],
        "slug": m["slug"],
        "kind": m["kind"],
        "managementPackApproach": (m.get("management_pack") or {}).get("approach", "none"),
        "summary": " ".join(str(m["summary"]).split()),
        "description": " ".join(str(m["description"]).split()),
        "version": str(m["version"]),
        "licence": m["licence"],
        "author": m["author"],
        "baseline": str(m["compatibility"]["baseline"]),
        "compatibility": [
            {
                "release": str(r["release"]),
                "vcfOperations": str(r["vcf_operations"]),
                "vcf": str(r.get("vcf", "")),
                "status": r["status"],
                "notes": r.get("notes", ""),
            }
            for r in m["compatibility"]["matrix"]
        ],
        "permissions": {
            "summary": p["summary"],
            "account": p["account"],
            "role": p["role"],
            "privileges": [{k: v for k, v in x.items() if k != "example"} for x in p["privileges"]],
            "notRequired": p["not_required"],
        },
        "topics": m["topics"],
        "links": {
            "projectPage": m["project_page"],
            "repository": m["repo_url"],
            "releases": f"{m['repo_url']}/releases",
            "latestRelease": f"{m['repo_url']}/releases/latest",
            "issues": f"{m['repo_url']}/issues",
            "changelog": f"{m['repo_url']}/blob/main/CHANGELOG.md",
        },
        "notAffiliated": "Independent community project. Not affiliated with, endorsed by or supported by Broadcom.",
    }


# -------------------------------------------------------------------- render


BLOCK = "<!-- repokit:begin {0} -->\n{1}\n<!-- repokit:end {0} -->"


def replace_block(text: str, name: str, content: str, where: str) -> str:
    pattern = re.compile(
        rf"<!-- repokit:begin {re.escape(name)} -->.*?<!-- repokit:end {re.escape(name)} -->", re.S
    )
    if not pattern.search(text):
        raise SystemExit(f"{where}: missing block markers for '{name}'")
    return pattern.sub(lambda _: BLOCK.format(name, content), text, count=1)


def planned_outputs(m: dict[str, Any]) -> dict[Path, str | None]:
    """Every generated file and its expected content (None = must not exist)."""
    out: dict[Path, str | None] = {}

    readme = read(ROOT / "README.md")
    for name, content in (
        ("header", block_header(m)),
        ("compatibility", block_compat(m)),
        ("permissions", block_permissions(m)),
        ("architecture", block_architecture(m)),
        ("footer", block_footer(m)),
    ):
        readme = replace_block(readme, name, content, "README.md")
    out[ROOT / "README.md"] = readme

    docs = {
        "docs/compatibility.md": [("compatibility", block_compat(m, full=True))],
        "docs/permissions.md": [("permissions", block_permissions(m, link=False))],
        "docs/architecture.md": [("architecture", block_architecture(m))],
    }
    for path, blocks in docs.items():
        text = read(ROOT / path)
        for name, content in blocks:
            text = replace_block(text, name, content, path)
        out[ROOT / path] = text

    pkg = ROOT / "src" / m["package"]
    if pkg.is_dir():
        out[pkg / "_meta.py"] = meta_module(m)
    out[ROOT / "docs/assets/banner-light.svg"] = banner_svg(m, dark=False)
    out[ROOT / "docs/assets/banner-dark.svg"] = banner_svg(m, dark=True)
    out[ROOT / "docs/assets/social-preview.svg"] = social_svg(m)
    out[ROOT / "LICENSE"] = licence_text(m)
    out[ROOT / "NOTICE"] = notice_text(m) if m["licence"] == "Apache-2.0" else None

    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        text = read(pyproject)
        files = '["LICENSE", "NOTICE"]' if m["licence"] == "Apache-2.0" else '["LICENSE"]'
        text = re.sub(r'(?m)^license = ".*"$', f'license = "{m["licence"]}"', text)
        text = re.sub(r"(?m)^license-files = \[.*\]$", f"license-files = {files}", text)
        text = re.sub(
            r'(?m)^description = ".*"$',
            lambda _: f"description = {json.dumps(' '.join(str(m['summary']).split()))}",
            text,
        )
        out[pyproject] = text
    return out


def cmd_render(args: argparse.Namespace) -> int:
    m = load_meta()
    errors, _ = validate_meta(m)
    if errors:
        print("\n".join(f"✖ {e}" for e in errors))
        return 1
    stale = []
    for path, content in planned_outputs(m).items():
        current = read(path) if path.exists() else None
        if current == content:
            continue
        stale.append(path)
        if args.check:
            if content is None:
                print(f"✖ {rel(path)} should not exist for licence {m['licence']}")
            else:
                diff = difflib.unified_diff(
                    (current or "").splitlines(),
                    content.splitlines(),
                    f"{rel(path)} (committed)",
                    f"{rel(path)} (from tool.yaml)",
                    lineterm="",
                    n=1,
                )
                print("\n".join(list(diff)[:40]))
        elif content is None:
            path.unlink()
            print(f"removed {rel(path)}")
        else:
            write(path, content)
            print(f"wrote   {rel(path)}")
    if args.check and stale:
        print(f"\n✖ {len(stale)} generated file(s) out of date. Run: python scripts/repokit.py render")
        return 1
    if not stale:
        print("Generated files are up to date.")
    return 0


# --------------------------------------------------------------------- check


def cmd_check(args: argparse.Namespace) -> int:
    m = load_meta()
    errors, warnings = validate_meta(m)
    if errors:
        return _report(errors, warnings, args.strict)

    # Generated content in sync with tool.yaml.
    for path, content in planned_outputs(m).items():
        current = read(path) if path.exists() else None
        if current != content:
            errors.append(f"{rel(path)} is out of date with tool.yaml (run: repokit.py render)")

    # One version everywhere.
    init = ROOT / "src" / m["package"] / "__init__.py"
    if m["kind"] != "management-pack" or init.exists():
        found = re.search(r'__version__ = "([^"]+)"', read(init)) if init.exists() else None
        if not found:
            errors.append(f"{rel(init)}: no __version__")
        elif found[1] != str(m["version"]):
            errors.append(f"{rel(init)} version {found[1]} != tool.yaml {m['version']}")
    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        text = read(pyproject)
        if f'name = "{m["github"]["repo"]}"' not in text:
            errors.append(f"pyproject.toml: project name should be '{m['github']['repo']}'")
        if f'{m["slug"]} = "{m["package"]}.cli:main"' not in text:
            errors.append(
                f"pyproject.toml: console script '{m['slug']}' should point at {m['package']}.cli:main"
            )

    # Changelog.
    changelog = read(ROOT / "CHANGELOG.md")
    if "## [Unreleased]" not in changelog:
        errors.append("CHANGELOG.md: keep an '## [Unreleased]' section at the top")

    # SPDX headers match the licence.
    spdx = f"SPDX-License-Identifier: {m['licence']}"
    for path in repo_files():
        if path.suffix in {".py", ".ps1", ".psm1", ".sh"} and not rel(path).startswith("licenses/"):
            head = "\n".join(read(path).splitlines()[:4])
            if "SPDX-License-Identifier" not in head:
                errors.append(f"{rel(path)}: missing SPDX header ({spdx})")
            elif spdx not in head:
                errors.append(f"{rel(path)}: SPDX header does not say {m['licence']}")

    # Naming: never "VCF <Tool>".
    bad = re.compile(rf"\bVCF {re.escape(m['name'])}\b")
    for path in text_files():
        for i, line in enumerate(read(path).splitlines(), 1):
            if bad.search(line):
                errors.append(f"{rel(path)}:{i}: say '{m['display_name']}', not 'VCF {m['name']}'")

    # Required reader-facing statements.
    readme = read(ROOT / "README.md")
    if "not affiliated with" not in readme.lower():
        errors.append("README.md: the not-affiliated note is missing")
    if m["project_page"] not in readme:
        errors.append(f"README.md: link to {m['project_page']}")

    # Template leftovers.
    repo_env = os.environ.get("GITHUB_REPOSITORY", "")
    if m.get("template"):
        if repo_env and repo_env.lower() != str(m.get("template_repository", "")).lower():
            errors.append("tool.yaml: still a template. Run: python scripts/repokit.py init --name '<Tool>'")
    else:
        for path in text_files():
            if rel(path) in {"scripts/repokit.py", "tool.yaml"} or rel(path).startswith("tests/"):
                continue
            text = read(path)
            for token in ("Template Tool", "template-tool", "template_tool"):
                if token in text:
                    errors.append(f"{rel(path)}: leftover template name '{token}'")
                    break
        if (ROOT / "docs/template-guide.md").exists():
            warnings.append("docs/template-guide.md: delete it once the tool is set up")
        if "TODO" in readme:
            warnings.append("README.md: TODOs remain")

    return _report(errors, warnings, args.strict)


def _report(errors: list[str], warnings: list[str], strict: bool) -> int:
    for e in errors:
        print(f"✖ {e}")
    for w in warnings:
        print(f"{'✖' if strict else '!'} {w}")
    failed = bool(errors) or (strict and bool(warnings))
    if not failed:
        print(
            f"✔ Repository rules pass{' (strict)' if strict else ''}"
            f"{f' with {len(warnings)} warning(s)' if warnings else ''}."
        )
    return 1 if failed else 0


# ---------------------------------------------------------------------- init


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def set_yaml_scalar(text: str, key: str, value: str, *, indent: str = "") -> str:
    pattern = re.compile(rf"(?m)^({indent}{re.escape(key)}:)[ \t]*[^#\n]*?([ \t]+#.*)?$")
    if not pattern.search(text):
        raise SystemExit(f"tool.yaml: cannot find '{indent}{key}:'")
    return pattern.sub(lambda mt: f"{mt[1]} {value}{mt[2] or ''}", text, count=1)


def cmd_init(args: argparse.Namespace) -> int:
    m = load_meta()
    if not m.get("template"):
        print("This repository is already initialised (tool.yaml template: false).")
        return 1
    name = re.sub(rf"\s*{SUFFIX}$", "", args.name.strip(), flags=re.I)
    if re.match(r"(?i)^vcf\b", name):
        print(f"✖ '{name}' starts with VCF. Name it '<Tool> {SUFFIX}', e.g. 'Capacity Lens'.")
        return 1
    slug = args.slug or slugify(name)
    if not SLUG.match(slug):
        print(f"✖ slug '{slug}' must be lowercase-kebab-case")
        return 1
    package = slug.replace("-", "_")
    repo = args.repo or f"{slug}-{slugify(SUFFIX)}"
    owner = args.owner or m["github"]["owner"]

    replacements = [
        ("template-tool-for-vcf-operations", repo),
        ("Template Tool", name),
        ("template-tool", slug),
        ("template_tool", package),
    ]
    if owner != m["github"]["owner"]:
        replacements += [
            (f"github.com/{m['github']['owner']}/", f"github.com/{owner}/"),
            (f"@{m['github']['owner']}", f"@{owner}"),
        ]
    for path in text_files():
        if rel(path) in {"scripts/repokit.py"} or rel(path).startswith("licenses/"):
            continue
        text = original = read(path)
        for old, new in replacements:
            text = text.replace(old, new)
        if text != original:
            write(path, text)

    src = ROOT / "src" / "template_tool"
    if src.is_dir() and package != "template_tool":
        src.rename(ROOT / "src" / package)

    tool = read(ROOT / "tool.yaml")
    tool = set_yaml_scalar(tool, "template", "false")
    tool = set_yaml_scalar(tool, "version", "0.1.0")
    tool = set_yaml_scalar(tool, "kind", args.kind)
    tool = set_yaml_scalar(tool, "owner", owner, indent="  ")
    tool = set_yaml_scalar(tool, "copyright_year", str(dt.date.today().year))
    if args.summary:
        tool = set_yaml_scalar(tool, "summary", json.dumps(args.summary))
    if args.kind == "management-pack":
        tool = set_yaml_scalar(tool, "approach", args.mp_approach or "mp-builder", indent="  ")
    write(ROOT / "tool.yaml", tool)

    readme = read(ROOT / "README.md")
    readme = re.sub(
        r"<!-- repokit:begin template-notice -->.*?<!-- repokit:end template-notice -->\n*",
        "",
        readme,
        flags=re.S,
    )
    write(ROOT / "README.md", readme)
    (ROOT / "docs/template-guide.md").unlink(missing_ok=True)

    today = dt.date.today().isoformat()
    write(ROOT / "CHANGELOG.md", CHANGELOG_FRESH.format(today=today))
    cmd_render(argparse.Namespace(check=False))
    print(
        textwrap.dedent(f"""
        ✔ Initialised {name} {SUFFIX}
          package  src/{package}    CLI  {slug}    repo  {owner}/{repo}
          project page  {PROJECTS_URL}{slug}

        Next:
          1. Edit tool.yaml (summary, description, compatibility, permissions), then: python scripts/repokit.py render
          2. python scripts/repokit.py check && pytest
          3. Commit, push, then apply repository settings: scripts/configure-repo.sh
    """)
    )
    return 0


CHANGELOG_FRESH = """# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffold from the VCF Operations tool template ({today}).
"""


# ------------------------------------------------------------------- licence


def cmd_licence(args: argparse.Namespace) -> int:
    m = load_meta()
    new = args.licence
    old = m["licence"]
    write(ROOT / "tool.yaml", set_yaml_scalar(read(ROOT / "tool.yaml"), "licence", new))
    changed = 0
    for path in repo_files():
        if path.suffix in {".py", ".ps1", ".psm1", ".sh"}:
            text = read(path)
            updated = text.replace(f"SPDX-License-Identifier: {old}", f"SPDX-License-Identifier: {new}")
            if updated != text:
                write(path, updated)
                changed += 1
    print(f"Licence {old} -> {new}; updated SPDX headers in {changed} file(s).")
    return cmd_render(argparse.Namespace(check=False))


# ---------------------------------------------------------------- versioning


def cmd_bump(args: argparse.Namespace) -> int:
    version = args.version.removeprefix("v")
    if not SEMVER.match(version):
        print(f"✖ '{version}' is not a semantic version")
        return 1
    m = load_meta()
    changelog = read(ROOT / "CHANGELOG.md")
    if f"## [{version}]" in changelog:
        print(f"✖ CHANGELOG.md already has a {version} section")
        return 1
    unreleased = _section(changelog, "Unreleased")
    if not unreleased.strip():
        print("✖ The Unreleased section is empty. Describe the changes first.")
        return 1

    today = dt.date.today().isoformat()
    changelog = changelog.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{version}] - {today}", 1)
    base = m["repo_url"]
    previous = re.findall(r"(?m)^## \[(\d+\.\d+\.\d+[^\]]*)\]", changelog)
    prev = previous[1] if len(previous) > 1 else None
    changelog = re.sub(r"(?m)^\[Unreleased\]: .*\n?", "", changelog).rstrip() + "\n"
    links = f"\n[Unreleased]: {base}/compare/v{version}...HEAD\n"
    links += (
        f"[{version}]: {base}/compare/v{prev}...v{version}\n"
        if prev
        else f"[{version}]: {base}/releases/tag/v{version}\n"
    )
    # keep older link references, drop a duplicate for this version
    changelog = re.sub(rf"(?m)^\[{re.escape(version)}\]: .*\n?", "", changelog)
    body, refs = _split_refs(changelog)
    write(ROOT / "CHANGELOG.md", body.rstrip() + "\n" + links + refs)

    write(ROOT / "tool.yaml", set_yaml_scalar(read(ROOT / "tool.yaml"), "version", version))
    init = ROOT / "src" / m["package"] / "__init__.py"
    if init.exists():
        write(init, re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', read(init)))
    cmd_render(argparse.Namespace(check=False))
    print(
        textwrap.dedent(f"""
        ✔ Version {version}. Review, then:
          git commit -am "chore(release): v{version}"
          git tag -s v{version} -m "v{version}"     # or -a if you do not sign tags
          git push --follow-tags
    """)
    )
    return 0


def _split_refs(text: str) -> tuple[str, str]:
    lines = text.rstrip().splitlines()
    refs = []
    while lines and re.match(r"^\[[^\]]+\]: ", lines[-1]):
        refs.insert(0, lines.pop())
    return "\n".join(lines) + "\n", ("\n".join(refs) + "\n" if refs else "")


def _section(changelog: str, name: str) -> str:
    match = re.search(rf"(?ms)^## \[{re.escape(name)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", changelog)
    return match[1].strip() if match else ""


def cmd_verify_tag(args: argparse.Namespace) -> int:
    m = load_meta()
    version = args.tag.removeprefix("refs/tags/").removeprefix("v")
    problems = []
    if not args.tag.removeprefix("refs/tags/").startswith("v"):
        problems.append(f"tag '{args.tag}' must look like v1.2.3")
    if version != str(m["version"]):
        problems.append(f"tag {version} != tool.yaml version {m['version']} (run: repokit.py bump {version})")
    if not _section(read(ROOT / "CHANGELOG.md"), version):
        problems.append(f"CHANGELOG.md has no notes for {version}")
    for p in problems:
        print(f"✖ {p}")
    if not problems:
        print(f"✔ Tag v{version} matches tool.yaml and CHANGELOG.md")
    return 1 if problems else 0


def cmd_release_notes(args: argparse.Namespace) -> int:
    m = load_meta()
    version = args.version.removeprefix("v")
    notes = _section(read(ROOT / "CHANGELOG.md"), version)
    if not notes:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1
    owner_repo = m["owner_repo"]
    at_tag = f"{m['repo_url']}/blob/v{version}"
    compat = block_compat(m).replace("(docs/compatibility.md)", f"({at_tag}/docs/compatibility.md)")
    parts = [
        notes,
        "## Compatibility",
        compat,
        "## Verify this download",
        "Every asset is listed in `SHA256SUMS` and carries a signed build-provenance attestation.",
        "```sh\n"
        "sha256sum --check --ignore-missing SHA256SUMS\n"
        f"gh attestation verify <file> --repo {owner_repo}\n"
        "```",
        "The software bill of materials is attached as `sbom.spdx.json`. "
        f"Minimum permissions for this release: [docs/permissions.md]({at_tag}/docs/permissions.md).",
        "---",
        f"[Project page]({m['project_page']}) · [Documentation]({m['repo_url']}/tree/v{version}/docs) · "
        f"[Changelog]({at_tag}/CHANGELOG.md)",
        "<sub>Independent community project. Not affiliated with, endorsed by or supported by Broadcom.</sub>",
    ]
    print("\n\n".join(parts))
    return 0


# ----------------------------------------------------------- release assets


def cmd_project_json(args: argparse.Namespace) -> int:
    card = json.dumps(project_card(load_meta()), indent=2, ensure_ascii=False) + "\n"
    if args.output in (None, "-"):
        sys.stdout.write(card)
    else:
        write(Path(args.output), card)
        print(f"wrote {args.output}")
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    m = load_meta()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    added = []
    ps = ROOT / "powershell"
    if ps.is_dir() and any(ps.rglob("*.ps*1")):
        target = outdir / f"{m['github']['repo']}-{m['version']}-powershell.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(ps.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(ps.parent).as_posix())
            for extra in ("LICENSE", "NOTICE", "README.md"):
                if (ROOT / extra).exists():
                    zf.write(ROOT / extra, f"powershell/{extra}")
        added.append(target.name)
    mp_dist = ROOT / "management-pack" / "dist"
    if mp_dist.is_dir():
        for f in sorted(mp_dist.iterdir()):
            if f.suffix.lower() in {".pak", ".json", ".zip"}:
                shutil.copy2(f, outdir / f.name)
                added.append(f.name)
    if m["kind"] == "management-pack" and not any(a.endswith(".pak") for a in added):
        print("✖ kind is management-pack but management-pack/dist/ has no .pak to release")
        return 1
    print("bundled: " + (", ".join(added) if added else "nothing extra (Python package only)"))
    return 0


# -------------------------------------------------------------------- privacy


PRIVACY_RULES: list[tuple[str, re.Pattern[str], Any]] = [
    (
        "proprietary marking",
        re.compile(r"(?i)\b(proprietary|confidential|internal[ -]only|do not distribute)\b"),
        None,
    ),
    (
        "email address",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
        lambda s: (
            re.search(r"@(example\.(com|org|net)|rainpole\.io|users\.noreply\.github\.com)$", s, re.I)
            or s.lower().startswith(("noreply@", "git@"))
        ),
    ),
    (
        "IPv4 address",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b"),
        lambda s: (
            s.startswith(("192.0.2.", "198.51.100.", "203.0.113.", "127.0.0.1", "0.0.0.0"))
            or int(s.split(".")[0]) <= 9
        ),
    ),  # version strings such as 9.1.1.0
    (
        # Not after "[" (a TOML table such as [profiles.lab]) and not before "(" (a
        # call such as Path.home()), so code and config examples do not trip it.
        "internal hostname",
        re.compile(
            r"(?i)(?<![\[\w.-])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:corp|lan|intra|internal|home|lab)\b(?![(\w-])"
        ),
        None,
    ),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"), None),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), None),
    (
        "hard-coded password",
        re.compile(r"""(?i)\bpass(?:word|wd)?\s*[:=]\s*["'][^"'\s<>{}$]{6,}["']"""),
        None,
    ),
]
PRIVACY_SKIP = {"LICENSE", "NOTICE", "scripts/repokit.py"}


def private_terms() -> list[str]:
    """Names that must never appear, kept out of the repository itself.

    Sources: the PRIVACY_TERMS environment variable (a CI secret, one term per
    line or comma-separated) and an untracked .privacy-terms file.
    """
    raw = os.environ.get("PRIVACY_TERMS", "")
    local = ROOT / ".privacy-terms"
    if local.exists():
        raw += "\n" + read(local)
    return [t.strip() for t in re.split(r"[\n,]", raw) if t.strip() and not t.strip().startswith("#")]


def cmd_privacy(args: argparse.Namespace) -> int:
    rules = list(PRIVACY_RULES)
    terms = private_terms()
    if terms:
        rules.append(
            ("private term", re.compile(r"(?i)\b(" + "|".join(map(re.escape, terms)) + r")\b"), None)
        )
    paths = [Path(p).resolve() for p in args.paths] if args.paths else text_files()
    hits = 0
    for path in paths:
        files = [f for f in path.rglob("*") if f.is_file()] if path.is_dir() else [path]
        for f in files:
            try:
                name = rel(f)
            except ValueError:
                name = str(f)
            if name in PRIVACY_SKIP or name.startswith(("licenses/", ".git/")) or not _is_text(f):
                continue
            for i, line in enumerate(read(f).splitlines(), 1):
                if "privacy: allow" in line:
                    continue
                for label, pattern, allow in rules:
                    for match in pattern.finditer(line):
                        if allow and allow(match[0]):
                            continue
                        hits += 1
                        shown = (
                            "<redacted>"
                            if label
                            in {
                                "private term",
                                "GitHub token",
                                "AWS key",
                                "private key",
                                "hard-coded password",
                            }
                            else match[0]
                        )
                        print(f"{name}:{i}: [{label}] {shown}")
    note = f" ({len(terms)} private term(s) checked)" if terms else " (no PRIVACY_TERMS configured)"
    print(f"\n✖ {hits} finding(s){note}" if hits else f"✔ Privacy scan clean{note}")
    return 1 if hits else 0


def cmd_meta(args: argparse.Namespace) -> int:
    value: Any = load_meta()
    for part in args.field.split("."):
        value = value[part]
    print(value if isinstance(value, str) else json.dumps(value))
    return 0


# ---------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="repokit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("render", help="regenerate files from tool.yaml")
    p.add_argument("--check", action="store_true", help="fail instead of writing")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("check", help="run every repository rule")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors (releases)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("init", help="turn the template into a named tool")
    p.add_argument("--name", required=True, help="short name, e.g. 'Capacity Lens'")
    p.add_argument("--slug")
    p.add_argument("--repo", help="repository name (default: <slug>-for-vcf-operations)")
    p.add_argument("--owner", help="GitHub owner (default: from tool.yaml)")
    p.add_argument("--kind", choices=sorted(KINDS), default="script")
    p.add_argument("--mp-approach", choices=["mp-builder", "integration-sdk"])
    p.add_argument("--summary")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("licence", aliases=["license"], help="switch the licence")
    p.add_argument("licence", choices=sorted(LICENCES))
    p.set_defaults(func=cmd_licence)

    p = sub.add_parser("bump", help="set the version and cut the changelog")
    p.add_argument("version")
    p.set_defaults(func=cmd_bump)

    p = sub.add_parser("verify-tag", help="release gate")
    p.add_argument("tag")
    p.set_defaults(func=cmd_verify_tag)

    p = sub.add_parser("release-notes", help="print release notes")
    p.add_argument("version")
    p.set_defaults(func=cmd_release_notes)

    p = sub.add_parser("project-json", help="write the djonko.dev project card")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_project_json)

    p = sub.add_parser("bundle", help="add extra release assets")
    p.add_argument("--outdir", default="dist")
    p.set_defaults(func=cmd_bundle)

    p = sub.add_parser("privacy", help="scan for personal data, secrets and unpublishable material")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_privacy)

    p = sub.add_parser("meta", help="print a tool.yaml field")
    p.add_argument("field")
    p.set_defaults(func=cmd_meta)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
