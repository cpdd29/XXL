# dispatch/skill_runtime

技能运行时目录。

这里承载调度模块自己的 skill 执行运行时，包括能力调用、超时控制、执行追踪与结果摘要，不负责 skill 注册表本身。

- `execution_policy.py`：skill 执行时的流量策略与 builtin/runtime 切换规则。
- `runtime_router.py`：在 runtime 与 builtin 之间做执行路由和失败回退。
- `skill_execution_gateway.py`：统一 skill 执行入口，承接原 `execution_gateway` 的执行网关能力。
- `skill_runtime_service.py`：具体的 skill 运行时实现。

新的调度代码应直接从 `app.modules.dispatch.skill_runtime` 引用。
