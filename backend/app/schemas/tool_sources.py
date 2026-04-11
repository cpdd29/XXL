from typing import Any

from app.schemas.base import APIModel


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
