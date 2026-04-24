'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  BrainSkillActionResponse,
  BrainSkillDeleteResponse,
  BrainSkillListResponse,
  BrainSkillUploadRequest,
} from '@/shared/types'

function invalidateBrainSkillQueries(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: queryKeys.agents.brainSkills })
  queryClient.invalidateQueries({ queryKey: queryKeys.agents.list })
}

export function useBrainSkills() {
  return useQuery({
    queryKey: queryKeys.agents.brainSkills,
    queryFn: () => apiRequest<BrainSkillListResponse>('/api/agents/brain-skills'),
  })
}

export function useUploadBrainSkill() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: BrainSkillUploadRequest) =>
      apiRequest<BrainSkillActionResponse, BrainSkillUploadRequest>('/api/agents/brain-skills', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      invalidateBrainSkillQueries(queryClient)
    },
  })
}

export const useCreateBrainSkill = useUploadBrainSkill

export function useDeleteBrainSkill() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (skillId: string) =>
      apiRequest<BrainSkillDeleteResponse>(`/api/agents/brain-skills/${encodeURIComponent(skillId)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      invalidateBrainSkillQueries(queryClient)
    },
  })
}
