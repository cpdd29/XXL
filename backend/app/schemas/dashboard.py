from typing import Any

from app.schemas.base import APIModel


class DashboardTrend(APIModel):
    time: str
    requests: int
    tokens: int


class DashboardStat(APIModel):
    key: str
    title: str
    value: str | int
    description: str
    trend_value: int
    trend_positive: bool


class DashboardAgentStatus(APIModel):
    id: str
    name: str
    type: str
    status: str
    tasks_completed: int
    avg_response_time: str


class DashboardRealtimeLog(APIModel):
    id: str
    timestamp: str
    type: str
    agent: str
    message: str


class DashboardFailureBreakdownItem(APIModel):
    stage: str
    label: str
    count: int


class DashboardStatsResponse(APIModel):
    stats: list[DashboardStat]
    chart_data: list[DashboardTrend]
    agent_statuses: list[DashboardAgentStatus]
    failure_breakdown: list[DashboardFailureBreakdownItem]
    realtime_logs: list[DashboardRealtimeLog]


class AuditLog(APIModel):
    id: str
    timestamp: str
    action: str
    user: str
    resource: str
    status: str
    ip: str
    details: str
    metadata: dict[str, Any] | None = None


class AuditLogsResponse(APIModel):
    items: list[AuditLog]
    total: int
    limit: int
    offset: int
    has_more: bool
