# Management pack

Only used when `kind: management-pack` in `tool.yaml`. Script and agent tools can delete this folder.

Choose the build approach first: [docs/management-packs.md](../docs/management-packs.md).

```text
management-pack/
├── README.md     what the pack collects: object types, metrics, properties, relationships
├── design/       Management Pack Builder: the exported design file
│                 Integration SDK: the project created by mp-init (adapter code, tests, content)
└── dist/         the .pak and design export attached to each release
```

## Document here

- **Object model:** each object type, its key properties, and how it relates to VCF objects.
- **Collection:** what the adapter calls on the target system, how often, and with which read-only account.
- **Install and upgrade:** where to add the pack in VCF Operations, and what to do after a platform upgrade.
- **Uninstall:** how to remove the pack and its adapter instances cleanly.
