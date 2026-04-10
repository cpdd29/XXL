'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type { DashboardStatsResponse } from '@/types'

export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboard.stats,
    queryFn: () => apiRequest<DashboardStatsResponse>('/api/dashboard/stats'),
  })
}
