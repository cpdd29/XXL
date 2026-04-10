from app.schemas.base import APIModel
from app.schemas.messages import MessageRouteDecision


class TaskResultReference(APIModel):
    title: str
    detail: str | None = None


class TaskExecutionTraceEntry(APIModel):
    stage: str
    title: str
    status: str = "completed"
    detail: str | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


class TaskResult(APIModel):
    kind: str
    title: str = ""
    summary: str = ""
    content: str = ""
    text: str | None = None
    bullets: list[str] = []
    references: list[TaskResultReference] = []
    execution_trace: list[TaskExecutionTraceEntry] = []


class Task(APIModel):
    id: str
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
    route_decision: MessageRouteDecision | None = None
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
    tokens: int = 0


class TaskStepsResponse(APIModel):
    items: list[TaskStep]
    total: int


class TaskActionResponse(APIModel):
    ok: bool
    message: str
    task: Task | None = None
