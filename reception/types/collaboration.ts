import type { Workflow, WorkflowRunNodeError } from '@/types/workflow'
import type { BrainDispatchSummary, ManagerPacket, TaskRouteDecision } from '@/types/task'

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
  routeDecision?: TaskRouteDecision | null
  managerPacket?: ManagerPacket | null
  brainDispatchSummary?: BrainDispatchSummary | null
  executionPlan?: CollaborationExecutionPlan | null
  fallbackHistory?: CollaborationFallbackHistoryItem[]
  memoryInjectionSummary?: Record<string, unknown> | null
  contextPatchAudit?: Array<Record<string, unknown>>
  stateMachine?: Record<string, unknown> | null
}

export interface CollaborationExecutionPlanStep {
  id: string
  index: number
  branchId?: string | null
  intent?: string | null
  role?: string | null
  completionPolicy?: string | null
  dependsOn?: string[]
  executionAgentId?: string | null
  executionAgent?: string | null
  agentType?: string | null
  title?: string | null
}

export interface CollaborationExecutionPlanFallback {
  mode?: string | null
  target?: string | null
  onFailure?: string | null
  summary?: string | null
}

export interface CollaborationExecutionPlanRationale {
  intent?: string | null
  workflowMode?: string | null
  interactionMode?: string | null
  routingStrategy?: string | null
  routeReasonSummary?: string | null
  candidateCount: number
  skippedCount: number
}

export interface CollaborationExecutionPlanBranchResult {
  stepId?: string | null
  branchId?: string | null
  intent?: string | null
  agent?: string | null
  status?: string | null
  score: number
}

export interface CollaborationExecutionPlan {
  version: string
  planner?: string | null
  aggregator?: string | null
  planType: string
  coordinationMode: string
  stepCount: number
  plannedAgentCount?: number
  workflowId?: string | null
  workflowName?: string | null
  executionAgentId?: string | null
  executionAgent?: string | null
  currentOwner?: string | null
  summary?: string | null
  steps: CollaborationExecutionPlanStep[]
  fanOut?: Record<string, unknown> | null
  fanIn?: Record<string, unknown> | null
  winnerStrategy?: string | null
  quorum?: Record<string, unknown> | null
  mergeStrategy?: string | null
  cancelPolicy?: Record<string, unknown> | null
  fallback?: CollaborationExecutionPlanFallback | null
  routeRationale?: CollaborationExecutionPlanRationale | null
  selectedBranchId?: string | null
  selectedAgent?: string | null
  successfulAgents: number
  failedAgents: number
  cancelledAgents: number
  branchResults?: CollaborationExecutionPlanBranchResult[]
  metadata?: Record<string, unknown>
}

export interface CollaborationFallbackHistoryItem {
  id: string
  timestamp: string
  state: string
  failureStage: string
  reason: string
  message: string
  policyMode?: string | null
  policyTarget?: string | null
  resolvedAction: string
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
