export interface RuntimeQueueSnapshot {
  key: string
  label: string
  depth: number
  ready: number
  delayed: number
  activeLeases: number
  staleClaims: number
  retryScheduled: number
  deadLetters: number
}

export interface RuntimeAlert {
  key: string
  severity: 'warning' | 'critical' | string
  title: string
  detail: string
  source: string
  href?: string | null
  workflowRunId?: string | null
  taskId?: string | null
  updatedAt?: string | null
}

export interface RuntimeSnapshot {
  timestamp: string
  totalQueueDepth: number
  dispatchQueueDepth: number
  workflowExecutionQueueDepth: number
  agentExecutionQueueDepth: number
  activeDispatchLeases: number
  activeWorkflowExecutionLeases: number
  activeAgentExecutionLeases: number
  staleClaims: number
  retryScheduled: number
  deadLetters: number
  queues: RuntimeQueueSnapshot[]
  recentAlerts: RuntimeAlert[]
}
