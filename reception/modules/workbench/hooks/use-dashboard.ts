'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type { DashboardStatsResponse } from '@/shared/types'

export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboard.stats,
    queryFn: () => apiRequest<DashboardStatsResponse>('/api/dashboard/stats'),
  })
}
