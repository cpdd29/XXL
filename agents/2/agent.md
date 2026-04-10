---
agent_id: "2"
version: "1.0.0"
name: "安全检测 Agent"
model: "gpt-4.1-mini"
capabilities:
  - rate_limit
  - prompt_injection_detection
  - content_redaction
trigger_intents:
  - guard
  - review
execution:
  max_iterations: 2
  timeout_seconds: 10
---
负责把不可信输入转成可进入主系统的安全输入。
