from typing import Any

from app.schemas.base import APIModel
from app.schemas.runtime import RuntimeSnapshot


class DashboardTrend(APIModel):
    time: str
    requests: int
    tokens: int
    duration_ms: int = 0


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


class DashboardTentacleMetric(APIModel):
    agent_id: str | None = None
    name: str
    type: str
    calls: int
    success_calls: int
    success_rate: float
    tokens: int = 0
    duration_ms: int = 0


class DashboardCostSummary(APIModel):
    run_count: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: int = 0


class DashboardCostDistributionItem(APIModel):
    label: str
    calls: int
    tokens: int = 0
    duration_ms: int = 0
    share_percent: float = 0.0


class DashboardSlaThreshold(APIModel):
    metric: str
    healthy_gte: float | None = None
    healthy_lte: float | None = None
    degraded_gte: float | None = None
    degraded_lte: float | None = None


class DashboardSlaSummary(APIModel):
    window_hours: int = 24
    total_runs: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    timeout_rate: float = 0.0
    fallback_rate: float = 0.0
    delivery_failure_rate: float = 0.0
    security_risk_rate: float = 0.0
    health_status: str = "healthy"


class DashboardHealthSignal(APIModel):
    key: str
    label: str
    status: str
    value: float
    unit: str = "%"
    summary: str
    threshold: DashboardSlaThreshold


class DashboardPreparedAlert(APIModel):
    key: str
    severity: str
    title: str
    detail: str
    source: str
    href: str | None = None


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


class DashboardBrainBreakdownItem(APIModel):
    key: str
    label: str
    count: int
    hint: str | None = None


class DashboardManagerQueueItem(APIModel):
    task_id: str
    title: str
    status: str
    manager_action: str | None = None
    next_owner: str | None = None
    response_contract: str | None = None
    delivery_mode: str | None = None
    task_shape: str | None = None
    clarify_question: str | None = None
    current_stage: str | None = None
    session_state: str | None = None
    state_label: str | None = None


class DashboardReplyQueueItem(APIModel):
    task_id: str
    title: str
    channel: str | None = None
    user_label: str | None = None
    user_key: str | None = None
    session_id: str | None = None
    status: str
    clarify_question: str | None = None
    current_stage: str | None = None
    next_owner: str | None = None
    reception_mode: str | None = None
    workflow_mode: str | None = None
    response_contract: str | None = None
    confirmation_status: str | None = None
    session_state: str | None = None
    state_label: str | None = None


class DashboardStatsResponse(APIModel):
    stats: list[DashboardStat]
    chart_data: list[DashboardTrend]
    agent_statuses: list[DashboardAgentStatus]
    cost_summary: DashboardCostSummary
    sla_summary: DashboardSlaSummary
    health_signals: list[DashboardHealthSignal]
    prepared_alerts: list[DashboardPreparedAlert]
    tentacle_metrics: list[DashboardTentacleMetric]
    cost_distribution: list[DashboardCostDistributionItem]
    failure_breakdown: list[DashboardFailureBreakdownItem]
    brain_breakdown: list[DashboardBrainBreakdownItem]
    manager_queue: list[DashboardManagerQueueItem]
    reply_queue: list[DashboardReplyQueueItem]
    realtime_logs: list[DashboardRealtimeLog]
    runtime: RuntimeSnapshot


class AuditLog(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
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
