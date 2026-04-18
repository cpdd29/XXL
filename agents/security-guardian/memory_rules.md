---
agent_id: "security-guardian"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只允许保留风险标签、审计索引、处罚状态和脱敏建议摘要。
- 不保留明文凭证、验证码、完整证件号、银行卡号和内部秘密配置。
- 所有安全事件记录必须保留 `trace_id`，高风险结论应保留 `audit_id`。
- 不把用户原始敏感输入直接写入长期记忆。
