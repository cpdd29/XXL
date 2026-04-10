import type { Workflow, WorkflowRunNodeError } from '@/types/workflow'

export type CollaborationNodeStatus =
  | 'idle'
  | 'waiting'
  | 'running'
  | 'completed'
  | 'error'

export interface CollaborationTaskOption {
  id: string
  title: string
  status: string
  priority: string
  agent: string
}

export interface CollaborationSession {
  taskId: string
  taskTitle: string
  taskStatus: string
  taskPriority: string
  workflowId: string
  workflowName: string
  startedAt: string
  completedAt?: string
  totalTokens: number
  progressPercent: number
  currentStage: string
  failureStage?: string
  failureMessage?: string
  dispatchState?: string
  deliveryStatus?: string
  deliveryMessage?: string
  statusReason?: string
  activeAgentCount: number
  completedSteps: number
  totalSteps: number
  workflowRunId?: string
}

export interface CollaborationNode {
  id: string
  type: string
  label: string
  status: CollaborationNodeStatus
  agentType?: string
  tokens: number
  message?: string
  latestError?: string | null
  latestErrorAt?: string | null
  errorCount: number
  errorHistory: WorkflowRunNodeError[]
}

export interface CollaborationLog {
  id: string
  timestamp: string
  type: 'info' | 'success' | 'warning' | 'error'
  agent: string
  message: string
}

export interface CollaborationOverviewResponse {
  session: CollaborationSession
  tasks: CollaborationTaskOption[]
  workflow: Workflow
  nodes: CollaborationNode[]
  activeEdges: string[]
  logs: CollaborationLog[]
}
