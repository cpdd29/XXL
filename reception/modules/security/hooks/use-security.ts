'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAuthenticatedHeaders } from '@/platform/api'
import { apiRequest } from '@/platform/api/client'
import { API_BASE_URL } from '@/platform/api/config'
import { ApiError } from '@/platform/api/errors'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  Agent,
  AuditLogsQuery,
  AuditLogsResponse,
  CreateSecurityAlertSubscriptionRequest,
  AlertCenterActionRequest,
  AlertCenterActionResponse,
  CreateSecurityIncidentReviewRequest,
  CreateSecurityPenaltyRequest,
  CreateSecurityRuleRequest,
  RollbackSecurityRuleRequest,
  SecurityAlertSubscriptionActionResponse,
  SecurityAlertSubscriptionsResponse,
  SecurityAlertCenterQuery,
  SecurityAlertCenterResponse,
  SecurityIncidentReviewActionResponse,
  SecurityIncidentReviewsResponse,
  SecurityPenaltyActionResponse,
  SecurityPenaltyHistoryResponse,
  SecurityPenaltiesResponse,
  SecurityPolicySettingsResponse,
  SecurityReportExportResponse,
  SecurityReportResponse,
  SecurityRiskProfilesResponse,
  SecurityRuleActionResponse,
  SecurityRuleHitDetailsResponse,
  SecurityRuleVersionHistoryResponse,
  SecurityRulesResponse,
  SecurityTrendResponse,
  UpdateSecurityAlertSubscriptionRequest,
  UpdateSecurityPolicySettingsRequest,
  UpdateSecurityRuleRequest,
} from '@/shared/types'

function buildAuditLogsPath(params: AuditLogsQuery = {}) {
  const searchParams = new URLSearchParams()

  if (params.search) searchParams.set('search', params.search)
  if (params.status) searchParams.set('status', params.status)
  if (params.layer) searchParams.set('layer', params.layer)
  if (params.user) searchParams.set('user', params.user)
  if (params.resource) searchParams.set('resource', params.resource)
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit))
  if (params.offset !== undefined) searchParams.set('offset', String(params.offset))

  const queryString = searchParams.toString()
  return queryString ? `/api/dashboard/logs?${queryString}` : '/api/dashboard/logs'
}

function buildAuditLogsExportPath(params: AuditLogsQuery = {}) {
  const searchParams = new URLSearchParams()

  if (params.search) searchParams.set('search', params.search)
  if (params.status) searchParams.set('status', params.status)
  if (params.layer) searchParams.set('layer', params.layer)
  if (params.user) searchParams.set('user', params.user)
  if (params.resource) searchParams.set('resource', params.resource)

  const queryString = searchParams.toString()
  return queryString ? `/api/dashboard/logs/export?${queryString}` : '/api/dashboard/logs/export'
}

function resolveDownloadFilename(contentDisposition: string | null) {
  if (!contentDisposition) return 'workbot-audit-logs.csv'

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return filenameMatch?.[1] || 'workbot-audit-logs.csv'
}

export async function downloadAuditLogs(params: AuditLogsQuery = {}) {
  const headers = await getAuthenticatedHeaders({ Accept: 'text/csv' })
  const response = await fetch(`${API_BASE_URL}${buildAuditLogsExportPath(params)}`, {
    method: 'GET',
    headers,
    cache: 'no-store',
  })

  if (!response.ok) {
    const message = (await response.text()) || `Request failed with status ${response.status}`
    throw new ApiError(message, response.status)
  }

  return {
    blob: await response.blob(),
    filename: resolveDownloadFilename(response.headers.get('Content-Disposition')),
  }
}

export function useAuditLogs(params: AuditLogsQuery = {}) {
  return useQuery({
    queryKey: queryKeys.security.logs(params),
    queryFn: () => apiRequest<AuditLogsResponse>(buildAuditLogsPath(params)),
    placeholderData: (previousData) => previousData,
  })
}

function buildAlertCenterPath(params: SecurityAlertCenterQuery = {}) {
  const searchParams = new URLSearchParams()

  if (params.search) searchParams.set('search', params.search)
  if (params.status && params.status !== 'all') searchParams.set('status', params.status)
  if (params.severity && params.severity !== 'all') searchParams.set('severity', params.severity)
  if (params.source && params.source !== 'all') searchParams.set('source', params.source)
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit))
  if (params.offset !== undefined) searchParams.set('offset', String(params.offset))

  const queryString = searchParams.toString()
  return queryString ? `/api/alerts?${queryString}` : '/api/alerts'
}

