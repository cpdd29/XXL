'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import { normalizeToolSourceDetailResponse, normalizeToolSourceListResponse } from '@/hooks/use-tools'

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
