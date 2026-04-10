'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type { Agent, AgentActionResponse, AgentListResponse, AgentRuntimeStatus } from '@/types'

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
    mutationFn: async (agentId: string) => {
      const payload = await apiRequest<AgentActionResponse>(`/api/agents/${encodeURIComponent(agentId)}/reload`, {
        method: 'POST',
      })
      return {
        message: payload.message,
        agentId: payload.agent.id,
        status: payload.agent.status,
      }
    },
    onSuccess: (_, agentId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.status(agentId) })
    },
  })
}