export function useSecurityAlertCenter(params: SecurityAlertCenterQuery = {}) {
  return useQuery({
    queryKey: queryKeys.security.alerts(params),
    queryFn: () => apiRequest<SecurityAlertCenterResponse>(buildAlertCenterPath(params)),
    placeholderData: (previousData) => previousData,
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ alertId, payload }: { alertId: string; payload?: AlertCenterActionRequest }) =>
      apiRequest<AlertCenterActionResponse, AlertCenterActionRequest>(
        `/api/alerts/${encodeURIComponent(alertId)}/ack`,
        {
          method: 'POST',
          body: payload ?? {},
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'alerts'] })
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.stats })
    },
  })
}

export function useResolveAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ alertId, payload }: { alertId: string; payload?: AlertCenterActionRequest }) =>
      apiRequest<AlertCenterActionResponse, AlertCenterActionRequest>(
        `/api/alerts/${encodeURIComponent(alertId)}/resolve`,
        {
          method: 'POST',
          body: payload ?? {},
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'alerts'] })
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.stats })
    },
  })
}

export function useSuppressAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ alertId, payload }: { alertId: string; payload?: AlertCenterActionRequest }) =>
      apiRequest<AlertCenterActionResponse, AlertCenterActionRequest>(
        `/api/alerts/${encodeURIComponent(alertId)}/suppress`,
        {
          method: 'POST',
          body: payload ?? { durationMinutes: 60 },
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'alerts'] })
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.stats })
    },
  })
}

export function useSecurityRules() {
  return useQuery({
    queryKey: queryKeys.security.rules,
    queryFn: () => apiRequest<SecurityRulesResponse>('/api/security/rules'),
  })
}

export function useSecurityGuardian() {
  return useQuery({
    queryKey: queryKeys.security.guardian,
    queryFn: () => apiRequest<Agent>('/api/security/guardian'),
  })
}

export function useSecurityReport(windowHours = 24) {
  return useQuery({
    queryKey: queryKeys.security.report(windowHours),
    queryFn: () =>
      apiRequest<SecurityReportResponse>(`/api/security/report?windowHours=${encodeURIComponent(String(windowHours))}`),
  })
}

export function useSecurityPolicy() {
  return useQuery({
    queryKey: queryKeys.security.policy,
    queryFn: () => apiRequest<SecurityPolicySettingsResponse>('/api/settings/security-policy'),
  })
}

export function useSecurityPenalties() {
  return useQuery({
    queryKey: queryKeys.security.penalties,
    queryFn: () => apiRequest<SecurityPenaltiesResponse>('/api/security/penalties'),
  })
}

const securityIncidentReviewsQueryKey = ['security', 'incident-reviews'] as const
const securityPenaltyHistoryQueryKey = ['security', 'penalty-history'] as const
const securityUserProfilesQueryKey = ['security', 'profiles', 'users'] as const
const securityChannelProfilesQueryKey = ['security', 'profiles', 'channels'] as const
const securityAlertSubscriptionsQueryKey = ['security', 'subscriptions'] as const

export function useSecurityIncidentReviews() {
  return useQuery({
    queryKey: securityIncidentReviewsQueryKey,
    queryFn: () => apiRequest<SecurityIncidentReviewsResponse>('/api/security/incidents/reviews'),
  })
}

export function useSecurityPenaltyHistory(userKey?: string) {
  const suffix = userKey ? `?user_key=${encodeURIComponent(userKey)}` : ''
  return useQuery({
    queryKey: [...securityPenaltyHistoryQueryKey, userKey ?? 'all'],
    queryFn: () => apiRequest<SecurityPenaltyHistoryResponse>(`/api/security/penalties/history${suffix}`),
  })
}

export function useCreateSecurityPenalty() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateSecurityPenaltyRequest) =>
      apiRequest<SecurityPenaltyActionResponse, CreateSecurityPenaltyRequest>('/api/security/penalties/manual', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.penalties })
      queryClient.invalidateQueries({ queryKey: securityPenaltyHistoryQueryKey })
      queryClient.invalidateQueries({ queryKey: ['security', 'logs'] })
      queryClient.invalidateQueries({ queryKey: ['security', 'report'] })
    },
  })
}

export function useSubmitSecurityIncidentReview() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      incidentId,
      payload,
    }: {
      incidentId: string
      payload: CreateSecurityIncidentReviewRequest
    }) =>
      apiRequest<SecurityIncidentReviewActionResponse, CreateSecurityIncidentReviewRequest>(
        `/api/security/incidents/${encodeURIComponent(incidentId)}/review`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: securityIncidentReviewsQueryKey })
      queryClient.invalidateQueries({ queryKey: ['security', 'report'] })
    },
  })
}

