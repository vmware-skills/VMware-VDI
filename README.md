<!-- mcp-name: io.github.vmware-skills/vmware-vdi -->

# VMware-VDI

<a id="readme-overview"></a>

Investigate Horizon desktops and sessions with focused operational tools.

English · [简体中文](https://github.com/vmware-skills/VMware-VDI/blob/main/README-CN.md)

Community-maintained · MIT · Not an official VMware/Broadcom/Omnissa product.

[![24-second illustrative investigation demo](https://raw.githubusercontent.com/vmware-skills/marketplace/main/assets/demos/vmware-skills-en.gif)](https://github.com/vmware-skills/marketplace/releases/download/demos-2026-11-13-operations/vmware-skills-en.mp4)

Synthetic-data GIF; video includes redacted historical screenshots. [Download the AI-narrated family introduction (~3 min)](https://github.com/vmware-skills/marketplace/releases/download/demos-2026-11-13-operations/vmware-skills-en.mp4)

<a id="readme-capabilities-and-workflows"></a>

## Why use it?

- Inspect pools, farms, machines and health.
- Work with sessions and entitlements.
- Plan supported image and desktop operations explicitly.

<a id="readme-quick-start"></a>

## Get started

Install the published CLI and inspect its commands:

```sh
uv tool install vmware-vdi==2.4.6
vmware-vdi --help
```

Requires uv and Python >=3.10. Configure targets and credentials locally before remote queries. [Setup guide](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/references/setup-guide.md).

One-click installs, after local setup: [Claude Desktop extension (.mcpb)](https://github.com/vmware-skills/VMware-VDI/releases/download/v2.4.6/vmware-vdi-2.4.6.mcpb) · [Install in VS Code](https://insiders.vscode.dev/redirect/mcp/install?name=vmware-vdi&config=%7B%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22--from%22%2C%22vmware-vdi%3D%3D2.4.6%22%2C%22vmware-vdi-mcp%22%5D%7D). Both run the same pinned 2.4.6 server. The desktop extension starts with read-only tools; change *Tools to offer* to `all` for writes.

For agent-host installation, use the [setup guide](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/references/setup-guide.md) and [Cursor, Codex, Gemini CLI, Cline and local-model examples](https://github.com/vmware-skills/marketplace/blob/main/docs/agent-hosts.md).

Choose a model with the [shared model-fit workflow](https://github.com/vmware-skills/marketplace/blob/main/model-fit/RUNNER.md): compare the same tasks, review quality and safety, then select the smallest tested passing configuration per task group; this is not a production guarantee.

<a id="readme-safety-and-audit"></a>

## Know the boundaries

Includes session logoff, desktop reset and image operations. Missing or incomplete evidence must not be treated as a complete inventory. Horizon live-validation limits remain documented.

<a id="readme-mcp-configuration"></a> <a id="readme-troubleshooting"></a> <a id="readme-reference"></a>

## Go deeper

- [Capabilities](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/references/capabilities.md)
- [CLI reference](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/references/cli-reference.md)
- [Detailed usage and architecture](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/references/detailed-guide.md)
- [MCP launch configuration](https://github.com/vmware-skills/VMware-VDI/blob/main/.mcp.json)
- [Canonical skill instructions](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/SKILL.md)

<a id="readme-companion-skills"></a>

Part of [VMware Skills](https://github.com/vmware-skills/marketplace): 15 skills, 14 MCP servers and one shared Policy library. If it helps your work, star the family portal.

<a id="readme-license"></a>

[Issues and feedback](https://github.com/vmware-skills/VMware-VDI/issues) · [MIT](https://github.com/vmware-skills/VMware-VDI/blob/main/LICENSE)

## MCP result contract

Offset-capable listings expose `next_offset`; stop when it is null rather than looping on `truncated`. Failed calls provide `structuredContent.vmware_error` through Policy 1.26.0. Existing text, legacy flags, success values and confirmation checks remain unchanged. See the [contract](https://github.com/vmware-skills/VMware-VDI/blob/main/skills/vmware-vdi/references/mcp-result-contract.md).
