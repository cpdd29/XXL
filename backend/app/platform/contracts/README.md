# platform/contracts

稳定协议目录。

这里沉淀 NATS 事件协议、Agent 协议、事件主题、消息类型，以及跨模块复用的稳定执行协议。

- `api_model.py`：全仓 API DTO 共用的序列化基座与字段命名转换规则，原先位于 `app/schemas/base.py`。
- `agent_protocol.py`：Agent 相关协议定义。
- `event_protocol.py` / `event_subjects.py` / `event_types.py`：事件总线稳定协议。
- `execution_protocol.py`：执行请求、执行结果、执行尝试等跨模块复用协议，原先位于 `app/execution_gateway/contracts.py`。
- `payload_aliases.py`：跨模块复用的协议字段兼容解析工具，统一处理 snake_case / camelCase 取值、调度上下文提取、执行计划提取，原先分散在 `app/core/brain_payload_fields.py` 与 `app/core/payload_aliases.py`。
