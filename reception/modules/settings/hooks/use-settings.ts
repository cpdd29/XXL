'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  AgentApiSettingsResponse,
  ChannelIntegrationSettingsResponse,
  ConfirmWecomBindSessionRequest,
  ConfirmWecomBindSessionResponse,
  CreateWecomBindSessionRequest,
  CreateWecomBindSessionResponse,
  CustomerAccessSettings,
  CustomerAccessSettingsActionResponse,
  CustomerAccessSettingsResponse,
  CustomerAccessTemplateField,
  CustomerAccessTenantPolicy,
  DeleteWecomBindingResponse,
  GeneralSettingsResponse,
  ProtocolBinding,
  ProtocolBindingActionResponse,
  ProtocolBindingDeleteRequest,
  ProtocolBindingListResponse,
  PublicWecomBindSessionResponse,
  ProtocolBindingUpsertRequest,
  UpdateAgentApiSettingsRequest,
  UpdateChannelIntegrationSettingsRequest,
  UpdateCustomerAccessSettingsRequest,
  UpdateGeneralSettingsRequest,
  WecomBindSession,
  WecomBindingStateResponse,
  WecomChannelBinding,
} from '@/shared/types'

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

function buildQueryString(params: Record<string, string | null | undefined>) {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    const normalized = typeof value === 'string' ? value.trim() : ''
    if (normalized) {
      searchParams.set(key, normalized)
    }
  })
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

function readBoolean(
  record: Record<string, unknown>,
  camelKey: string,
  snakeKey: string,
  fallback = false,
) {
  const value = record[camelKey] ?? record[snakeKey]
  return typeof value === 'boolean' ? value : fallback
}

function normalizeRuntimeMemoryMode(raw: unknown): ProtocolBinding['runtimeMemoryMode'] {
  const normalized = String(raw ?? '').trim().toLowerCase().replace(/-/g, '_')
  if (
    normalized === 'platform_stateless' ||
    normalized === 'platform_only' ||
    normalized === 'hermes_runtime_only' ||
    normalized === 'platform_plus_hermes_runtime'
  ) {
    return 'platform_stateless'
  }
  return 'platform_stateless'
}

function normalizeProtocolBinding(raw: unknown): ProtocolBinding {
  const record = readRecord(raw)
  const metadataValue = record.metadata
  const metadata =
    metadataValue && typeof metadataValue === 'object' && !Array.isArray(metadataValue)
      ? (metadataValue as Record<string, unknown>)
      : {}
  return {
    bindingId: readString(record, 'bindingId', 'binding_id'),
    tenantId: readString(record, 'tenantId', 'tenant_id'),
    agentId: readString(record, 'agentId', 'agent_id'),
    protocolId: readString(record, 'protocolId', 'protocol_id'),
    protocolVersion: readString(record, 'protocolVersion', 'protocol_version'),
    targetProvider: readString(record, 'targetProvider', 'target_provider'),
    targetInstanceId: readNullableString(record, 'targetInstanceId', 'target_instance_id'),
    targetBaseUrl: readNullableString(record, 'targetBaseUrl', 'target_base_url'),
    runtimeMemoryMode: normalizeRuntimeMemoryMode(
      record.runtimeMemoryMode ?? record.runtime_memory_mode,
    ),
    memoryNamespaceStrategy: readString(
      record,
      'memoryNamespaceStrategy',
      'memory_namespace_strategy',
    ) as ProtocolBinding['memoryNamespaceStrategy'],
    enabled: readBoolean(record, 'enabled', 'enabled', true),
    metadata,
    createdAt: readNullableString(record, 'createdAt', 'created_at'),
    updatedAt: readNullableString(record, 'updatedAt', 'updated_at'),
  }
}

function normalizeProtocolBindingListResponse(raw: unknown): ProtocolBindingListResponse {
  const record = readRecord(raw)
  const rawItems = Array.isArray(record.items) ? record.items : []
  const total = typeof record.total === 'number' ? record.total : rawItems.length
  return {
    items: rawItems.map(normalizeProtocolBinding),
    total,
  }
}

function normalizeProtocolBindingActionResponse(raw: unknown): ProtocolBindingActionResponse {
  const record = readRecord(raw)
  return {
    ok: readBoolean(record, 'ok', 'ok'),
    message: readString(record, 'message', 'message'),
    binding: normalizeProtocolBinding(record.binding),
  }
}

