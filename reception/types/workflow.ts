import type { RuntimeSnapshot } from '@/types/runtime'

export type WorkflowNodeType =
  | 'trigger'
  | 'agent'
  | 'condition'
  | 'parallel'
  | 'merge'
  | 'workflow'
  | 'sub_workflow'
  | 'trigger_workflow'
  | 'tool'
  | 'transform'
  | 'output'
  | 'aggregate'

export const WORKFLOW_TRIGGER_TYPES = [
  'message',
  'schedule',
  'webhook',
  'internal',
  'manual',
] as const

export type WorkflowTriggerType = (typeof WORKFLOW_TRIGGER_TYPES)[number]

export type WorkflowTriggerTypeOption = {
  value: WorkflowTriggerType
  label: string
}

export const WORKFLOW_TRIGGER_TYPE_LABELS: Record<WorkflowTriggerType, string> = {
  message: '消息触发',
  schedule: '定时触发',
  webhook: 'Webhook 触发',
  internal: '工作流触发',
  manual: '手动触发',
}

export const WORKFLOW_TRIGGER_TYPE_OPTIONS: WorkflowTriggerTypeOption[] = WORKFLOW_TRIGGER_TYPES.map(
  (value) => ({
    value,
    label: WORKFLOW_TRIGGER_TYPE_LABELS[value],
  }),
)

export const WORKFLOW_STATUSES = ['draft', 'active', 'running', 'paused'] as const

export type WorkflowKnownStatus = (typeof WORKFLOW_STATUSES)[number]
export type WorkflowStatus = WorkflowKnownStatus | (string & {})

export type WorkflowStatusOption = {
  value: WorkflowKnownStatus
  label: string
}

export const WORKFLOW_STATUS_LABELS: Record<WorkflowKnownStatus, string> = {
  draft: '草稿',
  active: '启用中',
  running: '运行中',
  paused: '已暂停',
}

export const WORKFLOW_STATUS_OPTIONS: WorkflowStatusOption[] = WORKFLOW_STATUSES.map((value) => ({
  value,
  label: WORKFLOW_STATUS_LABELS[value],
}))

export const WORKFLOW_PAGE_CATEGORIES = ['basic', 'professional', 'free', 'agent'] as const

export type WorkflowPageCategory = (typeof WORKFLOW_PAGE_CATEGORIES)[number]

export type WorkflowPageCategoryOption = {
  value: WorkflowPageCategory
  label: string
}

export const WORKFLOW_PAGE_DEFAULT_CATEGORY: WorkflowPageCategory = 'basic'

export const WORKFLOW_PAGE_CATEGORY_LABELS: Record<WorkflowPageCategory, string> = {
  basic: '基础工作流',
  professional: '专业工作流',
  free: '自由工作流',
  agent: 'agent工作流',
}

export const WORKFLOW_PAGE_CATEGORY_OPTIONS: WorkflowPageCategoryOption[] = WORKFLOW_PAGE_CATEGORIES.map(
  (value) => ({
    value,
    label: WORKFLOW_PAGE_CATEGORY_LABELS[value],
  }),
)

export interface WorkflowTrigger {
  type: WorkflowTriggerType
  keyword?: string | null
  cron?: string | null
  webhookPath?: string | null
  internalEvent?: string | null
  description?: string | null
  priority?: number
  channels?: string[]
  preferredLanguage?: 'zh' | 'en' | null
  stepDelaySeconds?: number | null
  maxDispatchRetry?: number | null
  dispatchRetryBackoffSeconds?: number | null
  executionTimeoutSeconds?: number | null
  naturalLanguageRule?: string | null
  schedulePlan?: Record<string, unknown> | null
}

export interface WorkflowNode {
  id: string
  type: WorkflowNodeType
  label: string
  x: number
  y: number
  description?: string | null
  config?: Record<string, unknown> | null
  agentId?: string | null
  toolId?: string | null
  workflowId?: string | null
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
}

