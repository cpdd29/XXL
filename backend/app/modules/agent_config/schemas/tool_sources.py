from typing import Any

from pydantic import Field

from app.platform.contracts.api_model import APIModel


class ToolSourceItem(APIModel):
    id: str
    name: str
    kind: str
    path: str
    status: str
    scan_status: str
    tool_count: int
    notes: list[str] = []
    registry: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    config_summary: dict[str, Any] | None = None
    health_summary: dict[str, Any] | None = None
    bridge_summary: dict[str, Any] | None = None
    doctor_summary: dict[str, Any] | None = None
    migration_summary: dict[str, Any] | None = None
    traffic_policy: dict[str, Any] | None = None
    rollback: dict[str, Any] | None = None


class ToolSourceListResponse(APIModel):
    governance_summary: dict[str, Any]
    items: list[ToolSourceItem]
    total: int


class ToolSourceScanResponse(ToolSourceListResponse):
    ok: bool
    message: str


class ToolSourceToolItem(APIModel):
    id: str
    name: str
    type: str
    provider: str
    source_kind: str | None = None
    bridge_mode: str | None = None
    enabled: bool
    permissions: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    recent_call_summary: dict[str, Any] | None = None
    config_summary: dict[str, Any] | None = None
    health_summary: dict[str, Any] | None = None
    migration_stage: dict[str, Any] | None = None
    rollback: dict[str, Any] | None = None
    traffic_policy: dict[str, Any] | None = None


class ToolSourceDetailResponse(ToolSourceItem):
    governance_summary: dict[str, Any]
    tools: list[ToolSourceToolItem]
    tool_total: int
    scanned_at: str


class ToolSourceSkillRegistrationRequest(APIModel):
    id: str | None = None
    name: str
    description: str | None = None
    skill_family: str | None = None
    version: str = "1.0.0"
    base_url: str
    invoke_path: str = "/invoke"
    health_path: str | None = "/health"
    method: str = "POST"
    protocol: str = "http"
    provider: str | None = None
    enabled: bool = True
    timeout_seconds: float = 8.0
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    source_id: str | None = None
    source_name: str | None = None


class ToolSourceMcpRegistrationRequest(APIModel):
    id: str | None = None
    name: str
    description: str | None = None
    base_url: str
    invoke_path: str = "/invoke"
    method: str = "POST"
    provider: str | None = None
    enabled: bool = True
    timeout_seconds: float = 10.0
    requires_permission: bool = False
    approval_required: bool | None = None
    tags: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["agents:read"])
    roles: list[str] = Field(default_factory=lambda: ["admin", "operator", "power_user", "viewer"])
    source_id: str | None = None
    source_name: str | None = None


class ToolSourceRegistrationResponse(APIModel):
    ok: bool
    message: str
    source_id: str
    tool_id: str
    source: dict[str, Any]
    tool: dict[str, Any]


class ToolSourceDeleteResponse(APIModel):
    ok: bool
    message: str
    source_id: str
    tool_id: str
