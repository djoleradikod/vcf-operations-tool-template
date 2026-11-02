# Compatibility

<!-- repokit:begin compatibility -->
**Baseline: VCF Operations 9.1.1 or later.** VCF 9.1.1 updated the open-source dependencies that adapters run on, and management packs built with earlier versions of Management Pack Builder stop collecting after the upgrade ([KB 454434](https://knowledge.broadcom.com/external/article/454434)). Every tool in this family targets 9.1.1 and later so there is one baseline to test.

| Tool release | VCF Operations | VCF | Status | Notes |
| --- | --- | --- | --- | --- |
| 0.1.x | 9.1.1 | 9.1 | ✅ Tested | Lab-validated on a single-node deployment. |
| 0.1.x | 9.0.x | 9.0 | ❌ Not supported | Below the 9.1.1 baseline. |
| 0.1.x | 8.18.x | 5.2 | ❌ Not supported | VMware Aria Operations. Below the baseline. |

✅ Tested end to end by the maintainer · ☑️ Supported, reported working · ⚠️ Untested · ❌ Not supported
<!-- repokit:end compatibility -->

## Support policy

- **One baseline for the whole family.** Every "&lt;Tool&gt; for VCF Operations" project supports
  VCF Operations 9.1.1 and later. Older releases, including VMware Aria Operations 8.x, are out of scope.
- **What "tested" means.** The maintainer ran the release end to end against that VCF Operations version
  in a lab and the automated tests passed. "Supported" means it is expected to work, it has been
  reported working, and bugs on it will be fixed.
- **New VCF Operations releases.** They show as *untested* (the tool warns but runs) until they have
  been tested. If a new release breaks the tool, a patch release follows and the matrix records it.
- **Fixes land on the latest minor release** of the tool. Upgrade to get them.

## How the tool checks

`check` reads the product version from the Suite API and compares it with this table, which is compiled
into the tool at build time. A version below the baseline or marked *Not supported* exits with code 5.

## Report a result

Running a combination that is not listed? Open a
[compatibility report](../../../issues/new?template=compatibility_report.yml). Reports from real
deployments are how rows move from *untested* to *supported*.

## Why 9.1.1

VCF 9.1.1 updated the open-source and third-party dependencies that management-pack adapters run on.
Custom packs built with earlier versions of Management Pack Builder stop collecting after the upgrade
until they are rebuilt in the updated builder
([KB 454434](https://knowledge.broadcom.com/external/article/454434)), and several Broadcom-provided
management packs need their 9.1.1-compatible versions
([KB 454432](https://knowledge.broadcom.com/external/article/454432)). Targeting 9.1.1 and later keeps
one tested baseline across scripts, agents and packs.
