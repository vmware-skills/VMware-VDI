<!-- mcp-name: io.github.vmware-skills/vmware-vdi -->

# VMware-VDI

Investigate Horizon desktops and sessions with focused operational tools.

English · [简体中文](README-CN.md)

Community-maintained · MIT · Not an official VMware/Broadcom product.

[![18-second illustrative investigation demo](https://raw.githubusercontent.com/vmware-skills/marketplace/main/assets/demos/vmware-skills-en.gif)](https://github.com/vmware-skills/marketplace/blob/main/assets/demos/vmware-skills-en.mp4)

Synthetic-data animation, not a live recording. [Watch the narrated family introduction (~2 min)](https://github.com/vmware-skills/marketplace/blob/main/assets/demos/vmware-skills-en.mp4)

## Why use it?

- Inspect pools, farms, machines and health.
- Work with sessions and entitlements.
- Plan supported image and desktop operations explicitly.

## Get started

Install the published CLI and inspect its commands:

```sh
uv tool install vmware-vdi==2.4.5
vmware-vdi --help
```

Requires uv and Python >=3.10. Configure targets and credentials locally before remote queries. [Setup guide](skills/vmware-vdi/references/setup-guide.md).

For Claude Code and other host installation paths, see the [family portal](https://github.com/vmware-skills/marketplace).

## Know the boundaries

Includes session logoff, desktop reset and image operations. Missing or incomplete evidence must not be treated as a complete inventory. Horizon live-validation limits remain documented.

## Go deeper

- [Capabilities](skills/vmware-vdi/references/capabilities.md)
- [CLI reference](skills/vmware-vdi/references/cli-reference.md)
- [Detailed usage and architecture](skills/vmware-vdi/references/detailed-guide.md)
- [Canonical skill instructions](skills/vmware-vdi/SKILL.md)

Part of [VMware Skills](https://github.com/vmware-skills/marketplace): 15 skills, 14 MCP servers and one shared Policy library. If it helps your work, star the family portal.

[Issues and feedback](https://github.com/vmware-skills/VMware-VDI/issues) · [MIT](LICENSE)
