# backend/tests

后端最小冒烟测试目录。

这里不再保留历史大而全测试集，只保留当前主链仍然有价值的一组 smoke tests，用于支撑后续按新模块继续开发。

当前保留原则：

- `test_app.py`：应用启动、健康检查、任务列表基础可用。
- `test_agent_configs.py`：Agent 配置装载与持久化主链。
- `test_auth.py`：认证登录主链。
- `test_profiles.py` / `test_users.py`：组织、用户、画像主链。
- `test_webhooks.py`：渠道入口与 webhook 安全/接入主链。
- `test_payload_aliases.py`：稳定协议字段兼容层。
- `test_memory_midterm_sqlite.py`：中期记忆主链。
- `test_scheduler_startup.py`：调度运行时基础自检。
- `test_execution_gateway.py`：技能执行网关主链。
- `test_nats_event_bus.py`：事件总线协程清理与基础稳定性。

后续如果新增模块测试，优先围绕当前新目录结构补充，不再回补旧结构绑定测试。
