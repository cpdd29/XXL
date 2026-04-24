'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  Tool,
  ToolHealthStatus,
  ToolInvocationSummary,
  ToolListResponse,
  ToolMigrationStage,
  ToolPermissions,
  ToolSource,
  ToolSourceListResponse,
  ToolSourceType,
  ToolType,
} from '@/shared/types'

type JsonObject = Record<string, unknown>

function asObject(value: unknown): JsonObject | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as JsonObject
}

function asString(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const lowered = value.trim().toLowerCase()
    if (['true', 'enabled', 'active', 'online', 'healthy', 'ok', '1', 'yes'].includes(lowered)) return true
    if (['false', 'disabled', 'inactive', 'offline', '0', 'no'].includes(lowered)) return false
  }
  return null
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim()
      const objectItem = asObject(item)
      if (!objectItem) return null
      return (
        asString(objectItem.name) ??
        asString(objectItem.id) ??
        asString(objectItem.agent) ??
        asString(objectItem.agentId) ??
        asString(objectItem.scope) ??
        null
      )?.trim() ?? null
    })
    .filter((item): item is string => Boolean(item))
}

function firstValue(record: JsonObject, keys: string[]): unknown {
  for (const key of keys) {
    if (key in record) return record[key]
  }
  return undefined
}

function firstValueFromRecords(records: Array<JsonObject | null>, keys: string[]): unknown {
  for (const record of records) {
    if (!record) continue
    const value = firstValue(record, keys)
    if (value !== undefined) return value
  }
  return undefined
}

function summarizeUnknown(value: unknown): string {
  if (typeof value === 'string') return value.trim() || '-'
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    const sampled = value
      .map((item) => asString(item) ?? asString(asObject(item)?.name) ?? null)
      .filter((item): item is string => Boolean(item))
      .slice(0, 3)
    if (sampled.length > 0) return sampled.join(', ')
    return `${value.length} 项`
  }
  const objectValue = asObject(value)
  if (objectValue) {
    const keys = Object.keys(objectValue)
    if (keys.length === 0) return '-'
    return keys.slice(0, 4).join(', ')
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return '-'
}

function extractItems(payload: unknown, preferredKey: string): unknown[] {
  if (Array.isArray(payload)) return payload
  const root = asObject(payload)
  if (!root) return []
  const preferred = root[preferredKey]
  if (Array.isArray(preferred)) return preferred
  if (Array.isArray(root.items)) return root.items
  if (Array.isArray(root.data)) return root.data
  return []
}

function normalizeTotal(payload: unknown, fallbackLength: number): number {
  const root = asObject(payload)
  if (!root) return fallbackLength
  return asNumber(root.total) ?? fallbackLength
}

function normalizeToolType(value: unknown): ToolType {
  const normalized = asString(value)?.trim().toLowerCase()
  if (normalized === 'skill') return 'skill'
  if (normalized === 'tool') return 'tool'
  if (normalized === 'mcp') return 'mcp'
  return 'unknown'
}

function normalizeToolSourceType(value: unknown): ToolSourceType {
  const normalized = asString(value)?.trim().toLowerCase()
  if (normalized === 'internal' || normalized === 'internal_config' || normalized === 'internal-config') {
    return 'internal'
  }
  if (
    normalized === 'local_tool' ||
    normalized === 'local-tool' ||
    normalized === 'local' ||
    normalized === 'local_agents' ||
    normalized === 'local-agents'
  ) {
    return 'local_tool'
  }
  if (normalized === 'external_repo' || normalized === 'external-repo' || normalized === 'external') {
    return 'external_repo'
  }
  if (normalized === 'mcp_server' || normalized === 'mcp-server' || normalized === 'mcp') return 'mcp_server'
  return 'unknown'
}

function normalizeToolHealthStatus(value: unknown): ToolHealthStatus {
  const normalized = asString(value)?.trim().toLowerCase()
  if (
    normalized &&
    ['healthy', 'ok', 'online', 'active', 'ready', 'pass', 'available', 'success'].includes(normalized)
  ) {
    return 'healthy'
  }
  if (normalized && ['degraded', 'warn', 'warning', 'partial'].includes(normalized)) {
    return 'degraded'
  }
  if (
    normalized &&
    ['unhealthy', 'error', 'failed', 'offline', 'down', 'unavailable', 'missing', 'disabled'].includes(normalized)
  ) {
    return 'unhealthy'
  }
  return 'unknown'
}

