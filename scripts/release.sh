#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
#
# Build and check the assets for a release, on this machine, from a clean commit.
# Creates no tag and publishes nothing: it prints those commands for you to run.
# Needs: the dev extras (pip install -e ".[dev]"). syft is optional, for the SBOM.
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PY:-python}"

if [[ $# -ne 1 ]]; then
  echo "usage: scripts/release.sh VERSION    (for example 1.2.0 or 1.2.0-rc.1)" >&2
  exit 2
fi
version="${1#v}"
tag="v$version"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit first, so the assets match a commit." >&2
  exit 1
fi
if git rev-parse --quiet --verify "refs/tags/$tag" >/dev/null &&
  [[ "$(git rev-parse "$tag^{commit}")" != "$(git rev-parse HEAD)" ]]; then
  echo "Tag $tag exists and points at another commit. Never move a tag: fix forward." >&2
  exit 1
fi

echo "== Gate: tag, version and changelog"
"$PY" scripts/repokit.py verify-tag "$tag"

echo "== Gate: repository rules (strict) and privacy scan"
"$PY" scripts/repokit.py check --strict
"$PY" scripts/repokit.py privacy

echo "== Gate: tests"
"$PY" -m pytest -q

echo "== Build"
rm -rf dist
"$PY" -m build --outdir dist
"$PY" -m twine check --strict dist/*
"$PY" scripts/repokit.py bundle --outdir dist
"$PY" scripts/repokit.py project-json -o dist/project.json

echo "== Software bill of materials"
notes_flags=()
if command -v syft >/dev/null; then
  syft scan dir:. --exclude './dist/**' --exclude './.venv/**' --output "spdx-json=dist/sbom.spdx.json"
  notes_flags+=(--sbom)
else
  echo "WARNING: syft is not installed, so this release has no SBOM." >&2
  echo "         The release notes will not claim one. Install syft and rerun to add it." >&2
fi

"$PY" scripts/repokit.py release-notes "$tag" "${notes_flags[@]+"${notes_flags[@]}"}" >release-notes.md

echo "== Checksums"
(cd dist && sha256sum -- * >SHA256SUMS && cat SHA256SUMS)

title="$("$PY" scripts/repokit.py meta display_name) $tag"
kind="--latest"
if [[ "$version" == *-* ]]; then kind="--prerelease"; fi

cat <<NEXT

Assets are in dist/ and the notes are in release-notes.md. Nothing has been tagged or published.
Look them over, then run:

  git tag -s $tag -m "$tag"      # -a if you do not sign tags
  git push origin HEAD $tag
  gh release create $tag dist/* --verify-tag --title "$title" --notes-file release-notes.md $kind
NEXT
