from typing import Any

from pydantic import Field

from app.schemas.base import APIModel


class Agent(APIModel):
    id: str
    name: str
    description: str
    type: str
    status: str
    enabled: bool
    tasks_completed: int
    tasks_total: int
    avg_response_time: str
    tokens_used: int
    tokens_limit: int
    success_rate: float
    last_active: str
    runtime_status: str | None = None
    runtime_status_reason: str | None = None
    routable: bool | None = None
    runtime_priority: int | None = None
    last_heartbeat_at: str | None = None
    heartbeat_interval_seconds: int | None = None
    heartbeat_timeout_seconds: int | None = None
    runtime_metrics: dict[str, Any] = Field(default_factory=dict)
    config_summary: dict[str, Any] | None = None
    config_snapshot: dict[str, Any] | None = None


class AgentListResponse(APIModel):
    items: list[Agent]
    total: int


class AgentHeartbeatRequest(APIModel):
    status: str | None = None
    interval_seconds: int | None = None
    timeout_seconds: int | None = None
    source: str | None = None
    load: float | None = None
    queue_depth: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentActionResponse(APIModel):
    ok: bool
    message: str
    agent: Agent
