<!-- mcp-name: io.github.zw008/vmware-vdi -->

# VMware VDI (Horizon)

AI 驱动的 VMware / Omnissa **Horizon VDI** 智能运维 —— 桌面池、RDS 农场、**用户会话**、桌面机器、授权、
事件/健康/统计、即时克隆金像推送,通过 **Horizon 8 Connection Server REST API**(以 Horizon 8 为主,
兼容最新 Omnissa Horizon,同一套 `/rest/v1` API)。MCP server + CLI,VMware skill 家族成员。

> **声明**:社区维护的开源项目,**与 VMware, Inc.、Broadcom Inc.、Omnissa, LLC. 无任何隶属、背书或赞助关系。**
> "VMware"、"Horizon"、"Omnissa" 为各自商标。源码遵循 MIT 许可,公开可审计。

> **状态:v1.0.0(beta)。** REST 端点已对照官方 Horizon Server API 核实;GET 响应字段投影为防御式,
> 待真机 Connection Server 验证(在真实 Horizon 上跑一次 `vmware-vdi init` 即可确认)。由家族 harness
> 治理(审计 + 策略 + 教学性错误);读写授权交由 Horizon 管理账号的角色(RBAC)。

## 能力(27 工具:16 读 / 11 写)

| 类别 | 工具 |
|------|------|
| **监控** | 健康速览、会话 列表/详情、机器 列表/详情、事件列表 |
| **统计** | 会话并发统计、按池利用率 |
| **管理** | 池/农场/应用池/授权/镜像 列表、AD 搜索;池 启用/禁用、授权 增/删 |
| **运维动作** | 会话 注销/断开/发消息、机器 重置/维护/移除 |
| **任务** | 任务状态;镜像推送、任务取消 |

破坏性写操作预览爆炸半径、CLI 双重确认、`--dry-run`、统一审计到 `~/.vmware/audit.db`。
`pool_push_image` 重建整池桌面,爆炸半径最高,预览报受影响桌面数 + 在线用户数。

## 快速开始
```bash
uv tool install vmware-vdi
vmware-vdi init      # 友好向导:连接 Connection Server 并发现你的桌面池
vmware-vdi doctor
```

## Companion Skills
- [vmware-aiops](https://github.com/vmware-skills/VMware-AIops) —— 桌面背后的 vCenter 虚机
- [vmware-monitor](https://github.com/vmware-skills/VMware-Monitor) —— 只读 vSphere 监控
- [vmware-nsx-security](https://github.com/vmware-skills/VMware-NSX-Security) —— 桌面微隔离

## License
MIT
