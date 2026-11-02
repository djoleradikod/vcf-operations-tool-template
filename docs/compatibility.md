# Compatibility

<!-- repokit:begin compatibility -->
The baseline is VCF Operations 9.1.1 or later. VCF 9.1.1 updated the open-source dependencies that adapters run on, and management packs built with earlier versions of Management Pack Builder stop collecting after the upgrade ([KB 454434](https://knowledge.broadcom.com/external/article/454434)). Every tool in this family targets 9.1.1 and later so there is one baseline to test.

| Tool release | VCF Operations | VCF | Status | Notes |
| --- | --- | --- | --- | --- |
| 0.1.x | 9.1.1 | 9.1 | Tested | Lab-validated on a single-node deployment. |
| 0.1.x | 9.0.x | 9.0 | Not supported | Below the 9.1.1 baseline. |
| 0.1.x | 8.18.x | 5.2 | Not supported | VMware Aria Operations. Below the baseline. |
<!-- repokit:end compatibility -->

## Support policy

Every "&lt;Tool&gt; for VCF Operations" project supports VCF Operations 9.1.1 and later. Older
releases, including VMware Aria Operations 8.x, are out of scope. A single baseline across the family
means each tool is tested against the same versions, and an operator running several tools only has
one requirement to check.

The status column uses four values:

| Status | Meaning |
| --- | --- |
| Tested | The maintainer ran this tool release end to end against that VCF Operations version in a lab, and the automated tests passed. |
| Supported | Expected to work and reported working by users. Bugs on this combination are fixed. |
| Untested | May work, but nobody has confirmed it. The tool prints a warning and continues. |
| Not supported | Known not to work, or below the baseline. The tool exits with code 5. |

A new VCF Operations release starts as untested. When a release breaks a tool, we publish a patch
release and record the result in the matrix. Fixes go into the latest minor release of the tool
only, so upgrading is the way to pick them up.

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
