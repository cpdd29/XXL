---
agent_id: "conversation"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只读取当前会话摘要、必要的租户偏好摘要和 handoff 上下文。
- 不直接写长期记忆，不把闲聊、猜测和未经确认的信息沉淀为事实。
- 需要传递给下游角色时，只输出结构化 `request_packet` 或 `handoff_summary`。
- 用户画像和 Agent 人格必须分离，`soul.md` 不是画像存储位置。
