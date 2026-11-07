## What and why

<!-- One or two sentences. Link the issue: Closes #123 -->

## How it was tested

- [ ] `make check && make build` passes (there is no hosted CI, so this is the gate)
- [ ] Tested against VCF Operations version: <!-- e.g. 9.1.1, or "not needed" -->

## Checklist

- [ ] Still read-only: no new state-changing calls, and no new entries on the POST allowlist (or explained above)
- [ ] Needs no new permissions, or `tool.yaml` `permissions` is updated
- [ ] `CHANGELOG.md` has an entry under Unreleased
- [ ] No host names, IP addresses, user names or tokens in code, tests, docs or screenshots
