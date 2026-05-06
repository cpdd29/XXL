# 执行器接入模块（executor-config）

该模块负责“内部执行器接入配置”的前端能力，不负责外接 Agent 注册。

## 目标

- 提供独立路由页面用于配置内部执行器。
- 支持执行器接入校验、健康检查与状态观测。
- 为后续 Agent 管理绑定执行器做数据准备。

## 边界

- 只负责接入配置与基础观测，不负责任务调度。
- 不承载 Skill/MCP 具体实现，只保留绑定扩展所需元信息。
- 当前通过 `/api/executors` 管理内部执行器。

## 文件约定

- `pages/executor-settings-page.tsx`：执行器接入配置页面。
- `hooks/use-executor-config.ts`：执行器状态查询与注册调用。
