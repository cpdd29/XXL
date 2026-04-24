# agent_config/registries

注册表目录。

这里维护已接入 Agent、Skill、MCP、Tool Source 等可配置资源的注册、加载、校验与同步逻辑。

- `agent_reach_adapter.py`：承接 Agent Reach 这类外部工具目录适配逻辑，供 `tool_source_service.py` 直接调用。
