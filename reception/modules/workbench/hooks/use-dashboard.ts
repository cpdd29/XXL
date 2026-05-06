'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type { DashboardStatsResponse } from '@/shared/types'

interface UseDashboardQueryOptions {
  live?: boolean
  refetchIntervalMs?: number
}

const DEFAULT_DASHBOARD_REFETCH_INTERVAL_MS = 3_000

export function useDashboardStats(options?: UseDashboardQueryOptions) {
  const live = options?.live === true
  const refetchIntervalMs = options?.refetchIntervalMs ?? DEFAULT_DASHBOARD_REFETCH_INTERVAL_MS

  return useQuery({
    queryKey: queryKeys.dashboard.stats,
    queryFn: () => apiRequest<DashboardStatsResponse>('/api/dashboard/stats'),
    refetchInterval: live ? refetchIntervalMs : false,
    refetchIntervalInBackground: true,
  })
}