export function useUpdateSecurityRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      ruleId,
      payload,
    }: {
      ruleId: string
      payload: UpdateSecurityRuleRequest
    }) =>
      apiRequest<SecurityRuleActionResponse>(`/api/security/rules/${encodeURIComponent(ruleId)}`, {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules })
    },
  })
}

export function useCreateSecurityRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateSecurityRuleRequest) =>
      apiRequest<SecurityRuleActionResponse, CreateSecurityRuleRequest>('/api/security/rules', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules })
    },
  })
}

export function useSecurityRuleHitDetails(ruleId?: string) {
  return useQuery({
    queryKey: ['security', 'rule-hits', ruleId ?? null],
    queryFn: () => apiRequest<SecurityRuleHitDetailsResponse>(`/api/security/rules/${encodeURIComponent(ruleId ?? '')}/hits`),
    enabled: Boolean(ruleId),
  })
}

export function useSecurityRuleVersions(ruleId?: string) {
  return useQuery({
    queryKey: ['security', 'rule-versions', ruleId ?? null],
    queryFn: () => apiRequest<SecurityRuleVersionHistoryResponse>(`/api/security/rules/${encodeURIComponent(ruleId ?? '')}/versions`),
    enabled: Boolean(ruleId),
  })
}

export function useRollbackSecurityRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ ruleId, payload }: { ruleId: string; payload: RollbackSecurityRuleRequest }) =>
      apiRequest<SecurityRuleActionResponse, RollbackSecurityRuleRequest>(
        `/api/security/rules/${encodeURIComponent(ruleId)}/rollback`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules })
      queryClient.invalidateQueries({ queryKey: ['security', 'rule-versions', variables.ruleId] })
      queryClient.invalidateQueries({ queryKey: ['security', 'rule-hits', variables.ruleId] })
    },
  })
}

export function useUpdateSecurityPolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateSecurityPolicySettingsRequest) =>
      apiRequest<SecurityPolicySettingsResponse, UpdateSecurityPolicySettingsRequest>(
        '/api/settings/security-policy',
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.security.policy, response)
    },
  })
}

export function useReleaseSecurityPenalty() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ userKey }: { userKey: string }) =>
      apiRequest<SecurityPenaltyActionResponse>(`/api/security/penalties/${encodeURIComponent(userKey)}/release`, {
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.penalties })
      queryClient.invalidateQueries({ queryKey: ['security', 'report'] })
      queryClient.invalidateQueries({ queryKey: ['security', 'logs'] })
    },
  })
}

export function useSecurityUserProfiles() {
  return useQuery({
    queryKey: securityUserProfilesQueryKey,
    queryFn: () => apiRequest<SecurityRiskProfilesResponse>('/api/security/profiles/users'),
  })
}

export function useSecurityChannelProfiles() {
  return useQuery({
    queryKey: securityChannelProfilesQueryKey,
    queryFn: () => apiRequest<SecurityRiskProfilesResponse>('/api/security/profiles/channels'),
  })
}

export function useSecurityTrends(days = 7) {
  return useQuery({
    queryKey: ['security', 'trends', days],
    queryFn: () => apiRequest<SecurityTrendResponse>(`/api/security/trends?days=${encodeURIComponent(String(days))}`),
  })
}

export function useSecurityAlertSubscriptions() {
  return useQuery({
    queryKey: securityAlertSubscriptionsQueryKey,
    queryFn: () => apiRequest<SecurityAlertSubscriptionsResponse>('/api/security/subscriptions'),
  })
}

export function useCreateSecurityAlertSubscription() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateSecurityAlertSubscriptionRequest) =>
      apiRequest<SecurityAlertSubscriptionActionResponse, CreateSecurityAlertSubscriptionRequest>(
        '/api/security/subscriptions',
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: securityAlertSubscriptionsQueryKey })
    },
  })
}

export function useUpdateSecurityAlertSubscription() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      subscriptionId,
      payload,
    }: {
      subscriptionId: string
      payload: UpdateSecurityAlertSubscriptionRequest
    }) =>
      apiRequest<SecurityAlertSubscriptionActionResponse, UpdateSecurityAlertSubscriptionRequest>(
        `/api/security/subscriptions/${encodeURIComponent(subscriptionId)}`,
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: securityAlertSubscriptionsQueryKey })
    },
  })
}

export function useSecurityExportReport(period: 'daily' | 'weekly' = 'daily') {
  return useQuery({
    queryKey: ['security', 'export-report', period],
    queryFn: () =>
      apiRequest<SecurityReportExportResponse>(`/api/security/exports/report?period=${encodeURIComponent(period)}`),
  })
}
