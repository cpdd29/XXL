---
agent_id: "security"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只允许保留安全策略摘要、风险标签、处罚状态和审计索引。
- 不保留明文凭证、验证码、完整证件号、银行卡号和内部秘密配置。
- 所有安全事件记录必须可追溯到 `trace_id`，高风险结论应带 `audit_id`。
- 安全 Agent 的输出只能补充说明，不得覆盖本地安全真相源。
