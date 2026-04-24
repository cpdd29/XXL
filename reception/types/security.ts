import type { LogType } from '@/types/dashboard'

export type SecurityRuleType = 'filter' | 'block' | 'alert'

export interface SecuritySummary {
  todayEvents: number
  blockedThreats: number
  alertNotifications: number
  activeRules: number
}

export interface SecurityReportSummary {
  totalEvents: number
  blockedThreats: number
  alertNotifications: number
  activeRules: number
  uniqueUsers: number
  rewriteEvents: number
  highRiskEvents: number
}

export interface SecurityReportBreakdownItem {
  key: string
  label: string
  count: number
  share: number
}

export interface SecurityRule {
  id: string
  name: string
  description: string
  type: SecurityRuleType
  enabled: boolean
  hitCount: number
  lastTriggered: string
}

export interface SecurityEntityRef {
  type: 'task' | 'run' | 'workflow' | 'user' | 'channel'
  id: string
  label: string
  href: string
}

export interface UpdateSecurityRuleRequest {
  enabled?: boolean
  name?: string
  description?: string
  type?: SecurityRuleType
}

export interface SecurityRulesResponse {
  summary: SecuritySummary
  items: SecurityRule[]
  total: number
}

export interface SecurityRuleActionResponse {
  ok: boolean
  message: string
  rule: SecurityRule
}

export type SecurityPenaltyLevel = 'cooldown' | 'ban'

export interface SecurityPenalty {
  userKey: string
  level: SecurityPenaltyLevel | string
  detail: string
  statusCode: number
  until: string
  updatedAt?: string
}

export interface SecurityPenaltiesResponse {
  items: SecurityPenalty[]
  total: number
}

export interface SecurityPenaltyActionResponse {
  ok: boolean
  message: string
  userKey: string
  penalty?: SecurityPenalty
  releasedPenalty?: SecurityPenalty
}

export type SecurityIncidentReviewAction = 'reviewed' | 'false_positive' | 'note'

export interface SecurityIncidentReview {
  id: string
  timestamp: string
  incidentId: string
  action: SecurityIncidentReviewAction
  note?: string | null
  reviewer?: string | null
  source?: string | null
}

export interface SecurityIncidentReviewsResponse {
  items: SecurityIncidentReview[]
  total?: number
}

export interface CreateSecurityIncidentReviewRequest {
  action: SecurityIncidentReviewAction
  note?: string
}

export interface SecurityIncidentReviewActionResponse {
  ok: boolean
  message: string
  review?: SecurityIncidentReview
}

export interface SecurityPolicySettings {
  messageRateLimitPerMinute: number
  messageRateLimitCooldownSeconds: number
  messageRateLimitBanThreshold: number
  messageRateLimitBanSeconds: number
  securityIncidentWindowSeconds: number
  promptRuleBlockThreshold: number
  promptClassifierBlockThreshold: number
  promptInjectionEnabled: boolean
  contentRedactionEnabled: boolean
}

export interface SecurityPolicySettingsResponse {
  key: string
  updatedAt: string
  settings: SecurityPolicySettings
}

export interface UpdateSecurityPolicySettingsRequest extends SecurityPolicySettings {}

export interface SecurityReportResponse {
  generatedAt: string
  windowHours: number
  summary: SecurityReportSummary
  statusBreakdown: SecurityReportBreakdownItem[]
  gatewayLayerBreakdown: SecurityReportBreakdownItem[]
  topResources: SecurityReportBreakdownItem[]
  topActions: SecurityReportBreakdownItem[]
  topRules: SecurityReportBreakdownItem[]
  recentIncidents: SecurityReportIncident[]
}

export interface SecurityReportIncident extends AuditLog {
  layer?: string | null
  verdict?: string | null
  ruleLabel?: string | null
  entityRefs?: SecurityEntityRef[]
}

export interface SecurityRuleHitSummary {
  totalHits: number
  warningHits: number
  errorHits: number
  latestHitAt?: string | null
}

export interface SecurityRuleHitDetail extends SecurityReportIncident {
  entityRefs?: SecurityEntityRef[]
}

export interface SecurityRuleHitDetailsResponse {
  rule: SecurityRule
  summary: SecurityRuleHitSummary
  items: SecurityRuleHitDetail[]
  total: number
}

export interface CreateSecurityRuleRequest {
  name: string
  description: string
  type: SecurityRuleType
  enabled?: boolean
}

export interface SecurityRuleVersion {
  id: string
  ruleId: string
  timestamp: string
  action: string
  operator: string
  snapshot: SecurityRule
  note?: string
}

