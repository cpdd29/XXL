'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type {
  Agent,
  AgentActionResponse,
  AgentConfigRequest,
  AgentListResponse,
  AgentRuntimeStatus,
} from '@/types'

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents.list,
    queryFn: () => apiRequest<AgentListResponse>('/api/agents'),
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
