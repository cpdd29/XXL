'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  AgentApiSettingsResponse,
  ChannelIntegrationSettingsResponse,
  GeneralSettingsResponse,
  UpdateAgentApiSettingsRequest,
  UpdateChannelIntegrationSettingsRequest,
  UpdateGeneralSettingsRequest,
} from '@/shared/types'

export function useGeneralSettings() {
  return useQuery({
    queryKey: queryKeys.settings.general,
    queryFn: () => apiRequest<GeneralSettingsResponse>('/api/settings/general'),
  })
}

export function useUpdateGeneralSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateGeneralSettingsRequest) =>
      apiRequest<GeneralSettingsResponse, UpdateGeneralSettingsRequest>('/api/settings/general', {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.general, response)
    },
  })
}

export function useAgentApiSettings() {
  return useQuery({
    queryKey: queryKeys.settings.agentApi,
    queryFn: () => apiRequest<AgentApiSettingsResponse>('/api/settings/agent-api'),
  })
}

export function useUpdateAgentApiSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateAgentApiSettingsRequest) =>
      apiRequest<AgentApiSettingsResponse, UpdateAgentApiSettingsRequest>('/api/settings/agent-api', {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.agentApi, response)
    },
  })
}

export function useChannelIntegrationSettings() {
  return useQuery({
    queryKey: queryKeys.settings.channelIntegration,
    queryFn: () =>
      apiRequest<ChannelIntegrationSettingsResponse>('/api/settings/channel-integration'),
  })
}

export function useUpdateChannelIntegrationSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateChannelIntegrationSettingsRequest) =>
      apiRequest<ChannelIntegrationSettingsResponse, UpdateChannelIntegrationSettingsRequest>(
        '/api/settings/channel-integration',
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.channelIntegration, response)
    },
  })
}