function normalizeSourceMode(value: unknown): string | null {
  const raw = asString(value)?.trim()
  if (!raw) return null
  const normalized = raw.toLowerCase().replace(/-/g, '_')
  if (normalized === 'external_only' || normalized === 'hybrid' || normalized === 'local_only') {
    return normalized
  }
  return raw
}

function normalizeMigrationStage(value: unknown): ToolMigrationStage {
  const normalized = asString(value)?.trim().toLowerCase()
  if (!normalized) return 'unknown'
  if (['retained', 'keep', 'kept'].includes(normalized)) return 'retained'
  if (['bridging', 'bridge', 'shadow', 'dual_run'].includes(normalized)) return 'bridging'
  if (['externalized', 'external', 'mcp_default'].includes(normalized)) return 'externalized'
  if (['pending_removal', 'sunset', 'cleanup'].includes(normalized)) return 'pending_removal'
  if (['deprecated'].includes(normalized)) return 'deprecated'
  return 'unknown'
}

function normalizePermissions(value: unknown): ToolPermissions {
  const payload = asObject(value)
  if (!payload) {
    return {
      requiresPermission: false,
      scopes: [],
      roles: [],
      approvalRequired: false,
      executionScope: null,
    }
  }

  return {
    requiresPermission: asBoolean(firstValue(payload, ['requiresPermission', 'requires_permission'])) ?? false,
    scopes: asStringArray(firstValue(payload, ['scopes', 'scope'])),
    roles: asStringArray(firstValue(payload, ['roles'])),
    approvalRequired: asBoolean(firstValue(payload, ['approvalRequired', 'approval_required'])) ?? false,
    executionScope: asString(firstValue(payload, ['executionScope', 'execution_scope'])) ?? null,
  }
}

function normalizeInvocationSummary(record: JsonObject): ToolInvocationSummary {
  const nested = asObject(firstValue(record, ['recentCallSummary', 'recent_call_summary'])) ?? {}
  const lastCalledAt =
    asString(
      firstValue(nested, ['lastCalledAt', 'last_called_at']) ??
        firstValue(record, ['lastCalledAt', 'last_called_at', 'lastInvokedAt', 'last_invoked_at']),
    ) ?? null
  const totalCalls =
    asNumber(firstValue(nested, ['totalCalls', 'total_calls'])) ??
    asNumber(firstValue(record, ['callCount', 'call_count', 'invocationCount', 'invocation_count'])) ??
    0
  const successCalls =
    asNumber(firstValue(nested, ['successCalls', 'success_calls'])) ??
    Math.max(0, totalCalls - (asNumber(firstValue(nested, ['failedCalls', 'failed_calls'])) ?? 0))
  const failedCalls = asNumber(firstValue(nested, ['failedCalls', 'failed_calls'])) ?? 0
  const lastStatus = asString(firstValue(nested, ['lastStatus', 'last_status'])) ?? 'never_called'
  const lastError = asString(firstValue(nested, ['lastError', 'last_error'])) ?? null
  const summary =
    asString(firstValue(record, ['recentInvocationSummary', 'recent_invocation_summary'])) ??
    (totalCalls > 0
      ? `累计 ${totalCalls} 次，成功 ${successCalls} 次，失败 ${failedCalls} 次，最近状态 ${lastStatus}`
      : '暂无调用记录')

  return {
    lastCalledAt,
    callCount: totalCalls,
    successCalls,
    failedCalls,
    lastStatus,
    lastError,
    summary,
  }
}

