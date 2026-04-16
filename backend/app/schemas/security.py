from __future__ import annotations

from typing import Any, Literal

from app.schemas.base import APIModel
from app.schemas.dashboard import AuditLog


class SecuritySummary(APIModel):
    today_events: int
    blocked_threats: int
    alert_notifications: int
    active_rules: int


class SecurityReportSummary(APIModel):
    total_events: int
    blocked_threats: int
    alert_notifications: int
    active_rules: int
    unique_users: int
    rewrite_events: int
    high_risk_events: int


class SecurityReportBreakdownItem(APIModel):
    key: str
    label: str
    count: int
    share: float


class SecurityReportIncident(AuditLog):
    layer: str | None = None
    verdict: str | None = None
    rule_label: str | None = None
    entity_refs: list["SecurityEntityRef"] = []


class SecurityRule(APIModel):
    id: str
    name: str
    description: str
    type: str
    enabled: bool
    hit_count: int
    last_triggered: str


class SecurityRulesResponse(APIModel):
    summary: SecuritySummary
    items: list[SecurityRule]
    total: int


class UpdateSecurityRuleRequest(APIModel):
    enabled: bool | None = None
    name: str | None = None
    description: str | None = None
    type: Literal["filter", "block", "alert"] | None = None


class SecurityRuleActionResponse(APIModel):
    ok: bool
    message: str
    rule: SecurityRule


class ActiveSecurityPenalty(APIModel):
    user_key: str
    level: str
    detail: str
    status_code: int
    until: str
    updated_at: str


class SecurityPenaltiesResponse(APIModel):
    items: list[ActiveSecurityPenalty]
    total: int


class SecurityPenaltyActionResponse(APIModel):
    ok: bool
    message: str
    user_key: str
    penalty: ActiveSecurityPenalty | None = None
    released_penalty: ActiveSecurityPenalty


class SecurityReportResponse(APIModel):
    generated_at: str
    window_hours: int
    summary: SecurityReportSummary
    status_breakdown: list[SecurityReportBreakdownItem]
    gateway_layer_breakdown: list[SecurityReportBreakdownItem]
    top_resources: list[SecurityReportBreakdownItem]
    top_actions: list[SecurityReportBreakdownItem]
    top_rules: list[SecurityReportBreakdownItem]
    recent_incidents: list[SecurityReportIncident]


class SecurityIncidentReview(APIModel):
    id: str
    timestamp: str
    incident_id: str
    action: Literal["reviewed", "false_positive", "note"]
    note: str
    reviewer: str
    source: str


class SecurityIncidentReviewsResponse(APIModel):
    items: list[SecurityIncidentReview]
    total: int


class CreateSecurityIncidentReviewRequest(APIModel):
    action: Literal["reviewed", "false_positive", "note"]
    note: str = ""


class SecurityIncidentReviewActionResponse(APIModel):
    ok: bool
    message: str
    review: SecurityIncidentReview


class SecurityIncidentReviewListItem(SecurityReportIncident):
    reviewed: bool
    review_status: Literal["pending", "reviewed", "false_positive"]
    last_reviewed_at: str | None = None
    last_reviewer: str | None = None


class SecurityIncidentReviewListResponse(APIModel):
    items: list[SecurityIncidentReviewListItem]
    total: int


class SecurityIncidentReviewActionRequest(APIModel):
    action: Literal["reviewed", "false_positive", "note", "reopen"]
    note: str = ""


class SecurityIncidentReviewActionResult(APIModel):
    ok: bool
    message: str
    incident_id: str
    review: SecurityIncidentReview | None = None


class SecurityEntityRef(APIModel):
    type: Literal["task", "run", "collaboration", "workflow", "user", "channel"]
    id: str
    label: str
    href: str


class SecurityRuleHitDetail(AuditLog):
    layer: str | None = None
    verdict: str | None = None
    rule_label: str | None = None
    entity_refs: list[SecurityEntityRef] = []


class SecurityRuleHitSummary(APIModel):
    total_hits: int
    warning_hits: int
    error_hits: int
    latest_hit_at: str | None = None


class SecurityRuleHitDetailsResponse(APIModel):
    rule: SecurityRule
    summary: SecurityRuleHitSummary
    items: list[SecurityRuleHitDetail]
    total: int


class CreateSecurityRuleRequest(APIModel):
    name: str
    description: str
    type: Literal["filter", "block", "alert"]
    enabled: bool = True


class SecurityRuleVersion(APIModel):
    id: str
    rule_id: str
    timestamp: str
    action: str
    operator: str
    snapshot: SecurityRule
    note: str = ""


class SecurityRuleVersionHistoryResponse(APIModel):
    items: list[SecurityRuleVersion]
    total: int


class RollbackSecurityRuleRequest(APIModel):
    version_id: str


class SecurityPenaltyHistoryItem(APIModel):
    id: str
    timestamp: str
    user_key: str
    action: str
    level: str
    detail: str
    status_code: int
    until: str | None = None
    operator: str
    note: str = ""
    source: str = "audit_log"


class SecurityPenaltyHistoryResponse(APIModel):
    items: list[SecurityPenaltyHistoryItem]
    total: int


class CreateSecurityPenaltyRequest(APIModel):
    user_key: str
    level: Literal["cooldown", "ban"]
    detail: str
    duration_seconds: int
    status_code: int = 429
    note: str = ""
    approval_id: str | None = None
    approval_reason: str | None = None
    approval_note: str | None = None


class ReleaseSecurityPenaltyRequest(APIModel):
    approval_id: str | None = None
    approval_reason: str | None = None
    approval_note: str | None = None


class SecurityRiskProfileItem(APIModel):
    key: str
    label: str
    event_count: int
    blocked_count: int
    warning_count: int
    review_pending: int
    false_positive_count: int
    latest_event_at: str | None = None
    risk_score: int
    entity_refs: list[SecurityEntityRef] = []


class SecurityRiskProfilesResponse(APIModel):
    items: list[SecurityRiskProfileItem]
    total: int


class SecurityTrendPoint(APIModel):
    bucket: str
    total_events: int
    blocked_events: int
    warning_events: int
    false_positive_events: int
    review_events: int


class SecurityTrendResponse(APIModel):
    points: list[SecurityTrendPoint]
    total: int


class SecurityAlertSubscription(APIModel):
    id: str
    channel: Literal["email", "webhook", "nats"]
    target: str
    enabled: bool
    severity_scope: list[str]
    created_at: str
    updated_at: str


class SecurityAlertSubscriptionsResponse(APIModel):
    items: list[SecurityAlertSubscription]
    total: int


class CreateSecurityAlertSubscriptionRequest(APIModel):
    channel: Literal["email", "webhook", "nats"]
    target: str
    enabled: bool = True
    severity_scope: list[str] = ["warning", "error"]


class UpdateSecurityAlertSubscriptionRequest(APIModel):
    target: str | None = None
    enabled: bool | None = None
    severity_scope: list[str] | None = None


class SecurityAlertSubscriptionActionResponse(APIModel):
    ok: bool
    message: str
    subscription: SecurityAlertSubscription


class SecurityReportExportResponse(APIModel):
    generated_at: str
    period: Literal["daily", "weekly"]
    content_type: Literal["markdown"]
    content: str
    summary: dict[str, Any]
