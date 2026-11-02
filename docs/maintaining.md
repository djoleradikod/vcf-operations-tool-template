# Maintaining

## repokit

`scripts/repokit.py` keeps the repository consistent. `tool.yaml` is the single source of truth, and
anything a reader sees in more than one place is generated from it, so the README, the docs and the
project page cannot disagree about versions or permissions.

| Command | What it does |
| --- | --- |
| `repokit.py render` | Regenerates the README header, compatibility, permissions, architecture and footer blocks, the matching blocks in `docs/`, both banners, `LICENSE`/`NOTICE`, the licence fields in `pyproject.toml`, and `src/<package>/_meta.py`. |
| `repokit.py render --check` | Shows a diff and fails if anything is stale. |
| `repokit.py check` | All repository rules (below). CI runs it on every push. |
| `repokit.py check --strict` | Warnings become errors. The release workflow runs this. |
| `repokit.py licence MIT` | Switches the licence: `LICENSE`, `NOTICE`, every SPDX header, `pyproject.toml`, the badge. |
| `repokit.py bump 1.2.0` | Sets the version everywhere and dates the changelog section. |
| `repokit.py release-notes 1.2.0` | Prints the release notes the workflow publishes. |
| `repokit.py project-json -o card.json` | Writes the djonko.dev project card. |
| `repokit.py privacy` | Scans for personal data, secrets and material not meant for publication. |

Only edit outside the `<!-- repokit:begin … -->` / `<!-- repokit:end … -->` markers; the content
between them is overwritten.

## Rules that `check` enforces

- Naming: `<Tool> for VCF Operations`, never `VCF <Tool>`, anywhere in the repository.
- The not-affiliated note and the djonko.dev project page link are in the README.
- The compatibility baseline is 9.1.1 or later, every row has a valid status, and at least one is tested.
- The permission model is read-only, never mentions an admin role, and has no `example: true` rows at release.
- One version across `tool.yaml` and the package; the changelog has an Unreleased section.
- Every code file has an SPDX header that matches the licence.
- Generated files match `tool.yaml`.
- No template names are left after `init`.

## Privacy scan

`repokit.py privacy` flags e-mail addresses, IP addresses, internal host names, restrictive document
markings, private keys, tokens and hard-coded passwords. Use `rainpole.io` and the documentation IP
ranges in examples.

Some values identify no one and are accepted:

| Kind | Accepted |
| --- | --- |
| IPv4 | Documentation ranges 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24 (RFC 5737); the benchmarking range 198.18.0.0/15 (RFC 2544), which VCF also uses internally; loopback 127.0.0.0/8; 0.0.0.0. Addresses and CIDR blocks are both checked. |
| E-mail | `example.com`, `example.org`, `example.net`, `rainpole.io`, the default SSO domain `vsphere.local`, GitHub `noreply` addresses. |

An account at `vsphere.local` can still carry a person's name, for example `jsmith@vsphere.local`.
Use role names such as `administrator@vsphere.local` or `svc-vcfops-ro@vsphere.local` in examples.

Names that must never appear are kept out of the repository. Put them, one per line, in either:

- the `PRIVACY_TERMS` repository secret (CI reads it), or
- an untracked `.privacy-terms` file for local runs (already in `.gitignore`).

Add `privacy: allow` to a line to accept a deliberate finding.

## Repository settings

`scripts/configure-repo.sh` applies the settings every repository in the family shares: description,
homepage and topics from `tool.yaml`, squash-merge only, private vulnerability reporting, Dependabot
security updates, labels, and rulesets that protect `main` and release tags. It needs the GitHub CLI,
signed in as a repository admin.

```sh
scripts/configure-repo.sh            # uses owner/repo from tool.yaml
```
