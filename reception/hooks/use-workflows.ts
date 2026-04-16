'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type {
  CreateWorkflowRequest,
  UpdateWorkflowRequest,
  WorkflowActionResponse,
  WorkflowListResponse,
  WorkflowMonitorResponse,
  WorkflowRun,
  WorkflowRunListResponse,
} from '@/types'

export function useWorkflows() {
  return useQuery({
    queryKey: queryKeys.workflows.list,
    queryFn: () => apiRequest<WorkflowListResponse>('/api/workflows'),
  })
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateWorkflowRequest) =>
      apiRequest<WorkflowActionResponse>('/api/workflows', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ workflowId, payload }: { workflowId: string; payload: UpdateWorkflowRequest }) =>
      apiRequest<WorkflowActionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useRunWorkflow() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (workflowId: string) =>
      apiRequest<WorkflowActionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/run`, {
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['collaboration'] })
    },
  })
}

export function useWorkflowRuns(workflowId?: string) {
  return useQuery({
    queryKey: workflowId ? queryKeys.workflows.runs(workflowId) : ['workflows', null, 'runs'],
    queryFn: () =>
      apiRequest<WorkflowRunListResponse>(`/api/workflows/${encodeURIComponent(workflowId ?? '')}/runs`),
    enabled: Boolean(workflowId),
    refetchInterval: 10_000,
  })
}

export function useWorkflowMonitor(workflowId?: string) {
  return useQuery({
    queryKey: workflowId ? queryKeys.workflows.monitor(workflowId) : ['workflows', null, 'monitor'],
    queryFn: () =>
      apiRequest<WorkflowMonitorResponse>(`/api/workflows/${encodeURIComponent(workflowId ?? '')}/monitor`),
    enabled: Boolean(workflowId),
    refetchInterval: 10_000,
  })
}

export function useTickWorkflowRun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (runId: string) =>
      apiRequest<WorkflowRun>(`/api/workflows/runs/${encodeURIComponent(runId)}/tick`, {
        method: 'POST',
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['collaboration'] })
      queryClient.setQueryData(queryKeys.workflows.run(run.id), run)
    },
  })
}