function normalizeWecomChannelBinding(raw: unknown): WecomChannelBinding {
  const record = readRecord(raw)
  return {
    tenantId: readString(record, 'tenantId', 'tenant_id'),
    tenantName: readNullableString(record, 'tenantName', 'tenant_name'),
    channel: readString(record, 'channel', 'channel'),
    displayName: readString(record, 'displayName', 'display_name'),
    externalAccount: readNullableString(record, 'externalAccount', 'external_account'),
    status: 'bound',
    boundAt: readString(record, 'boundAt', 'bound_at'),
    updatedAt: readString(record, 'updatedAt', 'updated_at'),
  }
}

function normalizeWecomBindSession(raw: unknown): WecomBindSession {
  const record = readRecord(raw)
  const rawStatus = readString(record, 'status', 'status')
  const status: WecomBindSession['status'] =
    rawStatus === 'bound' || rawStatus === 'expired' || rawStatus === 'cancelled'
      ? rawStatus
      : 'pending'
  return {
    sessionId: readString(record, 'sessionId', 'session_id'),
    tenantId: readString(record, 'tenantId', 'tenant_id'),
    tenantName: readNullableString(record, 'tenantName', 'tenant_name'),
    channel: readString(record, 'channel', 'channel') || 'wecom',
    status,
    bindPath: readString(record, 'bindPath', 'bind_path'),
    qrCodeUrl: readNullableString(record, 'qrCodeUrl', 'qr_code_url'),
    scanStatus: readNullableString(record, 'scanStatus', 'scan_status'),
    expiresAt: readString(record, 'expiresAt', 'expires_at'),
    createdAt: readString(record, 'createdAt', 'created_at'),
    updatedAt: readString(record, 'updatedAt', 'updated_at'),
    displayName: readNullableString(record, 'displayName', 'display_name'),
    externalAccount: readNullableString(record, 'externalAccount', 'external_account'),
  }
}

function normalizeWecomBindingStateResponse(raw: unknown): WecomBindingStateResponse {
  const record = readRecord(raw)
  return {
    tenantId: readNullableString(record, 'tenantId', 'tenant_id'),
    tenantName: readNullableString(record, 'tenantName', 'tenant_name'),
    binding: record.binding ? normalizeWecomChannelBinding(record.binding) : null,
    activeSession: record.activeSession ?? record.active_session
      ? normalizeWecomBindSession(record.activeSession ?? record.active_session)
      : null,
  }
}

function normalizeCreateWecomBindSessionResponse(raw: unknown): CreateWecomBindSessionResponse {
  const record = readRecord(raw)
  return {
    ok: readBoolean(record, 'ok', 'ok'),
    message: readString(record, 'message', 'message'),
    state: normalizeWecomBindingStateResponse(record.state),
  }
}

function normalizeDeleteWecomBindingResponse(raw: unknown): DeleteWecomBindingResponse {
  const record = readRecord(raw)
  return {
    ok: readBoolean(record, 'ok', 'ok'),
    message: readString(record, 'message', 'message'),
    state: normalizeWecomBindingStateResponse(record.state),
  }
}

function normalizePublicWecomBindSessionResponse(raw: unknown): PublicWecomBindSessionResponse {
  const record = readRecord(raw)
  return {
    tenantId: readString(record, 'tenantId', 'tenant_id'),
    tenantName: readNullableString(record, 'tenantName', 'tenant_name'),
    session: normalizeWecomBindSession(record.session),
  }
}

function normalizeConfirmWecomBindSessionResponse(raw: unknown): ConfirmWecomBindSessionResponse {
  const record = readRecord(raw)
  return {
    ok: readBoolean(record, 'ok', 'ok'),
    message: readString(record, 'message', 'message'),
    binding: normalizeWecomChannelBinding(record.binding),
    session: normalizeWecomBindSession(record.session),
  }
}

function normalizeTemplateField(raw: unknown): CustomerAccessTemplateField {
  const record = readRecord(raw)
  return {
    key: readString(record, 'key', 'key'),
    label: readString(record, 'label', 'label'),
    required: readBoolean(record, 'required', 'required', true),
  }
}

function normalizeTenantPolicy(raw: unknown): CustomerAccessTenantPolicy {
  const record = readRecord(raw)
  const rawCodes = record.serviceCodes ?? record.service_codes
  return {
    tenantId: readString(record, 'tenantId', 'tenant_id'),
    tenantName: readNullableString(record, 'tenantName', 'tenant_name'),
    verificationMode: readString(record, 'verificationMode', 'verification_mode') as CustomerAccessTenantPolicy['verificationMode'],
    serviceCodes: Array.isArray(rawCodes)
      ? rawCodes.filter((item): item is string => typeof item === 'string')
      : [],
    enabled: readBoolean(record, 'enabled', 'enabled', true),
  }
}

