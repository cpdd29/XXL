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

interface UseTaskQueryOptions {
  live?: boolean
  refetchIntervalMs?: number
}

interface UseTaskListQueryOptions {
  live?: boolean
  refetchIntervalMs?: number
}

const DEFAULT_TASK_DETAIL_REFETCH_INTERVAL_MS = 3_000
const DEFAULT_TASK_LIST_REFETCH_INTERVAL_MS = 3_000

function isActiveTaskStatus(status?: string | null) {
  const normalized = String(status ?? '').trim().toLowerCase()
  return normalized === 'pending' || normalized === 'running'
}

export function useTasks(params?: UseTasksParams, options?: UseTaskListQueryOptions) {
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
  const live = options?.live === true
  const refetchIntervalMs = options?.refetchIntervalMs ?? DEFAULT_TASK_LIST_REFETCH_INTERVAL_MS

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
    refetchInterval: live ? refetchIntervalMs : false,
    refetchIntervalInBackground: true,
  })
}

export function useTaskDetail(taskId: string, options?: UseTaskQueryOptions) {
  const live = options?.live !== false
  const refetchIntervalMs = options?.refetchIntervalMs ?? DEFAULT_TASK_DETAIL_REFETCH_INTERVAL_MS

  return useQuery({
    queryKey: queryKeys.tasks.detail(taskId),
    queryFn: () => apiRequest<Task>(`/api/tasks/${encodeURIComponent(taskId)}`),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      if (!live) {
        return false
      }
      const task = query.state.data as Task | undefined
      return isActiveTaskStatus(task?.status) ? refetchIntervalMs : false
    },
    refetchIntervalInBackground: true,
  })
}

export function useTaskSteps(taskId: string, options?: UseTaskQueryOptions & { taskStatus?: string | null }) {
  const live = options?.live !== false
  const refetchIntervalMs = options?.refetchIntervalMs ?? DEFAULT_TASK_DETAIL_REFETCH_INTERVAL_MS

  return useQuery({
    queryKey: queryKeys.tasks.steps(taskId),
    queryFn: () => apiRequest<TaskStepsResponse>(`/api/tasks/${encodeURIComponent(taskId)}/steps`),
    enabled: Boolean(taskId),
    refetchInterval: live && isActiveTaskStatus(options?.taskStatus) ? refetchIntervalMs : false,
    refetchIntervalInBackground: true,
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
