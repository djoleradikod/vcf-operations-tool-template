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
  addresses in code, tests, docs and screenshots. The privacy scan in CI checks for this.
- The project name is "&lt;Tool&gt; for VCF Operations", never "VCF &lt;Tool&gt;".

## Development setup

```sh
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

| Task | Command |
| --- | --- |
| Tests | `pytest` |
| Lint and format | `ruff check . && ruff format .` |
| Repository rules | `python scripts/repokit.py check` |
| Regenerate docs after editing `tool.yaml` | `python scripts/repokit.py render` |
| Privacy scan | `python scripts/repokit.py privacy` |

`make check` runs all of them if you have make.

## Pull requests

- Keep each pull request to one change, with a test.
- Add a line under `## [Unreleased]` in `CHANGELOG.md`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`fix:`, `feat:`,
  `docs:`, `chore:`), which keeps the history readable.
- By contributing you agree that your contribution is licensed under the project licence (see `LICENSE`).