export function normalizeTool(item: unknown, index: number): Tool | null {
  const row = asObject(item)
  if (!row) return null

  const sourceValue = asObject(firstValue(row, ['source', 'tool_source', 'toolSource', 'sourceInfo']))
  const healthSummary = asObject(firstValue(row, ['healthSummary', 'health_summary']))
  const configSummaryRaw = firstValue(row, ['configSummary', 'config_summary'])
  const configDetail = asObject(firstValue(row, ['configDetail', 'config_detail'])) ?? asObject(configSummaryRaw)
  const permissions = normalizePermissions(firstValue(row, ['permissions']))

  const sourceId =
    asString(firstValue(row, ['sourceId', 'source_id'])) ??
    asString(firstValue(row, ['source'])) ??
    asString(sourceValue?.id) ??
    null
  const sourceName =
    asString(firstValue(row, ['sourceName', 'source_name'])) ??
    asString(firstValue(row, ['source'])) ??
    asString(sourceValue?.name) ??
    '未标记来源'
  const sourceType = normalizeToolSourceType(
    firstValue(row, ['sourceType', 'source_type', 'sourceKind', 'source_kind']) ??
      sourceValue?.type ??
      sourceValue?.sourceType ??
      sourceValue?.kind,
  )

  const agents = [
    ...asStringArray(firstValue(row, ['agentIds', 'agent_ids'])),
    ...asStringArray(firstValue(row, ['linkedAgents', 'linked_agents', 'agentNames', 'agent_names'])),
    ...asStringArray(firstValue(row, ['agents', 'agent_list'])),
  ]
  const uniqueAgents = [...new Set(agents)]

  const providers = asStringArray(firstValue(row, ['providers', 'provider_list']))
  const providerSummary =
    asString(firstValue(row, ['providerSummary', 'provider_summary'])) ??
    asString(firstValue(row, ['provider'])) ??
    summarizeUnknown(providers.length > 0 ? providers : firstValue(row, ['provider_config', 'providerConfig']))

  const requiredCapabilities = asStringArray(
    firstValue(row, ['requiredCapabilities', 'required_capabilities', 'capabilities']),
  )
  const requiredPermissions = [
    ...new Set([
      ...asStringArray(firstValue(row, ['requiredPermissions', 'required_permissions'])),
      ...permissions.scopes,
      ...(permissions.requiresPermission ? ['requires_permission'] : []),
    ]),
  ]
  const linkedWorkflows = asStringArray(
    firstValue(row, ['linkedWorkflows', 'linked_workflows', 'workflowNames', 'workflow_names', 'workflows']),
  )

  const bridgeMode =
    asString(firstValue(row, ['bridgeMode', 'bridge_mode'])) ??
    asString(firstValue(configDetail ?? {}, ['bridgeMode', 'bridge_mode'])) ??
    'catalog'
  const migrationStage = normalizeMigrationStage(
    firstValue(row, ['migrationStage', 'migration_stage']) ??
      firstValue(configDetail ?? {}, ['migrationStage', 'migration_stage']),
  )

  const trafficPolicy = asObject(firstValue(row, ['trafficPolicy', 'traffic_policy'])) ??
    asObject(firstValue(configDetail ?? {}, ['trafficPolicy', 'traffic_policy']))
  const rollbackSummary = asObject(firstValue(row, ['rollbackSummary', 'rollback_summary'])) ??
    asObject(firstValue(configDetail ?? {}, ['rollbackSummary', 'rollback_summary']))

  return {
    id:
      asString(firstValue(row, ['id', 'toolId', 'tool_id'])) ??
      asString(firstValue(row, ['name', 'tool_name'])) ??
      `tool-${index + 1}`,
    name: asString(firstValue(row, ['name', 'tool_name'])) ?? `tool-${index + 1}`,
    description: asString(firstValue(row, ['description', 'desc', 'summary'])) ?? '',
    type: normalizeToolType(firstValue(row, ['type', 'tool_type', 'category'])),
    sourceId,
    sourceName,
    sourceType,
    sourceKind:
      asString(firstValue(row, ['sourceKind', 'source_kind'])) ??
      asString(firstValue(sourceValue ?? {}, ['kind', 'sourceKind', 'source_kind'])) ??
      'unknown',
    enabled: asBoolean(firstValue(row, ['enabled', 'is_enabled', 'active'])) ?? true,
    healthStatus: normalizeToolHealthStatus(
      firstValue(row, ['healthStatus', 'health_status', 'health', 'status']) ??
        firstValue(healthSummary ?? {}, ['status']),
    ),
    healthMessage:
      asString(firstValue(row, ['healthMessage', 'health_message', 'message', 'status_reason'])) ??
      asString(firstValue(healthSummary ?? {}, ['reason'])) ??
      '',
    healthSummary: healthSummary
      ? {
          status: asString(firstValue(healthSummary, ['status'])) ?? undefined,
          checkedAt: asString(firstValue(healthSummary, ['checkedAt', 'checked_at'])) ?? null,
          reason: asString(firstValue(healthSummary, ['reason'])) ?? undefined,
          runtime: asObject(firstValue(healthSummary, ['runtime'])),
        }
      : null,
    bridgeMode,
    migrationStage,
    trafficPolicy: trafficPolicy ?? null,
    rollbackSummary: rollbackSummary ?? null,
    linkedAgents: uniqueAgents,
    providerSummary,
    configSummary: asString(configSummaryRaw) ?? summarizeUnknown(configSummaryRaw),
    capabilityCount:
      asNumber(firstValue(row, ['capabilityCount', 'capability_count', 'scannedCapabilityCount'])) ??
      requiredCapabilities.length,
    tags: asStringArray(firstValue(row, ['tags', 'labels'])),
    lastScannedAt:
      asString(firstValue(row, ['lastScannedAt', 'last_scanned_at', 'updatedAt', 'updated_at'])) ??
      asString(firstValue(healthSummary ?? {}, ['checkedAt', 'checked_at'])) ??
      null,
    linkedWorkflows,
    requiredPermissions,
    permissions,
    requiredCapabilities,
    inputSchema: asObject(firstValue(row, ['inputSchema', 'input_schema', 'input', 'inputs', 'parameters'])),
    outputSchema: asObject(firstValue(row, ['outputSchema', 'output_schema', 'output', 'outputs', 'result_schema'])),
    configDetail,
    invocationSummary: normalizeInvocationSummary(row),
  }
}

