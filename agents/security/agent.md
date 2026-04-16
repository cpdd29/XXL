---
agent_id: "security"
version: "1.0.0"
name: "安全检测 Agent"
model: "local-security-policy"
capabilities:
  - rate_limit_guard
  - auth_scope_validation
  - prompt_injection_assessment
  - content_redaction
  - audit_trace
trigger_intents:
  - help
execution:
  max_iterations: 1
  timeout_seconds: 10
---
负责 WorkBot 主脑本地安全网关五层治理。

该 Agent 只在本地可信域内工作，负责安全分析、规则执行与审计收口，不负责任何外置触手执行。
