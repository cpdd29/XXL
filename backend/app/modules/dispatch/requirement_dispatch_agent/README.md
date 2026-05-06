# dispatch/requirement_dispatch_agent

需求分发 Agent 服务层。

这里负责把 Hermes 交回的平台需求任务，转成可执行的需求下发结果：

- 判断当前需求走 `single_agent` 还是 `multi_agent`
- 生成并保留开发组与验收 Agent
- 为生成的 Agent 注入 `soul`、Skill / MCP 绑定意图与 NATS 协作主题
- 把分发结论回写到任务中心与任务步骤

节点层仍然只绑定可替换的 `agent_id`，不在工作流节点里写死具体 Agent 名称。
