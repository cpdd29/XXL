# modules

业务模块入口目录。

这里按业务职责拆分后端能力，不再把接待、调度、组织、Agent 配置都继续平铺在 `services/` 里。

当前目标模块：

- `reception`：渠道接入、实时安全监听、接待 Agent 接入、消息回传
- `dispatch`：任务下发、需求分发、单/多 Agent 执行与 workflow 运行内核
- `agent_config`：Agent / Skill / MCP / Tool Source 接入与节点绑定配置
- `organization`：租户、用户、画像等组织侧数据
