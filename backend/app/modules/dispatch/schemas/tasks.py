from typing import Any

from pydantic import ConfigDict, Field

from app.modules.reception.schemas.messages import MessageRouteDecision
from app.platform.contracts.api_model import APIModel


class ManagerPacket(APIModel):
    manager_agent: str | None = None
    manager_role: str | None = None
    user_goal: str | None = None
    intent: str | None = None
    interaction_mode: str | None = None
    reception_mode: str | None = None
    workflow_mode: str | None = None
    workflow_admission: str | None = None
    task_shape: str | None = None
    decomposition_hint: str | None = None
    delivery_mode: str | None = None
    clarify_required: bool | None = None
    clarify_question: str | None = None
    manager_action: str | None = None
    next_owner: str | None = None
    response_contract: str | None = None
    handoff_summary: str | None = None
    routing_note: str | None = None
    session_state: str | None = None
    state_label: str | None = None


class BrainDispatchSummary(APIModel):
    intent: str | None = None
    dispatch_type: str | None = None
    workflow_mode: str | None = None
    interaction_mode: str | None = None
    reception_mode: str | None = None
    workflow_name: str | None = None
    execution_agent: str | None = None
    manager_action: str | None = None
    next_owner: str | None = None
    delivery_mode: str | None = None
    response_contract: str | None = None
    clarify_required: bool | None = None
    approval_required: bool | None = None
    execution_scope: str | None = None
    summary_line: str | None = None
    routing_strategy: str | None = None
    execution_topology: str | None = None
    fallback_mode: str | None = None
    route_reason_summary: str | None = None
    session_state: str | None = None
    state_label: str | None = None


class TaskResultReference(APIModel):
    title: str
    detail: str | None = None


class TaskExecutionTraceEntry(APIModel):
    stage: str
    title: str
    status: str = "completed"
    detail: str | None = None
    metadata: dict[str, Any] | None = None


class TaskResult(APIModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=APIModel.model_config.get("alias_generator"),
        from_attributes=True,
        extra="allow",
    )

    kind: str
    title: str = ""
    summary: str = ""
    content: str = ""
    text: str | None = None
    bullets: list[str] = Field(default_factory=list)
    references: list[TaskResultReference] = Field(default_factory=list)
    execution_trace: list[TaskExecutionTraceEntry] = Field(default_factory=list)
    contract_version: str | None = None
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    output_snapshot: dict[str, Any] = Field(default_factory=dict)


class TaskAgentGroupMember(APIModel):
    id: str | None = None
    name: str | None = None
    role: str | None = None
    branch_id: str | None = None
    type: str | None = None
    status: str | None = None
    enabled: bool | None = None
    provider_key: str | None = None
    provider_label: str | None = None
    model: str | None = None
    bound_skill_ids: list[str] = Field(default_factory=list)
    bound_tool_ids: list[str] = Field(default_factory=list)
    requested_skill_ids: list[str] = Field(default_factory=list)
    requested_tool_ids: list[str] = Field(default_factory=list)
    nats_subject: str | None = None
    soul: str | None = None
    runtime_status: str | None = None
    current_step_id: str | None = None
    current_step_title: str | None = None
    current_step_message: str | None = None
    current_step_started_at: str | None = None
    current_step_finished_at: str | None = None
    selected_for_delivery: bool | None = None


class TaskAgentGroupTimelineEntry(APIModel):
    id: str | None = None
    kind: str | None = None
    title: str
    detail: str | None = None
    timestamp: str | None = None
    actor_agent_id: str | None = None
    actor_agent_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskAgentGroup(APIModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    topology: str | None = None
    coordination_mode: str | None = None
    dispatcher_agent_id: str | None = None
    development_agents: list[TaskAgentGroupMember] = Field(default_factory=list)
    acceptance_agent: TaskAgentGroupMember | None = None
    requested_skill_ids: list[str] = Field(default_factory=list)
    requested_tool_ids: list[str] = Field(default_factory=list)
    applied_skill_ids: list[str] = Field(default_factory=list)
    applied_tool_ids: list[str] = Field(default_factory=list)
    nats_subjects: dict[str, Any] = Field(default_factory=dict)
    timeline: list[TaskAgentGroupTimelineEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Task(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    title: str
    description: str
    status: str
    priority: str
    created_at: str
    completed_at: str | None = None
    agent: str
    tokens: int
    duration: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None
    trace_id: str | None = None
    channel: str | None = None
    session_id: str | None = None
    user_key: str | None = None
    current_stage: str | None = None
    dispatch_state: str | None = None
    failure_stage: str | None = None
    failure_message: str | None = None
    delivery_status: str | None = None
    delivery_message: str | None = None
    status_reason: str | None = None
    confirmation_status: str | None = None
    approval_status: str | None = None
    approval_required: bool | None = None
    audit_id: str | None = None
    idempotency_key: str | None = None
    execution_scope: str | None = None
    schedule_plan: dict[str, Any] | None = None
    route_decision: MessageRouteDecision | None = None
    manager_packet: ManagerPacket | None = None
    brain_dispatch_summary: BrainDispatchSummary | None = None
    brain_fact_snapshot: dict[str, Any] | None = None
    memory_injection_summary: dict[str, Any] | None = None
    context_patch_audit: list[dict[str, Any]] = []
    state_machine: dict[str, Any] | None = None
    task_agent_group: TaskAgentGroup | None = None
    result: TaskResult | None = None


class TaskListResponse(APIModel):
    items: list[Task]
    total: int


class TaskStep(APIModel):
    id: str
    title: str
    status: str
    agent: str
    started_at: str
    finished_at: str | None = None
    message: str
    metadata: dict[str, Any] | None = None
    tokens: int = 0


class TaskStepsResponse(APIModel):
    items: list[TaskStep]
    total: int


class TaskRealtimeResponse(APIModel):
    type: str = "task.snapshot"
    message_type: str = "snapshot"
    task_id: str
    workflow_id: str | None = None
    timestamp: str | None = None
    task: Task | None = None
    steps: TaskStepsResponse | None = None


class TaskActionResponse(APIModel):
    ok: bool
    message: str
    task: Task | None = None
