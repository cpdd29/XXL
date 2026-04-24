from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "acknowledged", "resolved", "suppressed"]
AlertSubscriptionChannel = Literal["telegram", "wecom", "feishu", "dingtalk"]


class AlertCenterItem(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    source_type: str
    source_id: str
    source: str
    severity: AlertSeverity
    status: AlertStatus
    category: str
    title: str
    message: str
    occurred_at: str
    first_occurred_at: str | None = None
    last_occurred_at: str | None = None
    updated_at: str
    resource: str | None = None
    user_key: str | None = None
    trace_id: str | None = None
    workflow_run_id: str | None = None
    href: str | None = None
    dedupe_key: str | None = None
    aggregate_count: int = 1
    aggregate_strategy: str | None = None
    aggregate_window_minutes: int | None = None
    suppressed_until: str | None = None
    metadata: dict[str, Any] | None = None


class AlertCenterSeverityBreakdownItem(APIModel):
    key: str
    count: int


class AlertCenterSourceBreakdownItem(APIModel):
    key: str
    count: int


class AlertCenterSummary(APIModel):
    total: int
    open: int
    acknowledged: int
    resolved: int
    suppressed: int
    severity_breakdown: list[AlertCenterSeverityBreakdownItem] = Field(default_factory=list)
    source_breakdown: list[AlertCenterSourceBreakdownItem] = Field(default_factory=list)


class AlertCenterListResponse(APIModel):
    items: list[AlertCenterItem]
    total: int
    summary: AlertCenterSummary


class AlertCenterActionRequest(APIModel):
    note: str | None = None
    duration_minutes: int | None = None


class AlertCenterActionResponse(APIModel):
    ok: bool
    message: str
    alert: AlertCenterItem


class AlertSubscriptionItem(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    channel: AlertSubscriptionChannel
    target: str
    enabled: bool = True
    severity_scope: list[AlertSeverity] = Field(default_factory=list)
    created_at: str
    updated_at: str


class AlertSubscriptionListResponse(APIModel):
    items: list[AlertSubscriptionItem]
    total: int


class AlertSubscriptionCreateRequest(APIModel):
    channel: AlertSubscriptionChannel
    target: str
    enabled: bool = True
    severity_scope: list[AlertSeverity] = Field(default_factory=list)


class AlertSubscriptionUpdateRequest(APIModel):
    target: str | None = None
    enabled: bool | None = None
    severity_scope: list[AlertSeverity] | None = None


class AlertSubscriptionActionResponse(APIModel):
    ok: bool
    message: str
    subscription: AlertSubscriptionItem


class AlertEscalationPolicyItem(APIModel):
    severity: AlertSeverity
    ordered_channels: list[AlertSubscriptionChannel] = Field(default_factory=list)
    send_all: bool = True
    max_deliveries: int | None = None
    suppression_minutes: int = 60


class AlertEscalationPolicySet(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    policies: list[AlertEscalationPolicyItem] = Field(default_factory=list)
    created_at: str
    updated_at: str


class AlertEscalationPolicyRequest(APIModel):
    policies: list[AlertEscalationPolicyItem] = Field(default_factory=list)


class AlertEscalationPolicyResponse(APIModel):
    ok: bool
    message: str
    policy: AlertEscalationPolicySet


class AlertDeliveryPreviewItem(APIModel):
    subscription_id: str
    channel: AlertSubscriptionChannel
    target: str
    selected: bool
    reason: str


class AlertDeliveryPreviewResponse(APIModel):
    alert: AlertCenterItem
    matched_subscriptions: int
    selected_subscriptions: int
    policy: AlertEscalationPolicyItem | None = None
    deliveries: list[AlertDeliveryPreviewItem] = Field(default_factory=list)


class AlertManualSendRequest(APIModel):
    note: str | None = None


class AlertManualSendDelivery(APIModel):
    subscription_id: str
    channel: AlertSubscriptionChannel
    target: str
    status: Literal["sent", "failed"]
    detail: str | None = None


class AlertManualSendResponse(APIModel):
    ok: bool
    message: str
    alert: AlertCenterItem
    matched_subscriptions: int
    selected_subscriptions: int
    sent: int
    failed: int
    deliveries: list[AlertManualSendDelivery] = Field(default_factory=list)
