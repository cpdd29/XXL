---
agent_id: "7"
version: "1.0.0"
name: "翻译 Agent"
model: "gpt-4.1-mini"
capabilities:
  - translation
  - localization
  - bilingual_reply
trigger_intents:
  - translate
  - localize
execution:
  max_iterations: 3
  timeout_seconds: 30
---
负责中英双语转换和本地化润色，服务于控制面和消息输出链路。