function normalizeCustomerAccessSettings(raw: unknown): CustomerAccessSettings {
  const record = readRecord(raw)
  const templateFieldsValue = record.templateFields ?? record.template_fields
  const tenantPoliciesValue = record.tenantPolicies ?? record.tenant_policies
  const rawFields = Array.isArray(templateFieldsValue) ? templateFieldsValue : []
  const rawPolicies = Array.isArray(tenantPoliciesValue) ? tenantPoliciesValue : []
  return {
    templateIntro: readString(record, 'templateIntro', 'template_intro'),
    templateFields: rawFields.map(normalizeTemplateField),
    tenantPolicies: rawPolicies.map(normalizeTenantPolicy),
    updatedAt: readNullableString(record, 'updatedAt', 'updated_at'),
  }
}

function normalizeCustomerAccessSettingsResponse(raw: unknown): CustomerAccessSettingsResponse {
  const record = readRecord(raw)
  return {
    settings: normalizeCustomerAccessSettings(record.settings),
  }
}

function normalizeCustomerAccessSettingsActionResponse(raw: unknown): CustomerAccessSettingsActionResponse {
  const record = readRecord(raw)
  return {
    ok: readBoolean(record, 'ok', 'ok'),
    message: readString(record, 'message', 'message'),
    settings: normalizeCustomerAccessSettings(record.settings),
  }
}

export function useGeneralSettings() {
  return useQuery({
    queryKey: queryKeys.settings.general,
    queryFn: () => apiRequest<GeneralSettingsResponse>('/api/settings/general'),
  })
}

export function useUpdateGeneralSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateGeneralSettingsRequest) =>
      apiRequest<GeneralSettingsResponse, UpdateGeneralSettingsRequest>('/api/settings/general', {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.general, response)
    },
  })
}

export function useAgentApiSettings() {
  return useQuery({
    queryKey: queryKeys.settings.agentApi,
    queryFn: () => apiRequest<AgentApiSettingsResponse>('/api/settings/agent-api'),
  })
}

export function useUpdateAgentApiSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateAgentApiSettingsRequest) =>
      apiRequest<AgentApiSettingsResponse, UpdateAgentApiSettingsRequest>('/api/settings/agent-api', {
        method: 'PUT',
        body: payload,
      }),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.agentApi, response)
    },
  })
}

export function useChannelIntegrationSettings() {
  return useQuery({
    queryKey: queryKeys.settings.channelIntegration,
    queryFn: () =>
      apiRequest<ChannelIntegrationSettingsResponse>('/api/settings/channel-integration'),
  })
}

export function useUpdateChannelIntegrationSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateChannelIntegrationSettingsRequest) =>
      apiRequest<ChannelIntegrationSettingsResponse, UpdateChannelIntegrationSettingsRequest>(
        '/api/settings/channel-integration',
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.channelIntegration, response)
    },
  })
}

export function useWecomBindingState(tenantId?: string, tenantName?: string) {
  return useQuery({
    queryKey: queryKeys.settings.wecomBindingState(tenantId),
    enabled: Boolean(tenantId?.trim()),
    queryFn: () =>
      apiRequest<unknown>(
        `/api/settings/channel-integration/wecom/binding-state${buildQueryString({
          tenant_id: tenantId,
          tenant_name: tenantName,
        })}`,
      ).then(normalizeWecomBindingStateResponse),
  })
}

export function useCreateWecomBindSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateWecomBindSessionRequest) =>
      apiRequest<unknown, CreateWecomBindSessionRequest>(
        '/api/settings/channel-integration/wecom/bind-sessions',
        {
          method: 'POST',
          body: payload,
        },
      ).then(normalizeCreateWecomBindSessionResponse),
    onSuccess: (response, variables) => {
      queryClient.setQueryData(
        queryKeys.settings.wecomBindingState(variables.tenantId),
        response.state,
      )
    },
  })
}

