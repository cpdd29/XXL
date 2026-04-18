from typing import Any

from pydantic import Field

from app.schemas.base import APIModel


class AgentModelBinding(APIModel):
    provider_key: str | None = None
    provider_label: str | None = None
    model: str | None = None
    source: str | None = None


class AgentBoundSkill(APIModel):
    id: str
    name: str
    file_name: str
    format: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


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
    model_binding: AgentModelBinding | None = None
    bound_skill_ids: list[str] = Field(default_factory=list)
    bound_skills: list[AgentBoundSkill] = Field(default_factory=list)


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


class AgentConfigRequest(APIModel):
    name: str
    description: str = ""
    type: str = "default"
    enabled: bool = True
    provider_key: str | None = None
    model: str | None = None
    skill_ids: list[str] = Field(default_factory=list)


class BrainSkillItem(APIModel):
    id: str
    name: str
    file_name: str
    format: str
    description: str | None = None
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    uploaded_at: str | None = None


class BrainSkillListResponse(APIModel):
    items: list[BrainSkillItem]
    total: int


class BrainSkillUploadRequest(APIModel):
    file_name: str
    content: str


class BrainSkillActionResponse(APIModel):
    ok: bool
    message: str
    skill: BrainSkillItem


class BrainSkillDeleteResponse(APIModel):
    ok: bool
    message: str
    skill_id: str
