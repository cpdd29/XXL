from typing import Any, Literal

from pydantic import Field

from app.modules.agent_config.schemas.agents import Agent
from app.platform.observability.schemas.dashboard import AuditLog
from app.platform.contracts.api_model import APIModel


class ExternalConnectionAuthHeaders(APIModel):
    token: str | None = None
    timestamp: str | None = None
    signature: str | None = None
    nonce: str | None = None


class ExternalAgentRegistrationRequest(APIModel):
    id: str
    name: str
    description: str | None = None
    type: str
    version: str = "0.0.0"
    agent_family: str | None = None
    compatibility: list[str] = Field(default_factory=list)
    release_channel: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    protocol: str | None = None
    base_url: str | None = None
    invoke_path: str | None = None
    health_path: str | None = None
    method: str | None = None
    heartbeat_interval_seconds: int | None = None
    heartbeat_timeout_seconds: int | None = None
    enabled: bool = True
    default_version: bool = False
    fallback_version_id: str | None = None
    deprecated: bool = False
    rollout_policy: dict[str, Any] = Field(default_factory=dict)
    rollback_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalSkillRegistrationRequest(APIModel):
    id: str
    name: str
    description: str | None = None
    skill_family: str | None = None
    version: str = "0.0.0"
    compatibility: list[str] = Field(default_factory=list)
    release_channel: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    protocol: str | None = None
    base_url: str | None = None
    invoke_path: str | None = None
    health_path: str | None = None
    method: str | None = None
    heartbeat_interval_seconds: int | None = None
    heartbeat_timeout_seconds: int | None = None
    enabled: bool = True
    default_version: bool = False
    fallback_version_id: str | None = None
    deprecated: bool = False
    timeout_seconds: float | None = None
    rollout_policy: dict[str, Any] = Field(default_factory=dict)
    rollback_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalHeartbeatRequest(APIModel):
    status: str | None = None
    load: float | None = None
    queue_depth: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalFailureReportRequest(APIModel):
    error: str | None = None


class ExternalCapabilityActionResponse(APIModel):
    ok: bool
    message: str
    capability_type: Literal["agent", "skill"]
    item: dict[str, Any]


class ExternalCapabilityRolloutPolicy(APIModel):
    canary_percent: int = 0
    route_key: str = "global"


class ExternalCapabilityRollbackPolicy(APIModel):
    active: bool = False
    target_version_id: str | None = None


class ExternalCapabilityHealthItem(APIModel):
    capability_type: Literal["agent", "skill"]
    id: str
    name: str
    family: str | None = None
    version: str | None = None
    compatibility: list[str] = Field(default_factory=list)
    release_channel: str | None = None
    status: str
    routable: bool
    circuit_state: str | None = None
    consecutive_failures: int = 0
    next_retry_at: str | None = None
    last_heartbeat_at: str | None = None
    health: dict[str, Any] = Field(default_factory=dict)
    invocation: dict[str, Any] = Field(default_factory=dict)


class ExternalCapabilityHealthResponse(APIModel):
    items: list[ExternalCapabilityHealthItem]
    total: int
    summary: dict[str, Any]


class ExternalAgentListResponse(APIModel):
    items: list[Agent]
    total: int


class ExternalCapabilityVersionItem(APIModel):
    capability_type: Literal["agent", "skill"]
    id: str
    family: str
    name: str
    version: str
    release_channel: str | None = None
    compatibility: list[str] = Field(default_factory=list)
    default_version: bool = False
    fallback_version_id: str | None = None
    deprecated: bool = False
    enabled: bool = True
    routable: bool = False
    status: str | None = None
    rollout_policy: ExternalCapabilityRolloutPolicy = Field(default_factory=ExternalCapabilityRolloutPolicy)
    rollback_policy: ExternalCapabilityRollbackPolicy = Field(default_factory=ExternalCapabilityRollbackPolicy)


class ExternalCapabilityVersionListResponse(APIModel):
    items: list[ExternalCapabilityVersionItem]
    total: int


class ExternalCapabilityVersionUpdateRequest(APIModel):
    fallback_version_id: str | None = None
    deprecated: bool | None = None
    rollout_policy: dict[str, Any] | None = None
    rollback_policy: dict[str, Any] | None = None


class ExternalCapabilityGovernanceFamilySummary(APIModel):
    capability_type: Literal["agent", "skill"]
    family: str
    name: str
    current_id: str
    current_version: str | None = None
    release_channel: str | None = None
    compatibility: list[str] = Field(default_factory=list)
    default_version_id: str | None = None
    fallback_version_id: str | None = None
    deprecated: bool = False
    enabled: bool = True
    routable: bool = False
    status: str
    circuit_state: str | None = None
    consecutive_failures: int = 0
    next_retry_at: str | None = None
    last_heartbeat_at: str | None = None
    health: dict[str, Any] = Field(default_factory=dict)
    invocation: dict[str, Any] = Field(default_factory=dict)
    rollout_policy: ExternalCapabilityRolloutPolicy = Field(default_factory=ExternalCapabilityRolloutPolicy)
    rollback_policy: ExternalCapabilityRollbackPolicy = Field(default_factory=ExternalCapabilityRollbackPolicy)
    version_count: int = 0


class ExternalCapabilityGovernanceSummary(APIModel):
    agent_families: int = 0
    skill_families: int = 0
    total_families: int = 0
    total_versions: int = 0
    routable: int = 0
    open_circuits: int = 0
    offline: int = 0


class ExternalCapabilityGovernanceOverviewResponse(APIModel):
    items: list[ExternalCapabilityGovernanceFamilySummary]
    total: int
    summary: ExternalCapabilityGovernanceSummary
    recent_audits: list[AuditLog] = Field(default_factory=list)
