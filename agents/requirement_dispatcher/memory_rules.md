---
agent_id: "requirement_dispatcher"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只读取当前会话的澄清摘要、安全结论和必要的租户上下文。
- 不写长期记忆，不保留原始敏感内容。
- 输出只保留意图、分发方向和 handoff 说明，不沉淀临时推断。
