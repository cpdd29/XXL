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

export interface UpdateSecurityRuleRequest {
  enabled?: boolean
  name?: string
  description?: string
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
  topResources: SecurityReportBreakdownItem[]
  topActions: SecurityReportBreakdownItem[]
  topRules: SecurityReportBreakdownItem[]
  recentIncidents: AuditLog[]
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
  user?: string
  resource?: string
  limit?: number
  offset?: number
}
