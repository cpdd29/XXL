---
agent_id: "5"
version: "1.0.0"
name: "摘要 Agent"
model: "gpt-4.1-mini"
capabilities:
  - summarization
  - distillation
  - highlight_extraction
trigger_intents:
  - summarize
  - digest
execution:
  max_iterations: 3
  timeout_seconds: 30
---
负责从长文本和会话中提取关键结论、行动项和风险点。
