---
agent_id: "4"
version: "1.0.0"
name: "写作 Agent"
model: "gpt-4.1"
capabilities:
  - drafting
  - rewriting
  - summarization
trigger_intents:
  - write
  - draft
  - reply
execution:
  max_iterations: 4
  timeout_seconds: 60
---
负责生成结构化草稿、客服回复和管理后台文本内容。
