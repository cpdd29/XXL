import type { ToolHealthStatus } from '@/shared/types/tool'

export type ToolSourceType = 'internal' | 'local_tool' | 'external_repo' | 'mcp_server' | 'unknown'

export interface ToolSource {
  id: string
  name: string
  type: ToolSourceType
  kind: string
  description: string
  path: string | null
  enabled: boolean
  healthStatus: ToolHealthStatus
  healthMessage: string
  healthSummary: Record<string, unknown> | null
  scannedCapabilityCount: number
  linkedAgents: string[]
  providerSummary: string
  configSummary: string
  configDetail: Record<string, unknown> | null
  registrySummary: Record<string, unknown> | null
  bridgeSummary: Record<string, unknown> | null
  doctorSummary: Record<string, unknown> | null
  tags: string[]
  lastScannedAt: string | null
  notes: string[]
  scanStatus: string
  status: string
  lastCheckedAt: string | null
  sourceMode: string | null
  legacyFallback: boolean
  deprecated: boolean
  activationMode: string | null
  toolTotal?: number
  sourceTools?: Array<Record<string, unknown>>
}

export interface ToolSourceListResponse {
  governanceSummary?: Record<string, unknown> | null
  items: ToolSource[]
  total: number
}