export function normalizeToolSource(item: unknown, index: number): ToolSource | null {
  const row = asObject(item)
  if (!row) return null

  const healthSummary = asObject(firstValue(row, ['healthSummary', 'health_summary']))
  const configSummaryRaw = firstValue(row, ['configSummary', 'config_summary'])
  const configDetail = asObject(configSummaryRaw)
  const registrySummary = asObject(firstValue(row, ['registry', 'registrySummary', 'registry_summary']))
  const bridgeSummary = asObject(firstValue(row, ['bridgeSummary', 'bridge_summary']))
  const doctorSummary = asObject(firstValue(row, ['doctorSummary', 'doctor_summary']))
  const metadataSummary = asObject(firstValue(row, ['metadata']))
  const sourceTools = extractItems(firstValue(row, ['tools']) ?? [], 'tools').map((entry) => asObject(entry)).filter(Boolean) as Array<Record<string, unknown>>

  const agents = [
    ...asStringArray(firstValue(row, ['linkedAgents', 'linked_agents', 'agentNames', 'agent_names'])),
    ...asStringArray(firstValue(row, ['agents', 'agent_list'])),
  ]
  const uniqueAgents = [...new Set(agents)]

  const id =
    asString(firstValue(row, ['id', 'sourceId', 'source_id'])) ??
    asString(firstValue(row, ['name', 'source_name'])) ??
    `source-${index + 1}`
  const status = asString(firstValue(row, ['status', 'state'])) ?? 'unknown'
  const scanStatus = asString(firstValue(row, ['scanStatus', 'scan_status'])) ?? 'unknown'
  const notes = asStringArray(firstValue(row, ['notes', 'warnings', 'messages']))
  const enabled =
    asBoolean(firstValue(row, ['enabled', 'is_enabled', 'active'])) ??
    !['disabled', 'inactive', 'unavailable'].includes(status.toLowerCase())

  const healthMessage =
    asString(firstValue(row, ['healthMessage', 'health_message', 'message', 'status_reason'])) ??
    asString(firstValue(healthSummary ?? {}, ['reason'])) ??
    summarizeUnknown(notes)

  const governanceContexts: Array<JsonObject | null> = [
    row,
    registrySummary,
    configDetail,
    bridgeSummary,
    doctorSummary,
    metadataSummary,
    asObject(firstValue(registrySummary ?? {}, ['metadata'])),
    asObject(firstValue(configDetail ?? {}, ['metadata'])),
    asObject(firstValue(bridgeSummary ?? {}, ['metadata'])),
    asObject(firstValue(doctorSummary ?? {}, ['metadata'])),
  ]
  const sourceMode = normalizeSourceMode(
    firstValueFromRecords(governanceContexts, ['sourceMode', 'source_mode']),
  )
  const deprecated =
    asBoolean(firstValueFromRecords(governanceContexts, ['deprecated', 'isDeprecated', 'is_deprecated'])) ?? false
  const legacyFallback =
    asBoolean(
      firstValueFromRecords(governanceContexts, ['legacyFallback', 'legacy_fallback', 'isLegacyFallback']),
    ) ?? false
  const activationMode =
    asString(firstValueFromRecords(governanceContexts, ['activationMode', 'activation_mode'])) ?? null

  return {
    id,
    name: asString(firstValue(row, ['name', 'source_name'])) ?? id,
    type: normalizeToolSourceType(firstValue(row, ['type', 'kind', 'source_type', 'category'])),
    kind: asString(firstValue(row, ['kind', 'sourceKind', 'source_kind'])) ?? 'unknown',
    description: asString(firstValue(row, ['description', 'desc', 'summary'])) ?? summarizeUnknown(notes),
    path: asString(firstValue(row, ['path', 'directory', 'location'])) ?? null,
    enabled,
    healthStatus: normalizeToolHealthStatus(
      firstValue(row, ['healthStatus', 'health_status', 'health', 'status']) ??
        firstValue(healthSummary ?? {}, ['status']),
    ),
    healthMessage,
    healthSummary,
    scannedCapabilityCount:
      asNumber(firstValue(row, ['scannedCapabilityCount', 'scanned_capability_count', 'toolCount', 'tool_count'])) ??
      sourceTools.length,
    linkedAgents: uniqueAgents,
    providerSummary:
      asString(firstValue(row, ['providerSummary', 'provider_summary'])) ??
      summarizeUnknown(firstValue(row, ['provider', 'providers', 'kind'])),
    configSummary: asString(configSummaryRaw) ?? summarizeUnknown(configSummaryRaw),
    configDetail,
    registrySummary,
    bridgeSummary,
    doctorSummary,
    tags: asStringArray(firstValue(row, ['tags', 'labels'])),
    lastScannedAt:
      asString(firstValue(row, ['lastScannedAt', 'last_scanned_at', 'updatedAt', 'updated_at'])) ??
      asString(firstValue(healthSummary ?? {}, ['checkedAt', 'checked_at'])) ??
      null,
    notes,
    scanStatus,
    status,
    lastCheckedAt:
      asString(firstValue(row, ['lastCheckedAt', 'last_checked_at', 'checkedAt', 'checked_at'])) ??
      asString(firstValue(healthSummary ?? {}, ['checkedAt', 'checked_at'])) ??
      null,
    sourceMode,
    legacyFallback,
    deprecated,
    activationMode,
    toolTotal: asNumber(firstValue(row, ['toolTotal', 'tool_total'])) ?? undefined,
    sourceTools,
  }
}

