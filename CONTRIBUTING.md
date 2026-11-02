# Contributing

Thank you for helping. Two kinds of contribution matter most here:

1. **Compatibility reports.** Run the tool against a VCF Operations version that is not in the matrix and
   [report what happened](../../issues/new?template=compatibility_report.yml).
2. **Fixes and improvements** that keep the tool read-only and least-privilege.

## Ground rules

- **Read-only.** No change may add a state-changing call. New entries on the client's POST allowlist
  need a reason in the pull request.
- **Least privilege.** If a change needs a new permission, update `permissions` in `tool.yaml` and say why.
- **No real environment data.** Use `rainpole.io` host names and `198.51.100.x` addresses in code, tests,
  docs and screenshots. The privacy scan in CI enforces this.
- **Naming.** "&lt;Tool&gt; for VCF Operations", never "VCF &lt;Tool&gt;".

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
