'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type {
  AuditLogsResponse,
  ExternalCapabilityActionResponse,
  ExternalCapabilityAuditQuery,
  ExternalCapabilityGovernanceOverviewResponse,
  ExternalCapabilityVersionListResponse,
  ExternalCapabilityVersionUpdateRequest,
} from '@/types'

function buildGovernancePath(auditLimit = 20) {
  return `/api/external-connections/governance?auditLimit=${encodeURIComponent(String(auditLimit))}`
}

function buildCapabilityAuditPath(params: ExternalCapabilityAuditQuery = {}) {
  const searchParams = new URLSearchParams()
  const capabilityType = params.capabilityType ?? null
  const resource =
    capabilityType === 'agent'
      ? 'external.agent.'
      : capabilityType === 'skill'
        ? 'external.skill.'
        : 'external'

  searchParams.set('resource', resource)
  searchParams.set('limit', String(params.limit ?? 50))

  if (params.status) {
    searchParams.set('status', params.status)
  }

  return `/api/dashboard/logs?${searchParams.toString()}`
}

function buildVersionListPath(capabilityType: 'agent' | 'skill', family: string) {
  const encodedFamily = encodeURIComponent(family)
  if (capabilityType === 'agent') {
    return `/api/external-connections/agents/families/${encodedFamily}/versions`
  }
  return `/api/external-connections/skills/families/${encodedFamily}/versions`
}

function invalidateGovernanceQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  options: {
    capabilityType: 'agent' | 'skill'
    family: string
  },
) {
  const { capabilityType, family } = options
  queryClient.invalidateQueries({ queryKey: ['external'] })
  if (capabilityType === 'agent') {
    queryClient.invalidateQueries({ queryKey: queryKeys.external.agentVersions(family) })
  } else {
    queryClient.invalidateQueries({ queryKey: queryKeys.external.skillVersions(family) })
  }
}

export function useExternalCapabilityGovernanceOverview(auditLimit = 20) {
  return useQuery({
    queryKey: queryKeys.external.governance(auditLimit),
    queryFn: () => apiRequest<ExternalCapabilityGovernanceOverviewResponse>(buildGovernancePath(auditLimit)),
  })
}

export function useExternalCapabilityAuditLogs(params: ExternalCapabilityAuditQuery = {}) {
  return useQuery({
    queryKey: queryKeys.external.audits(params),
    queryFn: () => apiRequest<AuditLogsResponse>(buildCapabilityAuditPath(params)),
    placeholderData: (previousData) => previousData,
  })
}

export function useExternalAgentVersions(family?: string | null) {
  return useQuery({
    queryKey: queryKeys.external.agentVersions(family),
    queryFn: () =>
      apiRequest<ExternalCapabilityVersionListResponse>(buildVersionListPath('agent', family ?? '')),
    enabled: Boolean(family),
  })
}

export function useExternalSkillVersions(family?: string | null) {
  return useQuery({
    queryKey: queryKeys.external.skillVersions(family),
    queryFn: () =>
      apiRequest<ExternalCapabilityVersionListResponse>(buildVersionListPath('skill', family ?? '')),
    enabled: Boolean(family),
  })
}

export function usePromoteExternalAgentVersion() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ agentId }: { family: string; agentId: string }) =>
      apiRequest<ExternalCapabilityActionResponse>(`/api/external-connections/agents/${encodeURIComponent(agentId)}/promote`, {
        method: 'POST',
      }),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'agent', family: variables.family })
    },
  })
}

export function usePromoteExternalSkillVersion() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ skillId }: { family: string; skillId: string }) =>
      apiRequest<ExternalCapabilityActionResponse>(`/api/external-connections/skills/${encodeURIComponent(skillId)}/promote`, {
        method: 'POST',
      }),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'skill', family: variables.family })
    },
  })
}

export function useSetExternalAgentFallback() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      agentId,
      payload,
    }: {
      family: string
      agentId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/agents/${encodeURIComponent(agentId)}/set-fallback`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'agent', family: variables.family })
    },
  })
}

export function useSetExternalSkillFallback() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      skillId,
      payload,
    }: {
      family: string
      skillId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/skills/${encodeURIComponent(skillId)}/set-fallback`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'skill', family: variables.family })
    },
  })
}

export function useSetExternalAgentDeprecated() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      agentId,
      payload,
    }: {
      family: string
      agentId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/agents/${encodeURIComponent(agentId)}/deprecate`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'agent', family: variables.family })
    },
  })
}

export function useSetExternalSkillDeprecated() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      skillId,
      payload,
    }: {
      family: string
      skillId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/skills/${encodeURIComponent(skillId)}/deprecate`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'skill', family: variables.family })
    },
  })
}

export function useSetExternalAgentRolloutPolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      agentId,
      payload,
    }: {
      family: string
      agentId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/agents/${encodeURIComponent(agentId)}/rollout-policy`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'agent', family: variables.family })
    },
  })
}

export function useSetExternalSkillRolloutPolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      skillId,
      payload,
    }: {
      family: string
      skillId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/skills/${encodeURIComponent(skillId)}/rollout-policy`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'skill', family: variables.family })
    },
  })
}

export function useSetExternalAgentRollbackPolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      agentId,
      payload,
    }: {
      family: string
      agentId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/agents/${encodeURIComponent(agentId)}/rollback`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'agent', family: variables.family })
    },
  })
}

export function useSetExternalSkillRollbackPolicy() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      skillId,
      payload,
    }: {
      family: string
      skillId: string
      payload: ExternalCapabilityVersionUpdateRequest
    }) =>
      apiRequest<ExternalCapabilityActionResponse, ExternalCapabilityVersionUpdateRequest>(
        `/api/external-connections/skills/${encodeURIComponent(skillId)}/rollback`,
        {
          method: 'POST',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      invalidateGovernanceQueries(queryClient, { capabilityType: 'skill', family: variables.family })
    },
  })
}
