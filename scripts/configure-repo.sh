#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jay Djonko
# SPDX-License-Identifier: Apache-2.0
#
# Apply the settings every "<Tool> for VCF Operations" repository shares.
# Idempotent: safe to run again after changing tool.yaml.
# Needs: gh (signed in as a repository admin), python with PyYAML.
set -euo pipefail

cd "$(dirname "$0")/.."
meta() { python scripts/repokit.py meta "$1"; }

owner="$(meta github.owner)"
repo="$(meta github.repo)"
full="$owner/$repo"
slug="$(meta slug)"

echo "Configuring $full"

topic_args=()
while IFS= read -r t; do topic_args+=(--add-topic "$t"); done < <(python -c 'import json,sys; [print(t) for t in json.loads(sys.argv[1])]' "$(meta topics)")

gh repo edit "$full" \
  --description "$(meta summary)" \
  --homepage "https://djonko.dev/projects/$slug" \
  "${topic_args[@]}" \
  --enable-issues \
  --enable-wiki=false \
  --enable-projects=false \
  --enable-squash-merge \
  --enable-merge-commit=false \
  --enable-rebase-merge=false \
  --delete-branch-on-merge \
  --allow-update-branch

echo "- security: vulnerability alerts, Dependabot security updates, private vulnerability reporting"
gh api -X PUT "repos/$full/vulnerability-alerts" --silent
gh api -X PUT "repos/$full/automated-security-fixes" --silent
gh api -X PUT "repos/$full/private-vulnerability-reporting" --silent

echo "- labels"
python -c 'import json; [print(l["name"], l["color"], l["description"], sep="\t") for l in json.load(open(".github/labels.json"))]' |
  while IFS=$'\t' read -r name color description; do
    gh label create "$name" --repo "$full" --color "$color" --description "$description" --force >/dev/null
  done

echo "- rulesets"
existing="$(gh api "repos/$full/rulesets" --jq '.[] | "\(.id)\t\(.name)"')"
for file in .github/rulesets/*.json; do
  name="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$file")"
  id="$(printf '%s\n' "$existing" | awk -F'\t' -v n="$name" '$2 == n {print $1}')"
  if [[ -n "$id" ]]; then
    gh api -X PUT "repos/$full/rulesets/$id" --input "$file" --silent && echo "  updated: $name"
  else
    gh api -X POST "repos/$full/rulesets" --input "$file" --silent && echo "  created: $name"
  fi
done

cat <<NEXT

Done. Remaining one-off steps in the GitHub UI:
  - Settings > General > Social preview: upload a PNG of docs/assets/social-preview.svg
  - Settings > Secrets and variables > Actions: add PRIVACY_TERMS
  - Settings > General > Releases: enable immutable releases if offered
NEXT
