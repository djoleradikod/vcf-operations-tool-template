# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub private vulnerability reporting](../../security/advisories/new). Do not open a public issue,
and do not include production host names, addresses or credentials in the report.

You can expect an acknowledgement within 7 days and an assessment within 14. Fixes ship as a patch
release with a GitHub security advisory crediting the reporter, unless you prefer otherwise.

## Supported versions

Only the latest minor release receives security fixes. Upgrade to get them.

## In scope

- Handling of credentials and session tokens
- TLS verification and certificate handling
- Any path that could make a state-changing call despite the read-only design
- Dependencies shipped in a release

Vulnerabilities in VCF Operations itself are out of scope; report those to Broadcom.

## Security design

The API client refuses calls that change state before they are sent, and the tool is designed to run
under a dedicated read-only service account, so it never needs administrator rights. Passwords are
read from the environment or a prompt, never from command-line flags, and are not logged. TLS
verification is on by default. Each release includes checksums, a software bill of materials and a
signed build-provenance attestation.
