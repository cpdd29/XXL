from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.messages import MessageRouteDecision
from app.schemas.tasks import BrainDispatchSummary, ManagerPacket
from app.schemas.workflows import Workflow, WorkflowRunNodeError


class CollaborationTaskOption(APIModel):
    id: str
    title: str
    status: str
    priority: str
    agent: str


class CollaborationExecutionPlanStep(APIModel):
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


class CollaborationExecutionPlanFallback(APIModel):
    mode: str | None = None
    target: str | None = None
    on_failure: str | None = None
    summary: str | None = None


class CollaborationExecutionPlanRationale(APIModel):
    intent: str | None = None
    workflow_mode: str | None = None
    interaction_mode: str | None = None
    routing_strategy: str | None = None
    route_reason_summary: str | None = None
    candidate_count: int = 0
    skipped_count: int = 0


class CollaborationExecutionPlanBranchResult(APIModel):
    step_id: str | None = None
    branch_id: str | None = None
    intent: str | None = None
    agent: str | None = None
    status: str | None = None
    score: int = 0


class CollaborationExecutionPlan(APIModel):
    version: str
    planner: str | None = None
    aggregator: str | None = None
    plan_type: str
    coordination_mode: str
    step_count: int
    planned_agent_count: int | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    current_owner: str | None = None
    summary: str | None = None
    steps: list[CollaborationExecutionPlanStep] = Field(default_factory=list)
    fan_out: dict | None = None
    fan_in: dict | None = None
    winner_strategy: str | None = None
    quorum: dict | None = None
    merge_strategy: str | None = None
    cancel_policy: dict | None = None
    fallback: CollaborationExecutionPlanFallback | None = None
    route_rationale: CollaborationExecutionPlanRationale | None = None
    selected_branch_id: str | None = None
    selected_agent: str | None = None
    successful_agents: int = 0
    failed_agents: int = 0
    cancelled_agents: int = 0
    branch_results: list[CollaborationExecutionPlanBranchResult] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class CollaborationFallbackHistoryItem(APIModel):
    id: str
    timestamp: str
    state: str
    failure_stage: str
    reason: str
    message: str
    policy_mode: str | None = None
    policy_target: str | None = None
    resolved_action: str


class CollaborationSession(APIModel):
    task_id: str
    task_title: str
    task_status: str
    task_priority: str
    workflow_id: str
    workflow_name: str
    started_at: str
    completed_at: str | None = None
    total_tokens: int
    progress_percent: int
    current_stage: str
    failure_stage: str | None = None
    failure_message: str | None = None
    dispatch_state: str | None = None
    delivery_status: str | None = None
    delivery_message: str | None = None
    status_reason: str | None = None
    active_agent_count: int
    completed_steps: int
    total_steps: int
    workflow_run_id: str | None = None
    route_decision: MessageRouteDecision | None = None
    manager_packet: ManagerPacket | None = None
    brain_dispatch_summary: BrainDispatchSummary | None = None
    execution_plan: CollaborationExecutionPlan | None = None
    fallback_history: list[CollaborationFallbackHistoryItem] = Field(default_factory=list)
    memory_injection_summary: dict | None = None
    context_patch_audit: list[dict] = Field(default_factory=list)
    state_machine: dict | None = None


class CollaborationNode(APIModel):
    id: str
    type: str
    label: str
    status: str
    agent_type: str | None = None
    tokens: int = 0
    message: str | None = None
    latest_error: str | None = None
    latest_error_at: str | None = None
    error_count: int = 0
    error_history: list[WorkflowRunNodeError] = Field(default_factory=list)


class CollaborationLog(APIModel):
    id: str
    timestamp: str
    type: str
    agent: str
    message: str


class CollaborationOverviewResponse(APIModel):
    session: CollaborationSession
    tasks: list[CollaborationTaskOption]
    workflow: Workflow
    nodes: list[CollaborationNode]
    active_edges: list[str]
    logs: list[CollaborationLog]
