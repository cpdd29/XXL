'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import type { ScheduledTask, ScheduledTaskListResponse, Workflow, WorkflowMonitorResponse } from '@/types'

export function useScheduledTasks() {
  return useQuery({
    queryKey: queryKeys.schedules.list,
    queryFn: async (): Promise<ScheduledTaskListResponse> => {
      const workflowPayload = await apiRequest<{ items: Workflow[]; total: number }>('/api/workflows')
      const workflows = workflowPayload.items ?? []
      const scheduledWorkflows = workflows.filter((workflow) => workflow.trigger?.type === 'schedule' && workflow.trigger?.cron)

      const monitorEntries = await Promise.all(
        scheduledWorkflows.map(async (workflow) => {
          try {
            const monitor = await apiRequest<WorkflowMonitorResponse>(
              `/api/workflows/${encodeURIComponent(workflow.id)}/monitor?limit=1`,
            )
            return { workflowId: workflow.id, monitor }
          } catch {
            return { workflowId: workflow.id, monitor: null }
          }
        }),
      )
      const monitorByWorkflow = new Map(monitorEntries.map((entry) => [entry.workflowId, entry.monitor]))

      const items: ScheduledTask[] = scheduledWorkflows.map((workflow) => {
        const monitor = monitorByWorkflow.get(workflow.id)
        const latestRun = monitor?.items?.[0]
        return {
          workflowId: workflow.id,
          workflowName: workflow.name,
          description: workflow.description,
          status: workflow.status,
          cron: workflow.trigger.cron ?? '',
          priority: workflow.trigger.priority ?? 100,
          channels: workflow.trigger.channels ?? [],
          preferredLanguage: workflow.trigger.preferredLanguage ?? null,
          nextAction: latestRun?.monitor?.nextAction ?? 'wait_for_schedule',
          dispatchState: latestRun?.monitor?.dispatchState ?? null,
          latestRunStatus: latestRun?.status ?? null,
          latestRunId: latestRun?.id ?? null,
          latestRunUpdatedAt: latestRun?.updatedAt ?? null,
          monitorState: latestRun?.monitor?.monitorState ?? null,
        }
      })

      return { items, total: items.length }
    },
    refetchInterval: 20_000,
  })
}
