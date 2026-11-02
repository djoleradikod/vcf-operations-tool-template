# Troubleshooting

Run with `-v` first. Debug output shows each call's method, path and HTTP status, and never shows
credentials or tokens.

| Exit | Message starts with | Usual cause | Fix |
| --- | --- | --- | --- |
| 2 | `No VCF Operations host` / `No username` / `Set VCFOPS_PASSWORD` | A setting is missing, or the tool runs without a terminal and no password variable | Set `VCFOPS_HOST`, `VCFOPS_USER` and, for unattended runs, `VCFOPS_PASSWORD`. |
| 2 | `Only HTTPS is supported` | The host was given as `http://…` | Use the HTTPS FQDN. |
| 3 | `VCF Operations rejected the credentials` | Wrong password, locked or expired account, or wrong authentication source | Log in to the UI as the service account once; for directory accounts set `--auth-source`. |
| 4 | `The service account may not call …` | The role lacks a read permission the tool needs | Compare the role with [permissions.md](permissions.md). Do not switch to an admin account. |
| 5 | `VCF Operations … is not supported` | Below the 9.1.1 baseline, or a row marked *Not supported* | See [compatibility.md](compatibility.md). |
| 6 | `TLS verification failed` | The certificate chain is not trusted on this machine | Export the CA chain to PEM and pass `--ca-bundle`. Avoid `--insecure` outside a lab. |
| 7 | `Refusing POST …` | A code path tried a call that is not read-only | This is a bug. Open an issue with the `-v` output. |
| 8 | `Cannot reach …` | DNS, routing, firewall, or proxy | Test `curl -sv https://<host>/suite-api/` from the same machine; set `HTTPS_PROXY`/`NO_PROXY` if a proxy is involved. |
| 8 | `… returned HTTP 5xx` | VCF Operations is busy, starting or degraded | Check cluster status in VCF Operations, then retry. |

## Before opening an issue

- Re-run with `-v` and copy the output.
- Replace host names, IP addresses, user names and anything that looks like a token.
- Include the tool version (`template-tool --version`) and the VCF Operations version.