export interface SecurityRuleVersionHistoryResponse {
  items: SecurityRuleVersion[]
  total: number
}

export interface RollbackSecurityRuleRequest {
  versionId: string
}

export interface CreateSecurityPenaltyRequest {
  userKey: string
  level: SecurityPenaltyLevel
  detail: string
  durationSeconds: number
  statusCode?: number
  note?: string
}

export interface SecurityPenaltyHistoryItem {
  id: string
  timestamp: string
  userKey: string
  action: string
  level: string
  detail: string
  statusCode: number
  until?: string | null
  operator: string
  note?: string
  source: string
}

export interface SecurityPenaltyHistoryResponse {
  items: SecurityPenaltyHistoryItem[]
  total: number
}

export interface SecurityRiskProfileItem {
  key: string
  label: string
  eventCount: number
  blockedCount: number
  warningCount: number
  reviewPending: number
  falsePositiveCount: number
  latestEventAt?: string | null
  riskScore: number
  entityRefs?: SecurityEntityRef[]
}

export interface SecurityRiskProfilesResponse {
  items: SecurityRiskProfileItem[]
  total: number
}

export interface SecurityTrendPoint {
  bucket: string
  totalEvents: number
  blockedEvents: number
  warningEvents: number
  falsePositiveEvents: number
  reviewEvents: number
}

export interface SecurityTrendResponse {
  points: SecurityTrendPoint[]
  total: number
}

export interface SecurityAlertSubscription {
  id: string
  channel: 'email' | 'webhook' | 'nats'
  target: string
  enabled: boolean
  severityScope: string[]
  createdAt: string
  updatedAt: string
}

export interface SecurityAlertSubscriptionsResponse {
  items: SecurityAlertSubscription[]
  total: number
}

export interface CreateSecurityAlertSubscriptionRequest {
  channel: 'email' | 'webhook' | 'nats'
  target: string
  enabled?: boolean
  severityScope?: string[]
}

export interface UpdateSecurityAlertSubscriptionRequest {
  target?: string
  enabled?: boolean
  severityScope?: string[]
}

export interface SecurityAlertSubscriptionActionResponse {
  ok: boolean
  message: string
  subscription: SecurityAlertSubscription
}

export interface SecurityReportExportResponse {
  generatedAt: string
  period: 'daily' | 'weekly'
  contentType: 'markdown'
  content: string
  summary: Record<string, unknown>
}

export interface AuditLog {
  id: string
  timestamp: string
  action: string
  user: string
  resource: string
  status: Extract<LogType, 'success' | 'warning' | 'error'>
  ip: string
  details: string
  metadata?: Record<string, unknown> | null
}

export interface AuditLogsResponse {
  items: AuditLog[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}

export interface AuditLogsQuery {
  search?: string
  status?: AuditLog['status']
  layer?: string
  user?: string
  resource?: string
  limit?: number
  offset?: number
}

export type AlertCenterSeverity = 'info' | 'warning' | 'critical'
export type AlertCenterStatus = 'open' | 'acknowledged' | 'resolved' | 'suppressed'

export interface SecurityAlertCenterItem {
  id: string
  sourceType: string
  sourceId: string
  source: string
  severity: AlertCenterSeverity
  status: AlertCenterStatus
  category: string
  title: string
  message: string
  occurredAt: string
  updatedAt: string
  resource?: string | null
  userKey?: string | null
  traceId?: string | null
  workflowRunId?: string | null
  href?: string | null
  metadata?: Record<string, unknown> | null
}

export interface SecurityAlertCenterQuery {
  search?: string
  status?: AlertCenterStatus | 'all'
  severity?: AlertCenterSeverity | 'all'
  source?: string
  limit?: number
  offset?: number
}

export interface SecurityAlertCenterSummaryBreakdownItem {
  key: string
  count: number
}

export interface SecurityAlertCenterSummary {
  total: number
  open: number
  acknowledged: number
  resolved: number
  suppressed: number
  severityBreakdown: SecurityAlertCenterSummaryBreakdownItem[]
  sourceBreakdown: SecurityAlertCenterSummaryBreakdownItem[]
}

export interface SecurityAlertCenterResponse {
  items: SecurityAlertCenterItem[]
  total: number
  summary: SecurityAlertCenterSummary
}

export interface AlertCenterActionRequest {
  note?: string
  durationMinutes?: number
}

export interface AlertCenterActionResponse {
  ok: boolean
  message: string
  alert: SecurityAlertCenterItem
}
