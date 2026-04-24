from typing import Any

from pydantic import Field

from app.platform.contracts.api_model import APIModel


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


class AgentBoundTool(APIModel):
    id: str
    name: str
    type: str
    description: str | None = None
    source: str | None = None


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
    bound_tool_ids: list[str] = Field(default_factory=list)
    bound_tools: list[AgentBoundTool] = Field(default_factory=list)
    agent_workflow_id: str | None = None
    input_contract: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    contract_version: str | None = None
    deletable: bool = True
    delete_blocked_reason: str | None = None


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


class AgentEnabledRequest(APIModel):
    enabled: bool


class AgentDeleteResponse(APIModel):
    ok: bool
    message: str
    agent_id: str


class AgentConfigRequest(APIModel):
    name: str
    description: str = ""
    type: str = "default"
    enabled: bool = True
    provider_key: str | None = None
    model: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)
    agent_workflow_id: str | None = None
    input_contract: dict[str, Any] | None = None
    output_contract: dict[str, Any] | None = None
    contract_version: str | None = None

    def model_dump(self, *args, **kwargs) -> dict[str, Any]:
        dumped = super().model_dump(*args, **kwargs)
        if not kwargs.get("exclude_none"):
            return dumped

        by_alias = bool(kwargs.get("by_alias"))
        for field_name in (
            "agent_workflow_id",
            "input_contract",
            "output_contract",
            "contract_version",
        ):
            if field_name not in self.model_fields_set:
                continue
            if getattr(self, field_name) is not None:
                continue
            field_info = self.__class__.model_fields[field_name]
            dumped[field_info.alias if by_alias and field_info.alias else field_name] = None
        return dumped


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
