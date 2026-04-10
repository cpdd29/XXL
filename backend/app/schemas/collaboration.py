from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.workflows import Workflow, WorkflowRunNodeError


class CollaborationTaskOption(APIModel):
    id: str
    title: str
    status: str
    priority: str
    agent: str


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
