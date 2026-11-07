# Maintaining

## The gate

This repository has no hosted CI, and repositories made from it should not add any. Nothing runs
automatically on a push or pull request, so run the gate yourself before every merge, including
Dependabot pull requests:

```sh
make check && make build
```

`make check` runs ruff, shellcheck, the tests with coverage, the privacy scan and the repository rules.
`make build` builds the package, runs `twine check` and writes the release assets to `dist/`.

### What the gate does not cover

| Check | Status | What to do |
| --- | --- | --- |
| Other Python versions and operating systems | The gate tests only the Python you run it on. The package declares 3.10 and later. | Before a release, repeat `make test` in a virtual environment for each Python you can get, and on Windows or macOS if you have them. On Python 3.11 and later, the `tomli` import used on 3.10 never runs. |
| CodeQL | Not replaced. No equivalent static security analysis runs. | Ruff covers lint only. Review changes to credential, TLS and request handling by hand. |
| PowerShell lint (PSScriptAnalyzer) | Not in the gate. | If the repository has `.ps1` files, run `Invoke-ScriptAnalyzer -Path . -Recurse -Severity Warning,Error -EnableExit` in PowerShell. |
| Build provenance | Not replaced. See [Releasing](releasing.md#verify-a-release). | Sign release tags. |

## repokit

`scripts/repokit.py` keeps the repository consistent. `tool.yaml` is the single source of truth, and
anything a reader sees in more than one place is generated from it, so the README, the docs and the
project page cannot disagree about versions or permissions.

| Command | What it does |
| --- | --- |
| `repokit.py render` | Regenerates the README header, compatibility, permissions, architecture and footer blocks, the matching blocks in `docs/`, both banners, `LICENSE`/`NOTICE`, the licence fields in `pyproject.toml`, and `src/<package>/_meta.py`. |
| `repokit.py render --check` | Shows a diff and fails if anything is stale. |
| `repokit.py check` | All repository rules (below). `make check` runs it. |
| `repokit.py check --strict` | Warnings become errors. `scripts/release.sh` runs this. |
| `repokit.py licence MIT` | Switches the licence: `LICENSE`, `NOTICE`, every SPDX header, `pyproject.toml`, the badge. |
| `repokit.py bump 1.2.0` | Sets the version everywhere and dates the changelog section. |
| `repokit.py release-notes 1.2.0` | Prints the release notes. `--sbom` adds the line saying an SBOM is attached. |
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

- an untracked `.privacy-terms` file (already in `.gitignore`), or
- the `PRIVACY_TERMS` environment variable.

Without one of these the scan cannot look for those names, so set one up on the machine you merge
and release from.

Add `privacy: allow` to a line to accept a deliberate finding.

## Repository settings

`scripts/configure-repo.sh` applies the settings every repository in the family shares: description,
homepage and topics from `tool.yaml`, squash-merge only, private vulnerability reporting, Dependabot
security updates, labels, and rulesets that protect `main` and release tags. It needs the GitHub CLI,
signed in as a repository admin.

```sh
scripts/configure-repo.sh            # uses owner/repo from tool.yaml
```
