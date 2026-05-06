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

export interface TaskAgentGroupMember {
  id?: string | null
  name?: string | null
  role?: string | null
  branchId?: string | null
  type?: string | null
  status?: string | null
  enabled?: boolean | null
  providerKey?: string | null
  providerLabel?: string | null
  model?: string | null
  boundSkillIds?: string[]
  boundToolIds?: string[]
  requestedSkillIds?: string[]
  requestedToolIds?: string[]
  natsSubject?: string | null
  soul?: string | null
  runtimeStatus?: string | null
  currentStepId?: string | null
  currentStepTitle?: string | null
  currentStepMessage?: string | null
  currentStepStartedAt?: string | null
  currentStepFinishedAt?: string | null
  selectedForDelivery?: boolean | null
}

export interface TaskAgentGroupTimelineEntry {
  id?: string | null
  kind?: string | null
  title: string
  detail?: string | null
  timestamp?: string | null
  actorAgentId?: string | null
  actorAgentName?: string | null
  metadata?: Record<string, unknown> | null
}

export interface TaskAgentGroup {
  id?: string | null
  name?: string | null
  status?: string | null
  topology?: string | null
  coordinationMode?: string | null
  dispatcherAgentId?: string | null
  developmentAgents?: TaskAgentGroupMember[]
  acceptanceAgent?: TaskAgentGroupMember | null
  requestedSkillIds?: string[]
  requestedToolIds?: string[]
  appliedSkillIds?: string[]
  appliedToolIds?: string[]
  natsSubjects?: Record<string, unknown> | null
  timeline?: TaskAgentGroupTimelineEntry[]
  warnings?: string[]
}

export interface Task {
  id: string
  tenantId?: string
  projectId?: string
  environment?: string
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
  confirmationStatus?: string
  approvalStatus?: string
  approvalRequired?: boolean
  auditId?: string
  idempotencyKey?: string
  executionScope?: string
  schedulePlan?: Record<string, unknown> | null
  routeDecision?: TaskRouteDecision
  managerPacket?: ManagerPacket | null
  brainDispatchSummary?: BrainDispatchSummary | null
  brainFactSnapshot?: Record<string, unknown> | null
  memoryInjectionSummary?: Record<string, unknown> | null
  contextPatchAudit?: Array<Record<string, unknown>>
  stateMachine?: Record<string, unknown> | null
  taskAgentGroup?: TaskAgentGroup | null
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

export interface TaskRealtimeResponse {
  type: string
  messageType: string
  taskId: string
  workflowId?: string | null
  timestamp?: string | null
  task?: Task | null
  steps?: TaskStepsResponse | null
}

export interface TaskActionResponse {
  ok: boolean
  message: string
  task?: Task
}
