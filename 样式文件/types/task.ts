export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type TaskPriority = 'low' | 'medium' | 'high'

export interface TaskResultReference {
  title: string
  detail?: string
}

export interface TaskExecutionTraceEntry {
  stage: string
  title: string
  status: string
  detail?: string
  metadata?: Record<string, string | number | boolean | null>
}

export interface TaskResult {
  kind: string
  title: string
  summary: string
  content: string
  bullets: string[]
  references: TaskResultReference[]
  executionTrace?: TaskExecutionTraceEntry[]
}

export interface TaskRouteDecision {
  intent: string
  workflowId: string
  workflowName: string
  executionAgentId?: string
  executionAgent: string
  executionPlan?: Record<string, unknown>
  selectedByMessageTrigger: boolean
  routeMessage: string
}

export interface Task {
  id: string
  title: string
  description: string
  status: TaskStatus
  priority: TaskPriority
  createdAt: string
  completedAt?: string
  agent: string
  tokens: number
  duration?: string
  workflowId?: string
  workflowRunId?: string
  traceId?: string
  channel?: string
  sessionId?: string
  userKey?: string
  currentStage?: string
  dispatchState?: string
  failureStage?: string
  failureMessage?: string
  deliveryStatus?: string
  deliveryMessage?: string
  statusReason?: string
  routeDecision?: TaskRouteDecision
  result?: TaskResult
}

export interface TaskStep {
  id: string
  title: string
  status: string
  startedAt?: string
  finishedAt?: string
  agent: string
  message?: string
  tokens?: number
}

export interface TaskListResponse {
  items: Task[]
  total: number
}

export interface TaskStepsResponse {
  items: TaskStep[]
  total: number
}

export interface TaskActionResponse {
  ok: boolean
  message: string
  task?: Task
}
