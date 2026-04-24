from pydantic import Field

from app.platform.contracts.api_model import APIModel


class RuntimeQueueSnapshot(APIModel):
    key: str
    label: str
    depth: int = 0
    ready: int = 0
    delayed: int = 0
    active_leases: int = 0
    stale_claims: int = 0
    retry_scheduled: int = 0
    dead_letters: int = 0


class RuntimeAlert(APIModel):
    key: str
    severity: str = "warning"
    title: str
    detail: str
    source: str
    href: str | None = None
    workflow_run_id: str | None = None
    task_id: str | None = None
    updated_at: str | None = None


class RuntimeSnapshot(APIModel):
    timestamp: str
    total_queue_depth: int = 0
    dispatch_queue_depth: int = 0
    workflow_execution_queue_depth: int = 0
    agent_execution_queue_depth: int = 0
    active_dispatch_leases: int = 0
    active_workflow_execution_leases: int = 0
    active_agent_execution_leases: int = 0
    stale_claims: int = 0
    retry_scheduled: int = 0
    dead_letters: int = 0
    queues: list[RuntimeQueueSnapshot] = Field(default_factory=list)
    recent_alerts: list[RuntimeAlert] = Field(default_factory=list)
