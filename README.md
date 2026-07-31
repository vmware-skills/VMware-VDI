<!-- mcp-name: io.github.zw008/vmware-vdi -->

# VMware VDI (Horizon)

AI-powered VMware / Omnissa **Horizon VDI** intelligent operations — desktop pools, RDS farms, **user
sessions**, desktop machines, entitlements, events/health, statistics, and instant-clone image push,
through the Horizon 8 Connection Server REST API. MCP server + CLI, part of the VMware skill family.

> **Disclaimer**: Community-maintained open-source project, **not affiliated with, endorsed by, or
> sponsored by VMware, Inc., Broadcom Inc., or Omnissa, LLC.** "VMware", "Horizon", and "Omnissa" are
> trademarks of their respective owners. Source is publicly auditable under the MIT license.

> **Status: in development (v1.0.0).** Design in `design/vmware-vdi-skill-design.md`. Tool surface
> (15 read / 14 write across monitoring / statistics / management / ops actions / tasks) is landing
> vertical by vertical — **sessions first**. Governed by the family harness (audit + policy + teaching
> errors); authorization is delegated to the Horizon admin account's role (a read-only role refuses
> writes at the Connection Server).

## Companion skills

- [vmware-aiops](https://github.com/zw008/VMware-AIops) — the vCenter VMs backing the desktops
- [vmware-monitor](https://github.com/zw008/VMware-Monitor) — read-only vSphere monitoring
- [vmware-nsx-security](https://github.com/zw008/VMware-NSX-Security) — desktop microsegmentation

## License

MIT