export interface Workflow {
  id: string
  name: string
  description: string
  version: string
  status: WorkflowStatus
  updatedAt: string
  nodeCount: number
  edgeCount: number
  trigger: WorkflowTrigger
  agentBindings: string[]
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

export interface CreateWorkflowRequest {
  name: string
  description: string
  version: string
  status: string
  trigger: WorkflowTrigger
  agentBindings?: string[]
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

export interface UpdateWorkflowRequest {
  name?: string
  description?: string
  version?: string
  status?: string
  trigger?: WorkflowTrigger
  agentBindings?: string[]
  nodes?: WorkflowNode[]
  edges?: WorkflowEdge[]
}

export interface WorkflowListResponse {
  items: Workflow[]
  total: number
}

export interface WorkflowActionResponse {
  ok: boolean
  message: string
  workflow: Workflow
  runId?: string | null
  taskId?: string | null
  triggeredCount?: number | null
  triggeredWorkflowIds?: string[] | null
  triggeredRunIds?: string[] | null
  triggeredTaskIds?: string[] | null
  internalEventId?: string | null
  internalEventStatus?: string | null
  internalEventAttemptCount?: number | null
  deduplicated?: boolean | null
}

export interface InternalEventDelivery {
  id: string
  eventName: string
  source: string
  payload: Record<string, unknown>
  idempotencyKey?: string | null
  status: string
  attemptCount: number
  lastError?: string | null
  triggeredCount: number
  triggeredWorkflowIds: string[]
  triggeredRunIds: string[]
  triggeredTaskIds: string[]
  primaryWorkflow?: Workflow | null
  createdAt: string
  updatedAt: string
  deliveredAt?: string | null
}

export interface InternalEventDeliveryListResponse {
  items: InternalEventDelivery[]
  total: number
}

export interface InternalEventDeliveryActionResponse extends WorkflowActionResponse {
  delivery: InternalEventDelivery
  replayedFromDeliveryId?: string | null
}

export interface WorkflowRunNode {
  id: string
  type: string
  label: string
  status: 'idle' | 'waiting' | 'running' | 'completed' | 'error'
  agentId?: string | null
  message?: string | null
  tokens: number
  startedAt?: string | null
  finishedAt?: string | null
  attempt?: number
  executionInstanceKey?: string | null
  latestError?: string | null
  latestErrorAt?: string | null
  errorCount: number
  errorHistory: WorkflowRunNodeError[]
}

export interface WorkflowRunNodeError {
  id: string
  timestamp?: string | null
  severity: 'warning' | 'error' | string
  source: string
  agent: string
  message: string
  stepId?: string | null
  stepTitle?: string | null
}

export interface WorkflowRunLog {
  id: string
  timestamp: string
  type: 'info' | 'success' | 'warning' | 'error'
  agent: string
  message: string
}

export interface WorkflowRunRelationItem {
  id: string
  relationType: string
  sourceNodeId?: string | null
  sourceNodeLabel?: string | null
  sourceAttempt?: number | null
  executionInstanceKey?: string | null
  targetWorkflowId: string
  targetWorkflowName?: string | null
  targetRunId?: string | null
  targetTaskId?: string | null
  targetStatus?: string | null
  trigger?: string | null
  handoffNote?: string | null
  payloadPreview?: string | null
  createdAt: string
  updatedAt?: string | null
}

export interface WorkflowRunMonitor {
  triggerType: string
  dispatchState?: string | null
  monitorState: string
  nextAction: string
  nextDispatchAt?: string | null
  isOverdue: boolean
  dispatcherId?: string | null
  dispatchClaimedAt?: string | null
  dispatchLeaseExpiresAt?: string | null
  dispatchFailureCount: number
  lastDispatchError?: string | null
  executionAgentId?: string | null
  warningCount: number
  latestWarning?: string | null
}

export interface WorkflowRunDispatchContext {
  summaryOnly?: boolean
  type?: string | null
  state?: string | null
  queuedAt?: string | null
  updatedAt?: string | null
  entrypoint?: string | null
  entrypointAgent?: string | null
  traceId?: string | null
  channel?: string | null
  messageId?: string | null
  platformUserId?: string | null
  chatId?: string | null
  userKey?: string | null
  sessionId?: string | null
  detectedLang?: string | null
  preferredLanguage?: string | null
  messagePreview?: string | null
  memoryHits?: number
  routeDecision?: Record<string, unknown> | null
  managerPacket?: import('@/types/task').ManagerPacket | null
  brainDispatchSummary?: import('@/types/task').BrainDispatchSummary | null
  brainFactSnapshot?: Record<string, unknown> | null
  internalEventPayload?: Record<string, unknown> | null
  workflowReturn?: Record<string, unknown> | null
  executionPlanSnapshot?: Record<string, unknown> | null
  fallbackHistory?: Array<Record<string, unknown>>
  fallbackRecoveryState?: string | null
  fallbackRecoveryReason?: string | null
  fallbackRecoveryAction?: string | null
  fallbackRecoveryAt?: string | null
  parentWorkflowId?: string | null
  parentWorkflowName?: string | null
  parentRunId?: string | null
  parentNodeId?: string | null
  parentNodeLabel?: string | null
  workflowRelationType?: string | null
  workflowRelations?: WorkflowRunRelationItem[]
  triggerPayload?: Record<string, unknown> | null
  manualHandoffRequiredAt?: string | null
  manualHandoffSource?: string | null
  manualHandoffOperator?: string | null
  manualHandoffNote?: string | null
  dispatchedAt?: string | null
  executionAgentId?: string | null
  executionAgent?: string | null
  completedAt?: string | null
  failedAt?: string | null
  failureStage?: string | null
  failureMessage?: string | null
  deliveryStatus?: string | null
  deliveryMessage?: string | null
  deliveryCompletedAt?: string | null
  deliveryFailedAt?: string | null
  resultKind?: string | null
  contextPatchCount?: number
  lastContextPatchAt?: string | null
  lastContextPatchTraceId?: string | null
  lastContextPatchPreview?: string | null
  workflowCallStack?: string[]
  internalEventId?: string | null
  internalEventStatus?: string | null
  internalEventAttemptCount?: number | null
  triggeredWorkflowIds?: string[]
  triggeredRunIds?: string[]
  triggeredTaskIds?: string[]
  selectedNodeId?: string | null
  selectedNodeLabel?: string | null
  selectedNodeType?: string | null
  selectedNodeDescription?: string | null
  selectedNodeConfig?: Record<string, unknown> | null
}

export interface WorkflowRun {
  id: string
  summaryOnly?: boolean
  workflowId: string
  workflowName: string
  taskId?: string | null
  trigger: string
  intent?: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  createdAt: string
  updatedAt: string
  startedAt: string
  completedAt?: string | null
  currentStage: string
  runtimeStage?: string | null
  finalStage?: string | null
  lastCompletedNode?: string | null
  lastCompletedNodeId?: string | null
  activeEdges: string[]
  nodes: WorkflowRunNode[]
  logs: WorkflowRunLog[]
  failureStage?: string | null
  failureMessage?: string | null
  deliveryStatus?: string | null
  deliveryMessage?: string | null
  statusReason?: string | null
  metrics?: WorkflowRunMetrics | null
  tokensTotal?: number
  durationMs?: number | null
  stepCount?: number
  executionAgentId?: string | null
  executionAgent?: string | null
  agentStartedAt?: string | null
  agentFinishedAt?: string | null
  dispatchContext?: WorkflowRunDispatchContext | null
  monitor?: WorkflowRunMonitor | null
  nodeCount?: number
  logCount?: number
  activeEdgeCount?: number
}

export interface WorkflowRunMetrics {
  tokensTotal: number
  durationMs?: number | null
  stepCount: number
  executionAgentId?: string | null
  executionAgent?: string | null
  agentStartedAt?: string | null
  agentFinishedAt?: string | null
}

export interface WorkflowRunListResponse {
  items: WorkflowRun[]
  total: number
}

export interface WorkflowMonitorStats {
  total: number
  queued: number
  scheduled: number
  claimed: number
  running: number
  retryWaiting: number
  overdue: number
  failed: number
  completed: number
  cancelled: number
  unhealthy: number
}

export interface WorkflowMonitorResponse {
  workflowId: string
  timestamp: string
  workflow: Workflow
  stats: WorkflowMonitorStats
  items: WorkflowRun[]
  alerts: string[]
  runtime?: RuntimeSnapshot | null
}

export interface WorkflowRealtimePayload {
  type: string
  workflowId: string
  timestamp: string
  items: WorkflowRun[]
  run?: WorkflowRun | null
}
