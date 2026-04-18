---
agent_id: "memory"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 长期记忆只允许 `distillation` 来源写入，不直接保存原始对话。
- 默认过滤 API Key、Token、私钥、助记词、验证码、调试日志和临时排障上下文。
- 只写结构化、高置信、可复用的信息，如偏好、任务结果、决策和关键事件。
- 所有写入都必须带作用域判断，禁止跨租户合并记忆。
- `soul.md` 只描述 Agent 人格，不存放用户画像或租户画像。
