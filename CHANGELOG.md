# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository template: single-source `tool.yaml`, generated README and docs blocks, read-only
  Suite API client, CI, CodeQL, and a signed release pipeline.
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

### Fixed

- `--ca-bundle` and `--insecure` were ignored when `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE` was
  set, because `requests` lets those variables override the session setting. The setting is now
  passed with every request.
- The privacy scan no longer reports TOML table names such as `[profiles.lab]` or calls such as
  `Path.home()` as internal host names.
