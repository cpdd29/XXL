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
    enabled: bool


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
    released_penalty: ActiveSecurityPenalty


class SecurityReportResponse(APIModel):
    generated_at: str
    window_hours: int
    summary: SecurityReportSummary
    status_breakdown: list[SecurityReportBreakdownItem]
    top_resources: list[SecurityReportBreakdownItem]
    top_actions: list[SecurityReportBreakdownItem]
    top_rules: list[SecurityReportBreakdownItem]
    recent_incidents: list[AuditLog]
