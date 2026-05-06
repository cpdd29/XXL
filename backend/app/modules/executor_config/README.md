# executor_config

内部执行器接入模块。

目标是把执行器做成平台内能力：可注册、可校验、可观测，再由 Agent 进行绑定。

## 能力范围

- 执行器配置管理（增删改查）
- 执行器接入校验（CLI / HTTP）
- 执行器健康检查与状态观测

## 边界

- 不负责任务调度执行链路
- 不负责外接 Agent 注册治理（那是 `agent_config/external_connections`）
- 本模块只管理“内部执行器真源”

