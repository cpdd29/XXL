'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAuthenticatedHeaders } from '@/lib/api'
import { apiRequest } from '@/lib/api/client'
import { API_BASE_URL } from '@/lib/api/config'
import { ApiError } from '@/lib/api/errors'
import { queryKeys } from '@/lib/api/query-keys'
import type {
  AuditLogsQuery,
  AuditLogsResponse,
  SecurityPenaltyActionResponse,
  SecurityPenaltiesResponse,
  SecurityPolicySettingsResponse,
  SecurityReportResponse,
  SecurityRuleActionResponse,
  SecurityRulesResponse,
  UpdateSecurityPolicySettingsRequest,
  UpdateSecurityRuleRequest,
} from '@/types'

function buildAuditLogsPath(params: AuditLogsQuery = {}) {
  const searchParams = new URLSearchParams()

  if (params.search) searchParams.set('search', params.search)
  if (params.status) searchParams.set('status', params.status)
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

export function useSecurityRules() {
  return useQuery({
    queryKey: queryKeys.security.rules,
    queryFn: () => apiRequest<SecurityRulesResponse>('/api/security/rules'),
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
