export type AgentStatus =
  | 'idle'
  | 'running'
  | 'waiting'
  | 'busy'
  | 'degraded'
  | 'offline'
  | 'maintenance'
  | 'error'
export type AgentType = 'search' | 'write' | 'security' | 'intent' | 'default' | 'output'
export type AgentRuntimeState = 'online' | 'degraded' | 'offline' | 'unknown'

export interface AgentConfigSummary {
  status: string
  directory: string | null
  version: string | null
  filesLoaded: string[]
  toolsCount: number
  examplesCount: number
  memoryRulesPresent: boolean
  soulPresent: boolean
  warnings: string[]
}

export interface Agent {
  id: string
  name: string
  description: string
  type: AgentType
  status: AgentStatus
  enabled: boolean
  tasksCompleted: number
  tasksTotal: number
  avgResponseTime: string
  tokensUsed: number
  tokensLimit: number
  successRate: number
  lastActive: string
  runtimeStatus?: AgentRuntimeState | null
  runtimeStatusReason?: string | null
  routable?: boolean | null
  runtimePriority?: number | null
  lastHeartbeatAt?: string | null
  heartbeatIntervalSeconds?: number | null
  heartbeatTimeoutSeconds?: number | null
  runtimeMetrics?: {
    heartbeatAgeSeconds?: number | null
    lastReportedStatus?: string | null
    source?: string | null
    load?: number | null
    queueDepth?: number | null
  } | null
  configSummary?: AgentConfigSummary | null
  configSnapshot?: Record<string, unknown> | null
}

export interface AgentRuntimeStatus {
  id: string
  name: string
  status: AgentStatus
  runtimeStatus?: AgentRuntimeState | null
  enabled: boolean
  lastActive: string
  avgResponseTime: string
  tokensUsed: number
  tokensLimit: number
}

export interface AgentListResponse {
  items: Agent[]
  total: number
}

export interface AgentActionResponse {
  ok: boolean
  message: string
  agent: Agent
}
