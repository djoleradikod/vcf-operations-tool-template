# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository template: single-source `tool.yaml`, generated README and docs blocks, read-only
  Suite API client.
- Connection profiles in a shared TOML file (`~/.config/vcfops/config.toml`), selected with
  `--profile` or `VCFOPS_PROFILE`, and a `profiles` command to show them. Passwords and TLS
  bypass are refused in the file; `password_command` reads the password from a secret manager.
- `inventory` command: lists objects with kind, adapter and health, with filters, `--limit`, and
  text, JSON or CSV output. CSV cells that a spreadsheet would run as formulas are neutralised.
- Bounded retries with exponential backoff and jitter on HTTP 429, 502, 503, 504 and failed
  connections, honouring `Retry-After`. Read timeouts and TLS failures are not retried.
- Paging helper that stops on `totalCount`, not on a short page, so a server-side page-size cap
  cannot truncate results.
- Global options are accepted before or after the command name; `-o` is short for `--output`.
- Dev container for VS Code and GitHub Codespaces.
- Optional `boundary` and `architecture` keys in `tool.yaml` for tools that read more than
  VCF Operations: they replace the README header's read-only sentence and the default
  diagram. `project.json` gains a `boundary` field (schema 1, additive).
- `scripts/release.sh` (`make release VERSION=1.2.0`) checks and builds release assets locally. It
  creates no tag and publishes nothing.

### Changed

- `make lint` also runs shellcheck, installed with the dev extras, and `make build` also runs
  `twine check --strict`.
- `repokit.py release-notes` mentions an SBOM only when given `--sbom`.
- `repokit.py check` spots a copy of the template that skipped `init` from the name of the `origin`
  remote, not from `GITHUB_REPOSITORY`.

### Removed

- GitHub Actions workflows (CI, CodeQL and release), the CI badge, the required "CI OK" check in the
  `main` ruleset, and Dependabot updates for Actions. `make check && make build` is now the gate.
  CodeQL, the Python and operating-system test matrix, PSScriptAnalyzer and build-provenance
  attestations have no replacement; see `docs/maintaining.md`. Releases no longer carry an
  attestation, and carry an SBOM only if `syft` is installed where they are built.

### Fixed

- `--ca-bundle` and `--insecure` were ignored when `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE` was
  set, because `requests` lets those variables override the session setting. The setting is now
  passed with every request.
- The privacy scan accepts the RFC 2544 benchmarking range 198.18.0.0/15, all of loopback
  127.0.0.0/8 and `@vsphere.local` addresses, none of which identify anyone. IPv4 ranges are
  now checked as networks, so CIDR blocks inside an accepted range pass too.
- The privacy scan no longer reports TOML table names such as `[profiles.lab]` or calls such as
  `Path.home()` as internal host names.
