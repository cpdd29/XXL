import type { RuntimeSnapshot } from '@/types/runtime'
import type { AgentType } from '@/types/agent'

export interface DashboardStat {
  key: string
  title: string
  value: string | number
  description: string
  trendValue: number
  trendPositive: boolean
}

export interface DashboardTrendPoint {
  time: string
  requests: number
  tokens: number
  durationMs: number
}

export type LogType = 'info' | 'success' | 'warning' | 'error'

export interface DashboardAgentStatus {
  id: string
  name: string
  type: AgentType
  status: 'idle' | 'running' | 'waiting' | 'error'
  tasksCompleted: number
  avgResponseTime: string
}

export interface DashboardTentacleMetric {
  agentId?: string | null
  name: string
  type: string
  calls: number
  successCalls: number
  successRate: number
  tokens: number
  durationMs: number
}

export interface DashboardCostSummary {
  runCount: number
  totalTokens: number
  totalDurationMs: number
  avgDurationMs: number
}

export interface DashboardCostDistributionItem {
  label: string
  calls: number
  tokens: number
  durationMs: number
  sharePercent: number
}

export interface DashboardSlaThreshold {
  metric: string
  healthyGte?: number | null
  healthyLte?: number | null
  degradedGte?: number | null
  degradedLte?: number | null
}

export interface DashboardSlaSummary {
  windowHours: number
  totalRuns: number
  successRate: number
  failureRate: number
  timeoutRate: number
  fallbackRate: number
  deliveryFailureRate: number
  securityRiskRate: number
  healthStatus: 'healthy' | 'degraded' | 'critical'
}

export interface DashboardHealthSignal {
  key: string
  label: string
  status: 'healthy' | 'degraded' | 'critical'
  value: number
  unit: string
  summary: string
  threshold: DashboardSlaThreshold
}

export interface DashboardPreparedAlert {
  key: string
  severity: 'warning' | 'critical'
  title: string
  detail: string
  source: string
  href?: string | null
}

export interface DashboardLogEntry {
  id: string
  timestamp: string
  type: LogType
  agent: string
  message: string
}

export interface DashboardFailureBreakdownItem {
  stage: string
  label: string
  count: number
}

export interface DashboardBrainBreakdownItem {
  key: string
  label: string
  count: number
  hint?: string | null
}

export interface DashboardManagerQueueItem {
  taskId: string
  title: string
  status: string
  managerAction?: string | null
  nextOwner?: string | null
  responseContract?: string | null
  deliveryMode?: string | null
  taskShape?: string | null
  clarifyQuestion?: string | null
  currentStage?: string | null
  sessionState?: string | null
  stateLabel?: string | null
}

export interface DashboardReplyQueueItem {
  taskId: string
  title: string
  channel?: string | null
  userLabel?: string | null
  userKey?: string | null
  sessionId?: string | null
  status: string
  clarifyQuestion?: string | null
  currentStage?: string | null
  nextOwner?: string | null
  receptionMode?: string | null
  workflowMode?: string | null
  responseContract?: string | null
  confirmationStatus?: string | null
  sessionState?: string | null
  stateLabel?: string | null
}

export interface DashboardStatsResponse {
  stats: DashboardStat[]
  chartData: DashboardTrendPoint[]
  agentStatuses: DashboardAgentStatus[]
  costSummary: DashboardCostSummary
  slaSummary: DashboardSlaSummary
  healthSignals: DashboardHealthSignal[]
  preparedAlerts: DashboardPreparedAlert[]
  tentacleMetrics: DashboardTentacleMetric[]
  costDistribution: DashboardCostDistributionItem[]
  failureBreakdown: DashboardFailureBreakdownItem[]
  brainBreakdown: DashboardBrainBreakdownItem[]
  managerQueue: DashboardManagerQueueItem[]
  replyQueue: DashboardReplyQueueItem[]
  realtimeLogs: DashboardLogEntry[]
  runtime: RuntimeSnapshot
}
