---
agent_id: "1"
version: "1.0.0"
name: "意图识别 Agent"
model: "gpt-4.1-mini"
capabilities:
  - intent_classification
  - route_selection
  - context_merge
trigger_intents:
  - search
  - write
  - help
execution:
  max_iterations: 2
  timeout_seconds: 15
---
负责把用户消息归类成主链可执行的意图和路由信号。
