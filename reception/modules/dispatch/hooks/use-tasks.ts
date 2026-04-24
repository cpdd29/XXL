'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type { Task, TaskActionResponse, TaskListResponse, TaskStepsResponse } from '@/shared/types'

interface UseTasksParams {
  status?: string
  search?: string
  priority?: string
  agent?: string
  channel?: string
}

export function useTasks(params?: UseTasksParams) {
  const searchParams = new URLSearchParams()
  if (params?.status && params.status !== 'all') {
    searchParams.set('status', params.status)
  }
  if (params?.search) {
    searchParams.set('search', params.search)
  }
  if (params?.priority && params.priority !== 'all') {
    searchParams.set('priority', params.priority)
  }
  if (params?.agent && params.agent !== 'all') {
    searchParams.set('agent', params.agent)
  }
  if (params?.channel && params.channel !== 'all') {
    searchParams.set('channel', params.channel)
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : ''

  return useQuery({
    queryKey: [
      ...queryKeys.tasks.list,
      params?.status ?? 'all',
      params?.search ?? '',
      params?.priority ?? 'all',
      params?.agent ?? 'all',
      params?.channel ?? 'all',
    ] as const,
    queryFn: () => apiRequest<TaskListResponse>(`/api/tasks${suffix}`),
  })
}

export function useTaskDetail(taskId: string) {
  return useQuery({
    queryKey: queryKeys.tasks.detail(taskId),
    queryFn: () => apiRequest<Task>(`/api/tasks/${encodeURIComponent(taskId)}`),
    enabled: Boolean(taskId),
  })
}

export function useTaskSteps(taskId: string) {
  return useQuery({
    queryKey: queryKeys.tasks.steps(taskId),
    queryFn: () => apiRequest<TaskStepsResponse>(`/api/tasks/${encodeURIComponent(taskId)}/steps`),
    enabled: Boolean(taskId),
  })
}

export function useCancelTask() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (taskId: string) =>
      apiRequest<TaskActionResponse>(`/api/tasks/${encodeURIComponent(taskId)}`, {
        method: 'DELETE',
      }),
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.steps(taskId) })
    },
  })
}

export function useRetryTask() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (taskId: string) =>
      apiRequest<TaskActionResponse>(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {
        method: 'POST',
      }),
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.steps(taskId) })
    },
  })
}
