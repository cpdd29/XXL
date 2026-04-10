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
}

export type LogType = 'info' | 'success' | 'warning' | 'error'

export interface DashboardAgentStatus {
  id: string
  name: string
  type: 'search' | 'write' | 'security' | 'intent' | 'default' | 'output'
  status: 'idle' | 'running' | 'waiting' | 'error'
  tasksCompleted: number
  avgResponseTime: string
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

export interface DashboardStatsResponse {
  stats: DashboardStat[]
  chartData: DashboardTrendPoint[]
  agentStatuses: DashboardAgentStatus[]
  failureBreakdown: DashboardFailureBreakdownItem[]
  realtimeLogs: DashboardLogEntry[]
}