export function useDeleteWecomBinding() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: { tenantId: string; tenantName?: string }) =>
      apiRequest<unknown>(
        `/api/settings/channel-integration/wecom/binding-state${buildQueryString({
          tenant_id: payload.tenantId,
          tenant_name: payload.tenantName,
        })}`,
        {
          method: 'DELETE',
        },
      ).then(normalizeDeleteWecomBindingResponse),
    onSuccess: (response, variables) => {
      queryClient.setQueryData(
        queryKeys.settings.wecomBindingState(variables.tenantId),
        response.state,
      )
    },
  })
}

export function usePublicWecomBindSession(token?: string | null) {
  return useQuery({
    queryKey: queryKeys.settings.wecomPublicBindSession(token),
    enabled: Boolean(token && token.trim()),
    queryFn: () =>
      apiRequest<unknown>(`/api/channel-bind/wecom/${encodeURIComponent(token ?? '')}`).then(
        normalizePublicWecomBindSessionResponse,
      ),
  })
}

export function useConfirmWecomBindSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: { token: string; body: ConfirmWecomBindSessionRequest }) =>
      apiRequest<unknown, ConfirmWecomBindSessionRequest>(
        `/api/channel-bind/wecom/${encodeURIComponent(payload.token)}/confirm`,
        {
          method: 'POST',
          body: payload.body,
        },
      ).then(normalizeConfirmWecomBindSessionResponse),
    onSuccess: (_response, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.settings.wecomPublicBindSession(variables.token),
      })
    },
  })
}

export function useCustomerAccessSettings() {
  return useQuery({
    queryKey: queryKeys.settings.customerAccess,
    queryFn: () =>
      apiRequest<unknown>('/api/customer-access/settings').then(normalizeCustomerAccessSettingsResponse),
  })
}

export function useUpdateCustomerAccessSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateCustomerAccessSettingsRequest) =>
      apiRequest<unknown, UpdateCustomerAccessSettingsRequest>(
        '/api/customer-access/settings',
        {
          method: 'PUT',
          body: payload,
        },
      ).then(normalizeCustomerAccessSettingsActionResponse),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.settings.customerAccess, { settings: response.settings })
    },
  })
}

export function useProtocolBindings(params?: { tenantId?: string; agentId?: string }) {
  const tenantId = params?.tenantId?.trim() || undefined
  const agentId = params?.agentId?.trim() || undefined
  const query = new URLSearchParams()
  if (tenantId) query.set('tenantId', tenantId)
  if (agentId) query.set('agentId', agentId)
  const suffix = query.toString()

  return useQuery({
    queryKey: queryKeys.settings.protocolBindings({ tenantId, agentId }),
    queryFn: () =>
      apiRequest<unknown>(
        suffix ? `/api/protocol-bindings?${suffix}` : '/api/protocol-bindings',
      ).then(normalizeProtocolBindingListResponse),
  })
}

export function useUpsertProtocolBinding(params?: { tenantId?: string; agentId?: string }) {
  const queryClient = useQueryClient()
  const tenantId = params?.tenantId?.trim() || undefined
  const agentId = params?.agentId?.trim() || undefined

  return useMutation({
    mutationFn: (payload: ProtocolBindingUpsertRequest) =>
      apiRequest<unknown, ProtocolBindingUpsertRequest>('/api/protocol-bindings', {
        method: 'PUT',
        body: payload,
      }).then(normalizeProtocolBindingActionResponse),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.settings.protocolBindings({ tenantId, agentId }),
      })
    },
  })
}

export function useDeleteProtocolBinding(params?: { tenantId?: string; agentId?: string }) {
  const queryClient = useQueryClient()
  const tenantId = params?.tenantId?.trim() || undefined
  const agentId = params?.agentId?.trim() || undefined

  return useMutation({
    mutationFn: (payload: ProtocolBindingDeleteRequest) => {
      const query = new URLSearchParams()
      const normalizedBindingId = payload.bindingId?.trim()
      const normalizedTenantId = payload.tenantId?.trim()
      const normalizedAgentId = payload.agentId?.trim()
      if (normalizedBindingId) query.set('bindingId', normalizedBindingId)
      if (normalizedTenantId) query.set('tenantId', normalizedTenantId)
      if (normalizedAgentId) query.set('agentId', normalizedAgentId)
      const suffix = query.toString()
      return apiRequest<unknown>(
        suffix ? `/api/protocol-bindings?${suffix}` : '/api/protocol-bindings',
        {
          method: 'DELETE',
        },
      ).then(normalizeProtocolBindingActionResponse)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.settings.protocolBindings({ tenantId, agentId }),
      })
    },
  })
}
