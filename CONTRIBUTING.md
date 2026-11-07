# Contributing

The contribution with the most value is a compatibility report. If you run the tool against a VCF
Operations version that is not in the matrix, [report what happened](../../issues/new?template=compatibility_report.yml).
Fixes and improvements are also welcome, as long as the tool stays read-only and keeps to the
minimum permissions.

## Ground rules

- No change may add a call that changes state. A new entry on the client's `POST` allowlist needs a
  reason in the pull request description.
- If a change needs a new permission, update `permissions` in `tool.yaml` and explain why it is needed.
- Do not include data from a real environment. Use `rainpole.io` host names and `198.51.100.x`
  addresses in code, tests, docs and screenshots. The privacy scan checks for this.
- The project name is "&lt;Tool&gt; for VCF Operations", never "VCF &lt;Tool&gt;".

## Development setup

The quickest start is the dev container: open the repository in VS Code with the Dev Containers
extension, or in GitHub Codespaces, and the Python version, linters and pre-commit hooks the project
uses are installed for you. The container can run the tests, but it usually cannot reach a VCF Operations
cluster; run live checks from a machine on your network.

To set up by hand:

```sh
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

| Task | Command |
| --- | --- |
| Tests | `pytest` |
| Lint and format | `ruff check . && ruff format .` |
| Lint shell scripts | `shellcheck scripts/*.sh` |
| Repository rules | `python scripts/repokit.py check` |
| Regenerate docs after editing `tool.yaml` | `python scripts/repokit.py render` |
| Privacy scan | `python scripts/repokit.py privacy` |
| Build the package and release assets | `make build` |

`make check` runs the tests, linters, repository rules and privacy scan if you have make.

## Pull requests

The project has no hosted CI, so nothing runs on your pull request automatically. Run
`make check && make build` first and say in the pull request that you did. A maintainer runs them
again before merging. [docs/maintaining.md](docs/maintaining.md#the-gate) lists what they do not cover.

- Keep each pull request to one change, with a test.
- Add a line under `## [Unreleased]` in `CHANGELOG.md`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`fix:`, `feat:`,
  `docs:`, `chore:`), which keeps the history readable.
- By contributing you agree that your contribution is licensed under the project licence (see `LICENSE`).
