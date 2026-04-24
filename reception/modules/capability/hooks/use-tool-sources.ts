'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import { normalizeToolSourceDetailResponse, normalizeToolSourceListResponse } from '@/modules/capability/hooks/use-tools'
import type { ToolSource } from '@/shared/types'

export interface RegisterSkillPayload {
  id?: string
  name: string
  description?: string
  skillFamily?: string
  version?: string
  baseUrl: string
  invokePath?: string
  healthPath?: string
  method?: string
  protocol?: string
  provider?: string
  enabled?: boolean
  timeoutSeconds?: number
  tags?: string[]
  capabilities?: string[]
  sourceId?: string
  sourceName?: string
}

export interface RegisterMcpPayload {
  id?: string
  name: string
  description?: string
  baseUrl: string
  invokePath?: string
  method?: string
  provider?: string
  enabled?: boolean
  timeoutSeconds?: number
  requiresPermission?: boolean
  approvalRequired?: boolean
  tags?: string[]
  scopes?: string[]
  roles?: string[]
  sourceId?: string
  sourceName?: string
}

export interface ToolSourceRegistrationResponse {
  ok: boolean
  message: string
  sourceId: string
  toolId: string
  source: ToolSource | null
  tool: Record<string, unknown> | null
}

export interface ToolSourceDeleteResponse {
  ok: boolean
  message: string
  sourceId: string
  toolId: string
}

export function useToolSources() {
  return useQuery({
    queryKey: queryKeys.tools.sources,
    queryFn: async () => {
      const payload = await apiRequest<unknown>('/api/tool-sources')
      return normalizeToolSourceListResponse(payload)
    },
  })
}

export function useToolSourceDetail(sourceId: string | null) {
  return useQuery({
    queryKey: queryKeys.tools.sourceDetail(sourceId),
    enabled: Boolean(sourceId),
    queryFn: async () => {
      if (!sourceId) return null
      const payload = await apiRequest<unknown>(`/api/tool-sources/${encodeURIComponent(sourceId)}`)
      return normalizeToolSourceDetailResponse(payload)
    },
  })
}

function invalidateToolQueries(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['tools'] })
}

export function useRegisterToolSkill() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: RegisterSkillPayload) => {
      const response = await apiRequest<ToolSourceRegistrationResponse, RegisterSkillPayload>(
        '/api/tool-sources/register-skill',
        {
          method: 'POST',
          body: payload,
        },
      )

      return {
        ...response,
        source: response.source ? normalizeToolSourceDetailResponse(response.source) : null,
      }
    },
    onSuccess: () => {
      invalidateToolQueries(queryClient)
    },
  })
}

export function useRegisterToolMcp() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (payload: RegisterMcpPayload) => {
      const response = await apiRequest<ToolSourceRegistrationResponse, RegisterMcpPayload>(
        '/api/tool-sources/register-mcp',
        {
          method: 'POST',
          body: payload,
        },
      )

      return {
        ...response,
        source: response.source ? normalizeToolSourceDetailResponse(response.source) : null,
      }
    },
    onSuccess: () => {
      invalidateToolQueries(queryClient)
    },
  })
}

export function useUpdateToolSkill() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      toolId,
      payload,
    }: {
      toolId: string
      payload: RegisterSkillPayload
    }) => {
      const response = await apiRequest<ToolSourceRegistrationResponse, RegisterSkillPayload>(
        `/api/tool-sources/tools/${encodeURIComponent(toolId)}/skill`,
        {
          method: 'PUT',
          body: payload,
        },
      )

      return {
        ...response,
        source: response.source ? normalizeToolSourceDetailResponse(response.source) : null,
      }
    },
    onSuccess: () => {
      invalidateToolQueries(queryClient)
    },
  })
}

export function useUpdateToolMcp() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      toolId,
      payload,
    }: {
      toolId: string
      payload: RegisterMcpPayload
    }) => {
      const response = await apiRequest<ToolSourceRegistrationResponse, RegisterMcpPayload>(
        `/api/tool-sources/tools/${encodeURIComponent(toolId)}/mcp`,
        {
          method: 'PUT',
          body: payload,
        },
      )

      return {
        ...response,
        source: response.source ? normalizeToolSourceDetailResponse(response.source) : null,
      }
    },
    onSuccess: () => {
      invalidateToolQueries(queryClient)
    },
  })
}

export function useDeleteManagedTool() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (toolId: string) =>
      apiRequest<ToolSourceDeleteResponse>(`/api/tool-sources/tools/${encodeURIComponent(toolId)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      invalidateToolQueries(queryClient)
    },
  })
}
