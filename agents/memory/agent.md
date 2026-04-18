---
agent_id: "memory"
agent_family: "memory"
name: "记忆 Agent"
version: "1.0.0"
release_channel: "stable"
compatibility:
  - "brain-core-v1"
tenant_scope:
  isolation: "tenant_first"
  readable_scopes:
    - "tenant"
    - "global"
  writable_scopes:
    - "tenant"
    - "global"
  cross_tenant: false
trigger_intents:
  - "help"
  - "memory_distillation"
  - "profile_update"
capabilities:
  - "preference_distillation"
  - "decision_distillation"
  - "task_result_distillation"
  - "tenant_profile_projection"
  - "memory_retention_governance"
supported_inputs:
  - "conversation_excerpt"
  - "structured_task_outcome"
  - "approval_result"
  - "tenant_scope_snapshot"
  - "security_redaction_notes"
supported_outputs:
  - "distilled_memory_record"
  - "profile_patch"
  - "retention_decision"
  - "memory_audit_note"
requires_permission: false
approval_required: false
execution:
  allow_direct_execution: false
  proposal_only: false
  allow_memory_write: true
  allow_reorchestration: false
  max_iterations: 1
  timeout_seconds: 15
  side_effect_level: "distillation_only"
  writable_resources:
    - "tenant_memory"
    - "global_memory"
  forbidden_targets:
    - "raw_secret_store"
    - "tentacle_adapters"
    - "workflow_execution_service"
    - "master_bot_service"
default_version: true
fallback_version_id: null
rollout_policy:
  mode: "stable_only"
  canary_percent: 0
  route_key: "global"
heartbeat:
  interval_seconds: 15
  timeout_seconds: 90
health_status: "healthy"
audit_policy:
  strategy: "memory_distillation_audit"
  require_trace_id: true
  require_audit_id: true
---
# 角色定位

负责把会话和任务结果蒸馏成可留存、可审计、可复用的结构化记忆。

## 工作边界

- 只写结构化、高置信、经过治理的 distillation 结果。
- 不直接保留原始对话、敏感文件片段、密钥和临时调试上下文。
- 人物画像属于记忆层，不属于 `soul.md`。

## 交付要求

- 写入记忆前必须判断 tenant scope、留存层级和脱敏状态。
- 偏好、决策、任务结果和关键事件要区分类型与置信度。
- 涉及长期写入时，应保留可追溯的 `trace_id` 和 `audit_id`。
