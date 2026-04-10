---
agent_id: "6"
version: "1.0.0"
name: "输出 Agent"
model: "gpt-4.1-mini"
capabilities:
  - response_formatting
  - channel_adaptation
  - final_delivery
trigger_intents:
  - deliver
  - format
execution:
  max_iterations: 2
  timeout_seconds: 20
---
负责把最终结果整理成适合控制面、Webhook 或多渠道下发的格式。
