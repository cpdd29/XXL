import type { ToolSourceType } from '@/shared/types/tool-source'

export type ToolType = 'skill' | 'tool' | 'mcp' | 'unknown'

export type ToolHealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export type ToolMigrationStage =
  | 'retained'
  | 'bridging'
  | 'externalized'
  | 'pending_removal'
  | 'deprecated'
  | 'unknown'

export interface ToolHealthSummary {
  status?: string
  checkedAt?: string | null
  reason?: string
  runtime?: Record<string, unknown> | null
}

export interface ToolPermissions {
  requiresPermission: boolean
  scopes: string[]
  roles: string[]
  approvalRequired: boolean
  executionScope?: string | null
}

export interface ToolInvocationSummary {
  lastCalledAt: string | null
  callCount: number
  successCalls: number
  failedCalls: number
  lastStatus: string
  lastError: string | null
  summary: string
}

export interface Tool {
  id: string
  name: string
  description: string
  type: ToolType
  sourceId: string | null
  sourceName: string
  sourceType: ToolSourceType
  sourceKind: string
  enabled: boolean
  healthStatus: ToolHealthStatus
  healthMessage: string
  healthSummary: ToolHealthSummary | null
  bridgeMode: string
  migrationStage: ToolMigrationStage
  trafficPolicy: Record<string, unknown> | null
  rollbackSummary: Record<string, unknown> | null
  linkedAgents: string[]
  providerSummary: string
  configSummary: string
  capabilityCount: number
  tags: string[]
  lastScannedAt: string | null
  linkedWorkflows: string[]
  requiredPermissions: string[]
  permissions: ToolPermissions
  requiredCapabilities: string[]
  inputSchema: Record<string, unknown> | null
  outputSchema: Record<string, unknown> | null
  configDetail: Record<string, unknown> | null
  invocationSummary: ToolInvocationSummary
}

export interface ToolListResponse {
  items: Tool[]
  total: number
}
