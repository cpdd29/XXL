from enum import Enum

from pydantic import ConfigDict, Field

from app.schemas.base import APIModel, to_camel
from app.schemas.messages import MessageRouteDecision
from app.schemas.runtime import RuntimeSnapshot
from app.schemas.tasks import BrainDispatchSummary, ManagerPacket


class WorkflowTriggerType(str, Enum):
    MESSAGE = "message"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    INTERNAL = "internal"
    MANUAL = "manual"


class WorkflowTrigger(APIModel):
    type: WorkflowTriggerType = WorkflowTriggerType.MESSAGE
    keyword: str | None = None
    cron: str | None = None
    webhook_path: str | None = None
    internal_event: str | None = None
    description: str | None = None
    priority: int = 100
    channels: list[str] = Field(default_factory=list)
    preferred_language: str | None = None
    step_delay_seconds: float | None = None
    max_dispatch_retry: int | None = None
    dispatch_retry_backoff_seconds: float | None = None
    execution_timeout_seconds: float | None = None
    natural_language_rule: str | None = None
    schedule_plan: dict[str, object] | None = None


class WorkflowNode(APIModel):
    id: str
    type: str
    label: str
    x: float
    y: float
    description: str | None = None
    config: dict[str, object] | None = None
    agent_id: str | None = None
    tool_id: str | None = None
    workflow_id: str | None = None


class WorkflowEdge(APIModel):
    id: str
    source: str
    target: str
    source_handle: str | None = None


class Workflow(APIModel):
    id: str
    name: str
    description: str
    version: str
    status: str
    updated_at: str
    node_count: int
    edge_count: int
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    trigger: str | WorkflowTrigger = Field(default_factory=WorkflowTrigger)
    agent_bindings: list[str] = Field(default_factory=list)


class WorkflowListResponse(APIModel):
    items: list[Workflow]
    total: int


class UpsertWorkflowRequest(APIModel):
    name: str
    description: str
    version: str = "v1.0"
    status: str = "draft"
    trigger: str | WorkflowTrigger = Field(default_factory=WorkflowTrigger)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    agent_bindings: list[str] = Field(default_factory=list)


class RunWorkflowRequest(APIModel):
    trigger: str = "manual"
    intent: str | None = None
    audit_id: str | None = None
    idempotency_key: str | None = None
    execution_scope: str | None = None
    requires_approval: bool | None = None


class WorkflowRunManualHandoffRequest(APIModel):
    operator: str | None = None
    note: str | None = None
    approval_id: str | None = None
    approval_reason: str | None = None
    approval_note: str | None = None


class InternalWorkflowTriggerRequest(APIModel):
    source: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = None


class WorkflowActionResponse(APIModel):
    ok: bool
    message: str
    workflow: Workflow | None = None
    run_id: str | None = None
    task_id: str | None = None
    triggered_count: int | None = None
    triggered_workflow_ids: list[str] | None = None
    triggered_run_ids: list[str] | None = None
    triggered_task_ids: list[str] | None = None
    internal_event_id: str | None = None
    internal_event_status: str | None = None
    internal_event_attempt_count: int | None = None
    deduplicated: bool | None = None


class InternalEventDelivery(APIModel):
    id: str
    event_name: str
    source: str
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = None
    status: str
    attempt_count: int = 0
    last_error: str | None = None
    triggered_count: int = 0
    triggered_workflow_ids: list[str] = Field(default_factory=list)
    triggered_run_ids: list[str] = Field(default_factory=list)
    triggered_task_ids: list[str] = Field(default_factory=list)
    primary_workflow: Workflow | None = None
    created_at: str
    updated_at: str
    delivered_at: str | None = None


class InternalEventDeliveryListResponse(APIModel):
    items: list[InternalEventDelivery]
    total: int


class InternalEventDeliveryActionResponse(APIModel):
    ok: bool
    message: str
    delivery: InternalEventDelivery
    workflow: Workflow | None = None
    replayed_from_delivery_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    triggered_count: int | None = None
    triggered_workflow_ids: list[str] | None = None
    triggered_run_ids: list[str] | None = None
    triggered_task_ids: list[str] | None = None
    internal_event_id: str | None = None
    internal_event_status: str | None = None
    internal_event_attempt_count: int | None = None
    deduplicated: bool | None = None


class WorkflowRunNodeError(APIModel):
    id: str
    timestamp: str | None = None
    severity: str = "error"
    source: str
    agent: str
    message: str
    step_id: str | None = None
    step_title: str | None = None


class WorkflowRunNode(APIModel):
    id: str
    type: str
    label: str
    status: str
    agent_id: str | None = None
    message: str | None = None
    tokens: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    latest_error: str | None = None
    latest_error_at: str | None = None
    error_count: int = 0
    error_history: list[WorkflowRunNodeError] = Field(default_factory=list)


class WorkflowRunLog(APIModel):
    id: str
    timestamp: str
    type: str
    agent: str
    message: str


