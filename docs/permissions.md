# Permissions

<!-- repokit:begin permissions -->
**Read-only. Needs a dedicated service account with a read-only role. Never needs an administrator account.**

- **Account:** Dedicated service account (local or from your identity source). Not a named person, not admin.
- **Role:** Built-in ReadOnly role, or a custom role cloned from it.
- **Scope:** All objects the tool reports on. Narrow it to specific object types if your security model needs it.

| Area | Access | Why it is needed |
| --- | --- | --- |
| Suite API | Read | Acquire a session token and read the product version. |

**Not required, never ask for it:** Administrator or any built-in admin role; Write access to policies, alerts, dashboards or adapters; Shell or SSH access to any appliance; vCenter, NSX or SDDC Manager credentials.

| From | To | Port | Purpose |
| --- | --- | --- | --- |
| Machine running the tool | VCF Operations (cluster FQDN or load balancer) | 443/TCP | Suite API over HTTPS. TLS verification is on by default. |
<!-- repokit:end permissions -->

## Principles

1. **A dedicated service account per tool.** Not a person's account, and not shared with other
   integrations, so it can be audited, rotated and removed on its own.
2. **Read-only role.** The tool's client refuses state-changing calls in code, and the role makes sure the
   server would refuse them too. Two independent controls.
3. **Never administrator.** If a feature ever seems to need admin rights, that feature is redesigned or
   dropped. Issues asking users to "just use admin" are closed.
4. **Narrowest scope that works.** Start with the objects the tool reports on.

## Set up the service account

Menu names move between VCF Operations releases. The steps below describe the intent; follow the
equivalent screens in your version and the
[VCF Operations documentation](https://techdocs.broadcom.com/) for exact paths.

1. **Create or choose the role.** In VCF Operations, open *Access Control* under *Administration*.
   Use the built-in read-only role, or create a custom role that grants only the read permissions in
   the table above.
2. **Create the account.** Add a local user, or use a directory account from your identity source.
   Give it a name that says what it is for, such as `svc-template-tool`, and a long random password from
   your password manager.
3. **Assign the role and scope.** Assign the role from step 1 to the account, limited to the objects the
   tool needs.
4. **Store the secret where the tool runs.** Use your scheduler's or CI system's secret store and expose
   it as `VCFOPS_PASSWORD`. Do not write it into scripts, cron lines or config files in this repository.
5. **Confirm.** Run `template-tool check`. A permissions problem exits with code 4 and names the call
   that was refused.

## Rotation and removal

Rotate the password on your normal schedule; the tool reads it fresh on every run. To remove the tool,
delete the service account and its role. Nothing else is left behind in VCF Operations.

## For maintainers

Permissions live in `tool.yaml` under `permissions`. Mark a privilege `example: true` until you have
confirmed it against a real deployment; releases run `repokit.py check --strict`, which fails while
any example rows remain.
