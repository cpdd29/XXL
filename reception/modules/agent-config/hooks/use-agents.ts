'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  Agent,
  AgentActionResponse,
  AgentBindableTool,
  AgentConfigRequest,
  AgentDeleteResponse,
  AgentListResponse,
  AgentRuntimeStatus,
} from '@/shared/types'

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents.list,
    queryFn: () => apiRequest<AgentListResponse>('/api/agents'),
  })
}

export function useAgentMcpTools() {
  return useQuery({
    queryKey: ['agents', 'mcp-tools'],
    queryFn: async () => {
      const payload = await apiRequest<{
        items?: Array<{
          id?: string | null
          name?: string | null
          type?: string | null
          description?: string | null
          source?: string | null
          sourceId?: string | null
          source_id?: string | null
          enabled?: boolean | null
        }>
      }>('/api/tools')

      const items: AgentBindableTool[] = (payload.items ?? [])
        .filter((item) => item?.type === 'mcp')
        .map((item) => {
          const id = String(item.id ?? '').trim()
          const source =
            String(item.sourceId ?? item.source_id ?? item.source ?? '').trim()
          return {
            id,
            name: String(item.name ?? id).trim() || id,
            type: String(item.type ?? 'mcp').trim() || 'mcp',
            description: String(item.description ?? '').trim(),
            source,
            enabled: item.enabled !== false,
          }
        })
        .filter((item) => item.id)

      return {
        items,
        total: items.length,
      }
    },
  })
}

export function useAgentStatus(agentId: string) {
  return useQuery({
    queryKey: queryKeys.agents.status(agentId),
    queryFn: async () => {
      const agent = await apiRequest<Agent>(`/api/agents/${encodeURIComponent(agentId)}/status`)
      return {
        id: agent.id,
        name: agent.name,
        status: agent.status,
        runtimeStatus: agent.runtimeStatus,
        enabled: agent.enabled,
        lastActive: agent.lastActive,
        avgResponseTime: agent.avgResponseTime,
        tokensUsed: agent.tokensUsed,
        tokensLimit: agent.tokensLimit,
      } satisfies AgentRuntimeStatus
    },
    enabled: Boolean(agentId),
    refetchInterval: 15_000,
  })
}

export function useReloadAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (agentId: string) =>
      apiRequest<AgentActionResponse>(`/api/agents/${encodeURIComponent(agentId)}/reload`, {
        method: 'POST',
      }),
    onSuccess: (_, agentId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.status(agentId) })
    },
  })
}

export function useCreateAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: AgentConfigRequest) =>
      apiRequest<AgentActionResponse, AgentConfigRequest>('/api/agents', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
    },
  })
}

export function useDeleteAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (agentId: string) =>
      apiRequest<AgentDeleteResponse>(`/api/agents/${encodeURIComponent(agentId)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
    },
  })
}

export function useSetAgentEnabled() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ agentId, enabled }: { agentId: string; enabled: boolean }) =>
      apiRequest<AgentActionResponse>(`/api/agents/${encodeURIComponent(agentId)}/enabled`, {
        method: 'PUT',
        body: { enabled },
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.status(variables.agentId) })
    },
  })
}

export function useUpdateAgentConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ agentId, payload }: { agentId: string; payload: AgentConfigRequest }) =>
      apiRequest<AgentActionResponse, AgentConfigRequest>(
        `/api/agents/${encodeURIComponent(agentId)}/config`,
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.status(variables.agentId) })
    },
  })
}
