from typing import Any

from app.platform.contracts.api_model import APIModel


class ToolItem(APIModel):
    id: str
    name: str
    type: str
    source: str
    enabled: bool
    description: str
    tags: list[str] = []
    provider: str
    source_kind: str | None = None
    bridge_mode: str | None = None
    health_status: str = "unknown"
    agent_ids: list[str] = []
    permissions: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    recent_call_summary: dict[str, Any] | None = None
    config_summary: dict[str, Any] | None = None
    health_summary: dict[str, Any] | None = None
    migration_stage: dict[str, Any] | None = None
    rollback: dict[str, Any] | None = None
    traffic_policy: dict[str, Any] | None = None


class ToolListResponse(APIModel):
    items: list[ToolItem]
    total: int


class ToolCatalogResponse(ToolListResponse):
    source_summary: dict[str, int] = {}
    type_summary: dict[str, int] = {}
    sources: list[dict[str, Any]] = []
    scanned_at: str


class ToolHealthItem(APIModel):
    tool_id: str
    tool_name: str
    source: str
    provider: str
    status: str
    checked_at: str
    reason: str = ""
    runtime: dict[str, Any] = {}


class ToolHealthResponse(APIModel):
    items: list[ToolHealthItem]
    total: int
    summary: dict[str, int] = {}
    checked_at: str
