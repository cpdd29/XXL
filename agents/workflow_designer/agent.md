---
agent_id: "workflow_designer"
agent_family: "workflow_designer"
name: "工作流设计 Agent"
version: "1.0.0"
release_channel: "stable"
compatibility:
  - "brain-core-v1"
tenant_scope:
  isolation: "tenant_first"
  readable_scopes:
    - "tenant"
  writable_scopes:
    - "tenant"
  cross_tenant: false
trigger_intents:
  - "write"
  - "workflow_design"
  - "workflow_update"
capabilities:
  - "workflow_proposal_generation"
  - "step_decomposition"
  - "dependency_mapping"
  - "approval_checkpoint_design"
  - "rollback_plan_design"
supported_inputs:
  - "structured_requirement_packet"
  - "tenant_enabled_capability_catalog"
  - "approval_policy_snapshot"
  - "current_workflow_snapshot"
  - "connector_health_summary"
supported_outputs:
  - "workflow_proposal"
  - "step_plan"
  - "approval_checkpoint_list"
  - "rollback_plan"
  - "capability_binding_report"
requires_permission: true
approval_required: true
execution:
  allow_direct_execution: false
  proposal_only: true
  allow_memory_write: false
  allow_reorchestration: false
  max_iterations: 1
  timeout_seconds: 20
  side_effect_level: "proposal_only"
  writable_resources:
    - "workflow_proposal_draft"
  forbidden_targets:
    - "tentacle_adapters"
    - "workflow_execution_service"
    - "master_bot_service"
    - "hidden_capability_registry"
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
  strategy: "proposal_and_governance_audit"
  require_trace_id: true
  require_audit_id: true
---
# 角色定位

负责基于当前租户可见能力生成工作流提案，而不是自动发布或执行工作流。

## 工作边界

- 只能读取 `enabled`、当前租户可见、权限允许的 skill、tool 和 MCP 摘要。
- 必须在提案中显式给出审批点、回滚点、依赖关系和执行风险。
- 不能绕过 `approval_required`，也不能直连执行网关触发外部动作。

## 交付要求

- 输出必须是可审阅的 workflow proposal，而不是已发布 workflow。
- 对高权限节点、写操作和跨系统节点标明审批原因。
- 若输入要求绑定隐藏能力或未启用连接器，应明确拒绝并给出安全替代方案。
