# Troubleshooting

Run with `-v` first. Debug output shows each call's method, path and HTTP status, and never shows
credentials or tokens.

| Exit | Message starts with | Usual cause | Fix |
| --- | --- | --- | --- |
| 2 | `No VCF Operations host` / `No username` / `No password` | A setting is missing, or the tool runs without a terminal and has no password source | Run `template-tool profiles` to see what was found. Set the host and user in a profile or the environment; for unattended runs set `VCFOPS_PASSWORD` or `password_command`. |
| 2 | `Profile '…' is not defined` | `--profile` or `VCFOPS_PROFILE` names a profile that is not in the file, or the tool is reading a different file | `template-tool about` prints the path it reads. Check `VCFOPS_CONFIG`. |
| 2 | `… Secrets do not belong in this file` / `TLS verification cannot be turned off` | The profile file contains a password, token, or `insecure` setting | Remove it. Use `password_command` or `VCFOPS_PASSWORD`, and `ca_bundle`. |
| 2 | `password_command exited with status …` | The secret manager is locked, or the entry name is wrong | Run the command by hand in the same shell and check it prints the password on its first line. |
| 2 | `CA bundle not found` | The `ca_bundle` path is wrong. `~` is expanded; environment variables are not | Use the full path to the PEM file. |
| 2 | `Only HTTPS is supported` | The host was given as `http://…` | Use the HTTPS FQDN. |
| 3 | `VCF Operations rejected the credentials` | Wrong password, locked or expired account, or wrong authentication source | Log in to the UI as the service account once; for directory accounts set `--auth-source`. |
| 4 | `The service account may not call …` | The role lacks a read permission the tool needs | Compare the role with [permissions.md](permissions.md). Do not switch to an admin account. |
| 5 | `VCF Operations … is not supported` | Below the 9.1.1 baseline, or a row marked *Not supported* | See [compatibility.md](compatibility.md). |
| 6 | `TLS verification failed` | The certificate chain is not trusted on this machine | Export the CA chain to PEM and pass `--ca-bundle`. Avoid `--insecure` outside a lab. |
| 7 | `Refusing POST …` | A code path tried a call that is not read-only | This is a bug. Open an issue with the `-v` output. |
| 8 | `Cannot reach …` | DNS, routing, firewall, or proxy | Test `curl -sv https://<host>/suite-api/` from the same machine; set `HTTPS_PROXY`/`NO_PROXY` if a proxy is involved. |
| 8 | `… returned HTTP 503 after 4 attempts` | VCF Operations is busy, starting or degraded, and stayed that way through the retries | Check cluster status in VCF Operations. Retry later rather than raising `max_retries`. |
| 8 | `… the server asked clients to wait …s` | The server sent a `Retry-After` longer than two minutes | The cluster is shedding load on purpose. Run the tool again after that time. |
| 8 | `… timed out after 30s` | One request took longer than `timeout` | Raise `--timeout`, or lower `--page-size` so each request does less work. |
| 8 | `… returned HTTP 5xx` | VCF Operations returned an error that retrying does not fix | Check cluster status and the VCF Operations logs, then retry. |

`WARNING … retrying in 2.0s (attempt 2 of 4)` on stderr is not an error. The tool met a busy server
and is backing off; it exits 0 if a later attempt succeeds.

## inventory returns fewer objects than expected

The Suite API returns only the objects in the service account's scope. Compare the scope assigned
to the account with what you expected, and see [permissions.md](permissions.md). Filters are matched
by VCF Operations: `--adapter-kind` and `--resource-kind` take internal keys such as `VMWARE` and
`VirtualMachine`, not the display names shown in the UI.

## Before opening an issue

- Re-run with `-v` and copy the output.
- Replace host names, IP addresses, user names and anything that looks like a token.
- Include the tool version (`template-tool --version`) and the VCF Operations version.
