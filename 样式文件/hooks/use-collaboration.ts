'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { apiRequest } from '@/lib/api/client'
import { queryKeys } from '@/lib/api/query-keys'
import { useWorkflowRealtime } from '@/hooks/use-workflow-realtime'
import type {
  CollaborationNode,
  CollaborationOverviewResponse,
  CollaborationTaskOption,
  WorkflowRun,
} from '@/types'

export type CollaborationRealtimeStatus = 'idle' | 'connecting' | 'connected' | 'disconnected'

function mergeTaskOptions(
  tasks: CollaborationTaskOption[],
  runs: WorkflowRun[],
  selectedRun?: WorkflowRun | null,
) {
  const candidates = selectedRun ? [selectedRun, ...runs] : runs
  const statusByTaskId = new Map(
    candidates
      .filter((run) => run.taskId)
      .map((run) => [run.taskId as string, run.status] as const),
  )

  return tasks.map((task) =>
    statusByTaskId.has(task.id)
      ? {
          ...task,
          status: statusByTaskId.get(task.id) ?? task.status,
        }
      : task,
  )
}

function progressFromNodes(nodes: CollaborationNode[]) {
  const weights = {
    completed: 1,
    running: 0.6,
    waiting: 0.3,
    error: 0.6,
    idle: 0,
  } as const

  const total = nodes.reduce((sum, node) => sum + weights[node.status], 0)
  return Math.round((total / Math.max(nodes.length, 1)) * 100)
}

function mergeOverviewWithRun(
  base: CollaborationOverviewResponse | undefined,
  runs: WorkflowRun[],
  selectedTaskId?: string,
  selectedRun?: WorkflowRun | null,
) {
  if (!base) return undefined

  const tasks = mergeTaskOptions(base.tasks, runs, selectedRun)
  const currentTaskId = selectedTaskId ?? base.session.taskId
  const liveRun = selectedRun ?? runs.find((run) => run.taskId === currentTaskId)

  if (!liveRun) {
    return {
      ...base,
      tasks,
    }
  }

  const nodes = liveRun.nodes.map(
    (node): CollaborationNode => ({
      id: node.id,
      type: node.type,
      label: node.label,
      status: node.status,
      tokens: node.tokens,
      message: node.message ?? undefined,
      latestError: node.latestError ?? undefined,
      latestErrorAt: node.latestErrorAt ?? undefined,
      errorCount: node.errorCount ?? 0,
      errorHistory: node.errorHistory ?? [],
    }),
  )
  const liveTokenTotal = nodes.reduce((sum, node) => sum + node.tokens, 0)

  return {
    ...base,
    tasks,
    session: {
      ...base.session,
      taskId: liveRun.taskId ?? base.session.taskId,
      taskStatus: liveRun.status,
      workflowId: liveRun.workflowId,
      workflowName: liveRun.workflowName,
      startedAt: liveRun.startedAt,
      completedAt: liveRun.completedAt ?? undefined,
      totalTokens: Math.max(base.session.totalTokens, liveTokenTotal),
      progressPercent: progressFromNodes(nodes),
      currentStage: liveRun.currentStage,
      activeAgentCount: nodes.filter(
        (node) => node.type === 'agent' && ['running', 'waiting'].includes(node.status),
      ).length,
      completedSteps: nodes.filter((node) => node.status === 'completed').length,
      totalSteps: nodes.length,
    },
    nodes,
    activeEdges: liveRun.activeEdges,
    logs: liveRun.logs,
  }
}

export function useCollaborationOverview(taskId?: string) {
  const suffix = taskId ? `?taskId=${encodeURIComponent(taskId)}` : ''

  const query = useQuery({
    queryKey: queryKeys.collaboration.overview(taskId),
    queryFn: () =>
      apiRequest<CollaborationOverviewResponse>(`/api/collaboration/overview${suffix}`),
    refetchInterval: 15_000,
  })

  const workflowId = query.data?.session.workflowId ?? query.data?.workflow.id
  const realtime = useWorkflowRealtime({
    workflowId,
    taskId: taskId ?? query.data?.session.taskId,
  })

  const data = useMemo(
    () => mergeOverviewWithRun(query.data, realtime.runs, taskId, realtime.run),
    [query.data, realtime.run, realtime.runs, taskId],
  )

  return {
    ...query,
    data,
    realtimeStatus: realtime.status as CollaborationRealtimeStatus,
    isRealtimeActive: realtime.isConnected,
  }
}
