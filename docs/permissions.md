# Permissions

<!-- repokit:begin permissions -->
The tool only reads. It runs under a dedicated service account with a read-only role and never needs an administrator account.

| Item | Requirement |
| --- | --- |
| Account | A dedicated service account, local or from your identity source. Not a person's account, and not an administrator. |
| Role | The built-in ReadOnly role, or a custom role cloned from it. |
| Scope | The objects the tool reports on. Narrow it to specific object types if your security model requires it. |

The role needs these permissions and no others:

| Area | Access | Why it is needed |
| --- | --- | --- |
| Suite API | Read | Acquire a session token and read the product version. |

The tool does not need any of the following. Treat a request for them as a bug.

- Administrator or any built-in admin role
- Write access to policies, alerts, dashboards or adapters
- Shell or SSH access to any appliance
- vCenter, NSX or SDDC Manager credentials

Network flows:

| From | To | Port | Purpose |
| --- | --- | --- | --- |
| Machine running the tool | VCF Operations (cluster FQDN or load balancer) | 443/TCP | Suite API over HTTPS. TLS verification is on by default. |
<!-- repokit:end permissions -->

## Principles

Each tool runs under its own service account. A person's account changes when they change roles or
leave, and an account shared between integrations cannot be audited, rotated or removed without
affecting everything else that uses it. A dedicated account avoids both problems.

The account holds a read-only role. The tool's API client already refuses calls that change state,
so the role is a second, independent control: if a defect in the client ever let a write through,
VCF Operations would still reject it. We rely on having both.

No tool in this family needs an administrator account. If a feature appears to require one, we
redesign the feature or drop it; we do not ask operators to widen the role. Scope follows the same
rule: grant access to the objects the tool reports on, and nothing broader.

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
