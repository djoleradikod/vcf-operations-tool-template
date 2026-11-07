# Management packs: Builder or SDK

Some tools in this family are management packs rather than scripts. Each one picks how it is built,
records the choice in `tool.yaml` (`management_pack.approach`), and keeps its sources under
[`management-pack/`](../management-pack/).

## Decide

| Question | Management Pack Builder | VCF Operations Integration SDK |
| --- | --- | --- |
| What you write | Nothing: a design made in the VCF Operations UI | Python adapter code |
| Target system | A REST API with JSON responses | Anything you can reach from Python: REST, SOAP, SNMP, CLI, files |
| Data shaping | Field mapping, simple relationships | Arbitrary logic, joins, derived metrics, events |
| Where it runs | Cloud proxy, inside VCF Operations' own runtime | A container on the cloud proxy |
| Build tooling | In-product (*Developer Center*) | `mp-init`, `mp-test`, `mp-build` on a workstation with Docker |
| Testing | Interactive, in the builder | Local test harness (`mp-test`) and unit tests |
| Version control | Exported design file, committed here | Full source tree, committed here |
| Upgrade exposure | Rebuild in the updated builder after platform upgrades such as 9.1.1 ([KB 454434](https://knowledge.broadcom.com/external/article/454434)) | Rebuild against the SDK release that matches the platform |

Start with Management Pack Builder when the target has a clean REST API and the goal is to get
objects and metrics into VCF Operations quickly. Move to the Integration SDK when you need logic the
builder cannot express, a protocol other than REST, or unit tests. The SDK costs more
to build and maintain, so choose it for a reason you can write down in the pack's README.

## Repository layout

```text
management-pack/
├── README.md            what the pack collects, object model, install and upgrade steps
├── design/              Builder: the exported design file   |  SDK: the mp-init project
└── dist/                the .pak (and design export) to attach to a release
```

The release script bundles everything in `management-pack/dist/` (`.pak`, `.json`, `.zip`). A
management-pack repository without a `.pak` there fails the release on purpose.

## After every VCF Operations upgrade

1. Check *Integrations* for adapter instances that stopped receiving data.
2. Builder packs: open the design in the updated builder, make a trivial change so it registers, and
   reinstall from the design (KB 454434).
3. SDK packs: rebuild with the matching SDK release and retest with `mp-test`.
4. Add a row to the compatibility matrix and cut a release.

## References

- [VCF Operations Integration SDK documentation](https://vmware.github.io/vmware-vcf-operations-integration-sdk/introduction)
- [KB 454434: MP Builder packs do not collect after upgrading to 9.1.1](https://knowledge.broadcom.com/external/article/454434)
- [KB 454432: Management packs not collecting data after upgrading to 9.1.1](https://knowledge.broadcom.com/external/article/454432)
