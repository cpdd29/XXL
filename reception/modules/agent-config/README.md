# agent-config 模块

## 模块职责

负责 Agent 的接入配置、展示与管理，是“Agent 可替换接入”在前端的配置入口。

## 当前路由

- `/agents`

## 主要文件

- `pages/agents-page.tsx`
- `hooks/use-agents.ts`

## 注意事项

- 仅做 Agent 管理与配置，不承载任务执行编排逻辑。
- Agent 绑定关系通过后端返回的 `agentId` 驱动，前端不写死 Agent 名称。