class WorkflowRunDispatchMemoryItem(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    memory_id: str | None = None
    source_mid_term_id: str | None = None
    memory_type: str | None = None
    source: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    score: float | None = None
    matched_terms: list[str] = Field(default_factory=list)
    rerank_score: float | None = None


class WorkflowRunExecutionPlanStep(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    id: str
    index: int
    branch_id: str | None = None
    intent: str | None = None
    role: str | None = None
    completion_policy: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    agent_type: str | None = None
    title: str | None = None


class WorkflowRunExecutionPlanFallback(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    mode: str | None = None
    target: str | None = None
    on_failure: str | None = None
    summary: str | None = None


class WorkflowRunExecutionPlanRationale(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    intent: str | None = None
    workflow_mode: str | None = None
    interaction_mode: str | None = None
    routing_strategy: str | None = None
    route_reason_summary: str | None = None
    candidate_count: int = 0
    skipped_count: int = 0


class WorkflowRunExecutionPlanSnapshot(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    version: str
    planner: str | None = None
    aggregator: str | None = None
    plan_type: str | None = None
    coordination_mode: str | None = None
    step_count: int = 0
    planned_agent_count: int = 0
    workflow_id: str | None = None
    workflow_name: str | None = None
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    current_owner: str | None = None
    summary: str | None = None
    steps: list[WorkflowRunExecutionPlanStep] = Field(default_factory=list)
    fan_out: dict[str, object] | None = None
    fan_in: dict[str, object] | None = None
    winner_strategy: str | None = None
    quorum: dict[str, object] | None = None
    merge_strategy: str | None = None
    cancel_policy: dict[str, object] | None = None
    fallback: WorkflowRunExecutionPlanFallback | None = None
    route_rationale: WorkflowRunExecutionPlanRationale | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowRunFallbackHistoryItem(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    id: str
    timestamp: str
    state: str
    failure_stage: str
    reason: str
    message: str
    policy_mode: str | None = None
    policy_target: str | None = None
    resolved_action: str


class WorkflowRunDispatchContext(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
        extra="allow",
    )

    type: str | None = None
    state: str | None = None
    queued_at: str | None = None
    updated_at: str | None = None
    entrypoint: str | None = None
    entrypoint_agent: str | None = None
    trace_id: str | None = None
    channel: str | None = None
    message_id: str | None = None
    platform_user_id: str | None = None
    chat_id: str | None = None
    user_key: str | None = None
    session_id: str | None = None
    detected_lang: str | None = None
    preferred_language: str | None = None
    message_preview: str | None = None
    memory_hits: int = 0
    memory_items: list[WorkflowRunDispatchMemoryItem] = Field(default_factory=list)
    route_decision: MessageRouteDecision | None = None
    manager_packet: ManagerPacket | None = None
    brain_dispatch_summary: BrainDispatchSummary | None = None
    brain_fact_snapshot: dict[str, object] | None = None
    execution_plan_snapshot: WorkflowRunExecutionPlanSnapshot | None = None
    fallback_history: list[WorkflowRunFallbackHistoryItem] = Field(default_factory=list)
    dispatched_at: str | None = None
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    fallback_recovery_state: str | None = None
    fallback_recovery_reason: str | None = None
    fallback_recovery_action: str | None = None
    fallback_recovery_at: str | None = None
    manual_handoff_required_at: str | None = None
    manual_handoff_source: str | None = None
    manual_handoff_operator: str | None = None
    manual_handoff_note: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    failure_stage: str | None = None
    failure_message: str | None = None
    delivery_status: str | None = None
    delivery_message: str | None = None
    delivery_completed_at: str | None = None
    delivery_failed_at: str | None = None
    result_kind: str | None = None
    context_patch_count: int = 0
    last_context_patch_at: str | None = None
    last_context_patch_trace_id: str | None = None
    last_context_patch_preview: str | None = None
    workflow_policy: dict[str, object] | None = None


class WorkflowRunMonitor(APIModel):
    trigger_type: str
    dispatch_state: str | None = None
    monitor_state: str
    next_action: str
    next_dispatch_at: str | None = None
    is_overdue: bool = False
    dispatcher_id: str | None = None
    dispatch_claimed_at: str | None = None
    dispatch_lease_expires_at: str | None = None
    dispatch_failure_count: int = 0
    last_dispatch_error: str | None = None
    execution_agent_id: str | None = None
    warning_count: int = 0
    latest_warning: str | None = None


class WorkflowRunMetrics(APIModel):
    tokens_total: int = 0
    duration_ms: int | None = None
    step_count: int = 0
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    agent_started_at: str | None = None
    agent_finished_at: str | None = None


class WorkflowRun(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    workflow_id: str
    workflow_name: str
    task_id: str | None = None
    trigger: str
    intent: str | None = None
    status: str
    created_at: str
    updated_at: str
    started_at: str
    completed_at: str | None = None
    current_stage: str
    active_edges: list[str] = Field(default_factory=list)
    nodes: list[WorkflowRunNode] = Field(default_factory=list)
    logs: list[WorkflowRunLog] = Field(default_factory=list)
    failure_stage: str | None = None
    failure_message: str | None = None
    delivery_status: str | None = None
    delivery_message: str | None = None
    status_reason: str | None = None
    metrics: WorkflowRunMetrics | None = None
    tokens_total: int = 0
    duration_ms: int | None = None
    step_count: int = 0
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    agent_started_at: str | None = None
    agent_finished_at: str | None = None
    dispatch_context: WorkflowRunDispatchContext | None = None
    monitor: WorkflowRunMonitor | None = None


class WorkflowRunListResponse(APIModel):
    items: list[WorkflowRun]
    total: int


class WorkflowMonitorStats(APIModel):
    total: int = 0
    queued: int = 0
    scheduled: int = 0
    claimed: int = 0
    claimed_stale: int = 0
    running: int = 0
    retry_waiting: int = 0
    overdue: int = 0
    execution_timeout: int = 0
    failed: int = 0
    completed: int = 0
    cancelled: int = 0
    unhealthy: int = 0


class WorkflowMonitorResponse(APIModel):
    workflow_id: str
    timestamp: str
    workflow: Workflow
    stats: WorkflowMonitorStats
    items: list[WorkflowRun]
    alerts: list[str] = Field(default_factory=list)
    runtime: RuntimeSnapshot | None = None
