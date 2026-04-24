import type { AuditLog } from '@/shared/types/security'

export type ExternalCapabilityType = 'agent' | 'skill'

export interface ExternalCapabilityRolloutPolicy {
  canaryPercent: number
  routeKey: string
}

export interface ExternalCapabilityRollbackPolicy {
  active: boolean
  targetVersionId: string | null
}

export interface ExternalCapabilityGovernanceSummary {
  agentFamilies: number
  skillFamilies: number
  totalFamilies: number
  totalVersions: number
  routable: number
  openCircuits: number
  offline: number
}

export interface ExternalCapabilityGovernanceFamilySummary {
  capabilityType: ExternalCapabilityType
  family: string
  name: string
  currentId: string
  currentVersion: string | null
  releaseChannel: string | null
  compatibility: string[]
  defaultVersionId: string | null
  fallbackVersionId: string | null
  deprecated: boolean
  enabled: boolean
  routable: boolean
  status: string
  circuitState: string | null
  consecutiveFailures: number
  nextRetryAt: string | null
  lastHeartbeatAt: string | null
  health: Record<string, unknown>
  invocation: Record<string, unknown>
  rolloutPolicy: ExternalCapabilityRolloutPolicy
  rollbackPolicy: ExternalCapabilityRollbackPolicy
  versionCount: number
}

export interface ExternalCapabilityGovernanceOverviewResponse {
  items: ExternalCapabilityGovernanceFamilySummary[]
  total: number
  summary: ExternalCapabilityGovernanceSummary
  recentAudits: AuditLog[]
}

export interface ExternalCapabilityVersionItem {
  capabilityType: ExternalCapabilityType
  id: string
  family: string
  name: string
  version: string
  releaseChannel: string | null
  compatibility: string[]
  defaultVersion: boolean
  fallbackVersionId: string | null
  deprecated: boolean
  enabled: boolean
  routable: boolean
  status: string | null
  rolloutPolicy: ExternalCapabilityRolloutPolicy
  rollbackPolicy: ExternalCapabilityRollbackPolicy
}

export interface ExternalCapabilityVersionListResponse {
  items: ExternalCapabilityVersionItem[]
  total: number
}

export interface ExternalCapabilityVersionUpdateRequest {
  fallbackVersionId?: string | null
  deprecated?: boolean
  rolloutPolicy?: Partial<ExternalCapabilityRolloutPolicy>
  rollbackPolicy?: Partial<ExternalCapabilityRollbackPolicy>
}

export interface ExternalCapabilityActionResponse {
  ok: boolean
  message: string
  capabilityType: ExternalCapabilityType
  item: Record<string, unknown>
}

export interface ExternalCapabilityAuditQuery {
  capabilityType?: ExternalCapabilityType | null
  limit?: number
  status?: AuditLog['status'] | null
}
