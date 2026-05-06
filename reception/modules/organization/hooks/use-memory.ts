'use client'

import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type { LongTermMemoryItem, LongTermMemoryListResponse } from '@/shared/types'

export interface LongTermMemoryQueryParams {
  tenantId?: string
  subjectType?: string
  subjectId?: string
  memoryType?: string
  query?: string
  memoryScope?: string
  limit?: number
}

function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function readString(record: Record<string, unknown>, camelKey: string, snakeKey: string) {
  const value = record[camelKey] ?? record[snakeKey]
  return typeof value === 'string' ? value : ''
}

function readNullableString(record: Record<string, unknown>, camelKey: string, snakeKey: string) {
  const value = record[camelKey] ?? record[snakeKey]
  return typeof value === 'string' ? value : null
}

function readNumberOrNull(record: Record<string, unknown>, camelKey: string, snakeKey: string) {
  const value = record[camelKey] ?? record[snakeKey]
  return typeof value === 'number' ? value : null
}

function readStringArray(record: Record<string, unknown>, camelKey: string, snakeKey: string) {
  const value = record[camelKey] ?? record[snakeKey]
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

function normalizeMemoryItem(raw: unknown): LongTermMemoryItem {
  const record = readRecord(raw)
  return {
    id: readString(record, 'id', 'id'),
    userId: readString(record, 'userId', 'user_id'),
    sourceMidTermId: readString(record, 'sourceMidTermId', 'source_mid_term_id'),
    memoryType: readString(record, 'memoryType', 'memory_type'),
    subjectType: readNullableString(record, 'subjectType', 'subject_type'),
    subjectId: readNullableString(record, 'subjectId', 'subject_id'),
    title: readNullableString(record, 'title', 'title'),
    source: readNullableString(record, 'source', 'source'),
    importance: readNumberOrNull(record, 'importance', 'importance'),
    summary: readNullableString(record, 'summary', 'summary'),
    memoryText: readString(record, 'memoryText', 'memory_text'),
    keywords: readStringArray(record, 'keywords', 'keywords'),
    createdAt: readString(record, 'createdAt', 'created_at'),
    updatedAt: readNullableString(record, 'updatedAt', 'updated_at'),
    tenantId: readString(record, 'tenantId', 'tenant_id'),
    projectId: readString(record, 'projectId', 'project_id'),
    environment: readString(record, 'environment', 'environment'),
    memoryScope: readString(record, 'memoryScope', 'memory_scope'),
    memoryLayerKind: readString(record, 'memoryLayerKind', 'memory_layer_kind'),
    writeSource: readString(record, 'writeSource', 'write_source'),
    trustLevel: readString(record, 'trustLevel', 'trust_level'),
    memoryStatus: readString(record, 'memoryStatus', 'memory_status'),
    reviewStatus: readString(record, 'reviewStatus', 'review_status'),
  }
}

function normalizeLongTermMemoryListResponse(raw: unknown): LongTermMemoryListResponse {
  const record = readRecord(raw)
  const rawItems = Array.isArray(record.items) ? record.items : []
  const rawTotal = record.total
  const rawScopeBreakdown = record.scopeBreakdown ?? record.scope_breakdown

  const scopeBreakdown =
    rawScopeBreakdown && typeof rawScopeBreakdown === 'object' && !Array.isArray(rawScopeBreakdown)
      ? Object.fromEntries(
          Object.entries(rawScopeBreakdown as Record<string, unknown>).map(([key, value]) => [
            key,
            typeof value === 'number' ? value : 0,
          ]),
        )
      : {}

  return {
    items: rawItems.map(normalizeMemoryItem),
    total: typeof rawTotal === 'number' ? rawTotal : rawItems.length,
    scopeBreakdown,
  }
}

export function useLongTermMemories(params?: LongTermMemoryQueryParams) {
  const tenantId = params?.tenantId?.trim() || undefined
  const subjectType = params?.subjectType?.trim() || undefined
  const subjectId = params?.subjectId?.trim() || undefined
  const memoryType = params?.memoryType?.trim() || undefined
  const query = params?.query?.trim() || undefined
  const memoryScope = params?.memoryScope?.trim() || undefined
  const limit = params?.limit ?? 20

  return useQuery({
    queryKey: queryKeys.memory.longTerm({
      tenantId,
      subjectType,
      subjectId,
      memoryType,
      query,
      memoryScope,
      limit,
    }),
    queryFn: () => {
      const search = new URLSearchParams()
      if (tenantId) search.set('tenantId', tenantId)
      if (subjectType) search.set('subjectType', subjectType)
      if (subjectId) search.set('subjectId', subjectId)
      if (memoryType) search.set('memoryType', memoryType)
      if (query) search.set('query', query)
      if (memoryScope) search.set('memoryScope', memoryScope)
      search.set('limit', String(limit))
      return apiRequest<unknown>(`/api/memory/long-term?${search.toString()}`).then(
        normalizeLongTermMemoryListResponse,
      )
    },
  })
}
