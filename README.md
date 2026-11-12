<!-- mcp-name: io.github.vmware-skills/vmware-vdi -->

# VMware-VDI

<a id="readme-overview"></a>

Investigate Horizon desktops and sessions with focused operational tools.

English · [简体中文](README-CN.md)

Community-maintained · MIT · Not an official VMware/Broadcom/Omnissa product.

[![18-second illustrative investigation demo](https://raw.githubusercontent.com/vmware-skills/marketplace/main/assets/demos/vmware-skills-en.gif)](https://github.com/vmware-skills/marketplace/blob/main/assets/demos/vmware-skills-en.mp4)

Synthetic-data animation, not a live recording. [Watch the AI-narrated family introduction (~2 min)](https://github.com/vmware-skills/marketplace/blob/main/assets/demos/vmware-skills-en.mp4)

<a id="readme-capabilities-and-workflows"></a>

## Why use it?

- Inspect pools, farms, machines and health.
- Work with sessions and entitlements.
- Plan supported image and desktop operations explicitly.

<a id="readme-quick-start"></a>

## Get started

Install the published CLI and inspect its commands:

```sh
uv tool install vmware-vdi==2.4.5
vmware-vdi --help
```

Requires uv and Python >=3.10. Configure targets and credentials locally before remote queries. [Setup guide](skills/vmware-vdi/references/setup-guide.md).

For Claude Code and other host installation paths, see the [family portal](https://github.com/vmware-skills/marketplace).

<a id="readme-safety-and-audit"></a>

## Know the boundaries

Includes session logoff, desktop reset and image operations. Missing or incomplete evidence must not be treated as a complete inventory. Horizon live-validation limits remain documented.

<a id="readme-mcp-configuration"></a> <a id="readme-troubleshooting"></a> <a id="readme-reference"></a>

## Go deeper

- [Capabilities](skills/vmware-vdi/references/capabilities.md)
- [CLI reference](skills/vmware-vdi/references/cli-reference.md)
- [Detailed usage and architecture](skills/vmware-vdi/references/detailed-guide.md)
- [MCP launch configuration](.mcp.json)
- [Canonical skill instructions](skills/vmware-vdi/SKILL.md)

<a id="readme-companion-skills"></a>

Part of [VMware Skills](https://github.com/vmware-skills/marketplace): 15 skills, 14 MCP servers and one shared Policy library. If it helps your work, star the family portal.

<a id="readme-license"></a>

[Issues and feedback](https://github.com/vmware-skills/VMware-VDI/issues) · [MIT](LICENSE)
