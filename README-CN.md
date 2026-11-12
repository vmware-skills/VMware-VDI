<!-- mcp-name: io.github.vmware-skills/vmware-vdi -->

# VMware-VDI

通过专业运维工具调查 Horizon 桌面与会话。

English · [简体中文](README-CN.md)

社区维护 · MIT 开源 · 非 VMware/Broadcom 官方产品。

[![18 秒调查示意演示](https://raw.githubusercontent.com/vmware-skills/marketplace/main/assets/demos/vmware-skills-zh.gif)](https://github.com/vmware-skills/marketplace/blob/main/assets/demos/vmware-skills-zh.mp4)

使用合成数据的示意动画，非实时录屏。[观看家族配音介绍（约 2 分钟）](https://github.com/vmware-skills/marketplace/blob/main/assets/demos/vmware-skills-zh.mp4)

## 能解决什么问题？

- 检查桌面池、Farm、机器与健康。
- 处理会话与授权。
- 明确规划受支持的镜像与桌面操作。

## 快速开始

安装已发布 CLI，并查看可用命令：

```sh
uv tool install vmware-vdi==2.4.5
vmware-vdi --help
```

需要 uv 与 Python >=3.10。远程查询前，在本地配置目标与凭据。[配置指南](skills/vmware-vdi/references/setup-guide.md).

Claude Code 及其他宿主安装方式见[家族门户](https://github.com/vmware-skills/marketplace/blob/main/README-CN.md)。

## 使用边界

包含会话注销、桌面重置和镜像操作。缺失或不完整证据不能视为完整清单；Horizon 真机验证限制另有记录。

## 详细文档

- [能力范围](skills/vmware-vdi/references/capabilities.md)
- [CLI 用法](skills/vmware-vdi/references/cli-reference.md)
- [详细用法与架构](skills/vmware-vdi/references/detailed-guide-CN.md)
- [唯一技能指令正本](skills/vmware-vdi/SKILL.md)

属于 [VMware Skills 家族](https://github.com/vmware-skills/marketplace/blob/main/README-CN.md)：15 个 skill、14 个 MCP server 与一个共享 Policy 库。如果对你有用，欢迎 Star 家族门户。

[问题与反馈](https://github.com/vmware-skills/VMware-VDI/issues) · [MIT](LICENSE)
