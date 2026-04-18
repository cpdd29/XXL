---
agent_id: "workflow_designer"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只读取当前租户可见的能力目录摘要、审批策略摘要和相关 workflow 草稿上下文。
- 不把未审批的 workflow proposal 写入长期记忆，最多保留租户内草稿。
- 不引用隐藏工具、禁用连接器或跨租户能力作为提案节点。
- 每个提案都要带审批点、回滚计划和审计要求，便于后续人工复核。