export function normalizeToolListResponse(payload: unknown): ToolListResponse {
  const items = extractItems(payload, 'tools')
    .map((item, index) => normalizeTool(item, index))
    .filter((item): item is Tool => item !== null)
  return {
    items,
    total: normalizeTotal(payload, items.length),
  }
}

export function normalizeToolDetailResponse(payload: unknown): Tool | null {
  const item = normalizeTool(payload, 0)
  if (item) return item
  const root = asObject(payload)
  if (!root) return null
  if ('item' in root) return normalizeTool(root.item, 0)
  return null
}

export function normalizeToolSourceListResponse(payload: unknown): ToolSourceListResponse {
  const items = extractItems(payload, 'sources')
    .map((item, index) => normalizeToolSource(item, index))
    .filter((item): item is ToolSource => item !== null)
  const root = asObject(payload)
  return {
    governanceSummary: asObject(firstValue(root ?? {}, ['governanceSummary', 'governance_summary'])),
    items,
    total: normalizeTotal(payload, items.length),
  }
}

export function normalizeToolSourceDetailResponse(payload: unknown): ToolSource | null {
  return normalizeToolSource(payload, 0)
}

export function useTools() {
  return useQuery({
    queryKey: queryKeys.tools.list,
    queryFn: async () => {
      const payload = await apiRequest<unknown>('/api/tools')
      return normalizeToolListResponse(payload)
    },
  })
}

export function useToolDetail(toolId: string | null) {
  return useQuery({
    queryKey: queryKeys.tools.detail(toolId),
    enabled: Boolean(toolId),
    queryFn: async () => {
      if (!toolId) return null
      const payload = await apiRequest<unknown>(`/api/tools/${encodeURIComponent(toolId)}`)
      return normalizeToolDetailResponse(payload)
    },
  })
}
