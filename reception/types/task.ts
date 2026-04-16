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
  timestamp?: string
  startedAt?: string
  finishedAt?: string
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
  workflowId?: string
  workflowName?: string
  executionAgentId?: string
  executionAgent: string
  interactionMode?: string | null
  receptionMode?: string | null
  workflowMode?: string | null
  requiresPermission?: boolean | null
  requiredCapabilities?: string[]
  userVisibleWorkflowMode?: string | null
  executionPlan?: Record<string, unknown>
  selectedByMessageTrigger: boolean
  routeMessage: string
  intentConfidence?: number | null
  intentScores?: Record<string, number>
  intentReasons?: Record<string, string[]>
  candidateWorkflows?: Array<Record<string, unknown>>
  skippedWorkflows?: Array<Record<string, string>>
  routingStrategy?: string | null
  executionSupport?: Record<string, unknown> | null
  confirmationStatus?: string | null
  confirmationDeadlineAt?: string | null
  approvalRequired?: boolean | null
  auditId?: string | null
  idempotencyKey?: string | null
  executionScope?: string | null
  routeRationale?: Record<string, unknown> | null
  fallbackPolicy?: Record<string, unknown> | null
}

export interface ManagerPacket {
  managerAgent?: string | null
  managerRole?: string | null
  userGoal?: string | null
  intent?: string | null
  interactionMode?: string | null
  receptionMode?: string | null
  workflowMode?: string | null
  workflowAdmission?: string | null
  taskShape?: string | null
  decompositionHint?: string | null
  deliveryMode?: string | null
  clarifyRequired?: boolean | null
  clarifyQuestion?: string | null
  managerAction?: string | null
  nextOwner?: string | null
  responseContract?: string | null
  handoffSummary?: string | null
  routingNote?: string | null
  sessionState?: string | null
  stateLabel?: string | null
}

export interface BrainDispatchSummary {
  intent?: string | null
  dispatchType?: string | null
  workflowMode?: string | null
  interactionMode?: string | null
  receptionMode?: string | null
  workflowName?: string | null
  executionAgent?: string | null
  managerAction?: string | null
  nextOwner?: string | null
  deliveryMode?: string | null
  responseContract?: string | null
  clarifyRequired?: boolean | null
  approvalRequired?: boolean | null
  executionScope?: string | null
  summaryLine?: string | null
  routingStrategy?: string | null
  executionTopology?: string | null
  fallbackMode?: string | null
  routeReasonSummary?: string | null
  sessionState?: string | null
  stateLabel?: string | null
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
  managerPacket?: ManagerPacket | null
  brainDispatchSummary?: BrainDispatchSummary | null
  brainFactSnapshot?: Record<string, unknown> | null
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
  metadata?: Record<string, string | number | boolean | null>
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
