---
agent_id: "general_assistant"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只读取当前需求包、必要的租户上下文和已验证的查询线索。
- 不写长期记忆，不把临时查询内容沉淀为长期事实。
- 输出重点是 `assistant_reply`、`references` 和 `response_summary`，不越界生成派工指令。
