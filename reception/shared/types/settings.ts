export interface GeneralSettings {
  dashboardAutoRefresh: boolean
  showSystemStatus: boolean
}

export interface GeneralSettingsResponse {
  key: string
  updatedAt: string
  settings: GeneralSettings
}

export interface UpdateGeneralSettingsRequest extends GeneralSettings {}

export interface AgentApiProviderSettings {
  enabled: boolean
  baseUrl: string
  model: string
  organizationId: string
  projectId: string
  groupId: string
  endpointPath: string
  notes: string
  hasApiKey: boolean
  apiKeyMasked: string | null
}

export interface AgentApiSettings {
  providers: Record<string, AgentApiProviderSettings>
}

export interface AgentApiSettingsResponse {
  key: string
  updatedAt: string
  settings: AgentApiSettings
}

export interface UpdateAgentApiProviderSettingsRequest {
  enabled?: boolean
  baseUrl?: string
  model?: string
  organizationId?: string
  projectId?: string
  groupId?: string
  endpointPath?: string
  notes?: string
  apiKey?: string
  clearApiKey?: boolean
}

export interface UpdateAgentApiSettingsRequest {
  providers?: Record<string, UpdateAgentApiProviderSettingsRequest>
}

export interface TelegramChannelIntegrationSettings {
  enabled: boolean
  apiBaseUrl: string
  httpTimeoutSeconds: number
  tenantId: string | null
  tenantName: string | null
  hasBotToken: boolean
  botTokenMasked: string | null
  hasWebhookSecret: boolean
  webhookSecretMasked: string | null
}

export interface WeComChannelIntegrationSettings {
  enabled: boolean
  webhookSecretHeader: string
  webhookSecretQueryParam: string
  botWebhookBaseUrl: string
  httpTimeoutSeconds: number
  tenantId: string | null
  tenantName: string | null
  hasBotWebhookKey: boolean
  botWebhookKeyMasked: string | null
  hasWebhookSecret: boolean
  webhookSecretMasked: string | null
}

export interface FeishuChannelIntegrationSettings {
  enabled: boolean
  webhookSecretHeader: string
  webhookSecretQueryParam: string
  botWebhookBaseUrl: string
  httpTimeoutSeconds: number
  tenantId: string | null
  tenantName: string | null
  hasBotWebhookKey: boolean
  botWebhookKeyMasked: string | null
  hasWebhookSecret: boolean
  webhookSecretMasked: string | null
}

export interface DingTalkChannelIntegrationSettings {
  enabled: boolean
  apiBaseUrl: string
  httpTimeoutSeconds: number
  tenantId: string | null
  tenantName: string | null
  appId: string
  agentId: string
  clientId: string
  corpId: string
  webhookSecretHeader: string
  webhookSecretQueryParam: string
  hasClientSecret: boolean
  clientSecretMasked: string | null
  hasWebhookSecret: boolean
  webhookSecretMasked: string | null
}

export interface ChannelIntegrationSettings {
  telegram: TelegramChannelIntegrationSettings
  wecom: WeComChannelIntegrationSettings
  feishu: FeishuChannelIntegrationSettings
  dingtalk: DingTalkChannelIntegrationSettings
}

export interface ChannelIntegrationSettingsResponse {
  key: string
  updatedAt: string
  settings: ChannelIntegrationSettings
  wecomBindingState: WecomBindingStateResponse | null
}

export interface UpdateTelegramChannelIntegrationSettingsRequest {
  enabled?: boolean
  apiBaseUrl?: string
  httpTimeoutSeconds?: number
  tenantId?: string
  tenantName?: string
  botToken?: string
  clearBotToken?: boolean
  webhookSecret?: string
  clearWebhookSecret?: boolean
}

export interface UpdateWeComChannelIntegrationSettingsRequest {
  enabled?: boolean
  webhookSecretHeader?: string
  webhookSecretQueryParam?: string
  botWebhookBaseUrl?: string
  httpTimeoutSeconds?: number
  tenantId?: string
  tenantName?: string
  botWebhookKey?: string
  clearBotWebhookKey?: boolean
  webhookSecret?: string
  clearWebhookSecret?: boolean
}

export interface UpdateFeishuChannelIntegrationSettingsRequest {
  enabled?: boolean
  webhookSecretHeader?: string
  webhookSecretQueryParam?: string
  botWebhookBaseUrl?: string
  httpTimeoutSeconds?: number
  tenantId?: string
  tenantName?: string
  botWebhookKey?: string
  clearBotWebhookKey?: boolean
  webhookSecret?: string
  clearWebhookSecret?: boolean
}

export interface UpdateDingTalkChannelIntegrationSettingsRequest {
  enabled?: boolean
  apiBaseUrl?: string
  httpTimeoutSeconds?: number
  tenantId?: string
  tenantName?: string
  appId?: string
  agentId?: string
  clientId?: string
  corpId?: string
  clientSecret?: string
  clearClientSecret?: boolean
  webhookSecret?: string
  clearWebhookSecret?: boolean
  webhookSecretHeader?: string
  webhookSecretQueryParam?: string
}

export interface UpdateChannelIntegrationSettingsRequest {
  telegram?: UpdateTelegramChannelIntegrationSettingsRequest
  dingtalk?: UpdateDingTalkChannelIntegrationSettingsRequest
  wecom?: UpdateWeComChannelIntegrationSettingsRequest
  feishu?: UpdateFeishuChannelIntegrationSettingsRequest
}

export type WecomBindSessionStatus = 'pending' | 'bound' | 'expired' | 'cancelled'

export interface WecomChannelBinding {
  tenantId: string
  tenantName: string | null
  channel: string
  displayName: string
  externalAccount: string | null
  status: 'bound'
  boundAt: string
  updatedAt: string
}

export interface WecomBindSession {
  sessionId: string
  tenantId: string
  tenantName: string | null
  channel: string
  status: WecomBindSessionStatus
  bindPath: string
  qrCodeUrl: string | null
  scanStatus: string | null
  expiresAt: string
  createdAt: string
  updatedAt: string
  displayName: string | null
  externalAccount: string | null
}

export interface WecomBindingStateResponse {
  tenantId: string | null
  tenantName: string | null
  binding: WecomChannelBinding | null
  activeSession: WecomBindSession | null
}

export interface CreateWecomBindSessionRequest {
  tenantId: string
  tenantName?: string
}

export interface CreateWecomBindSessionResponse {
  ok: boolean
  message: string
  state: WecomBindingStateResponse
}

export interface DeleteWecomBindingResponse {
  ok: boolean
  message: string
  state: WecomBindingStateResponse
}

export interface PublicWecomBindSessionResponse {
  tenantId: string
  tenantName: string | null
  session: WecomBindSession
}

export interface ConfirmWecomBindSessionRequest {
  displayName: string
  externalAccount?: string
}

export interface ConfirmWecomBindSessionResponse {
  ok: boolean
  message: string
  binding: WecomChannelBinding
  session: WecomBindSession
}

export type CustomerAccessVerificationMode = "relaxed" | "strict"

export interface CustomerAccessTemplateField {
  key: string
  label: string
  required: boolean
}

export interface CustomerAccessTenantPolicy {
  tenantId: string
  tenantName: string | null
  verificationMode: CustomerAccessVerificationMode
  serviceCodes: string[]
  enabled: boolean
}

export interface CustomerAccessSettings {
  templateIntro: string
  templateFields: CustomerAccessTemplateField[]
  tenantPolicies: CustomerAccessTenantPolicy[]
  updatedAt: string | null
}

export interface CustomerAccessSettingsResponse {
  settings: CustomerAccessSettings
}

export interface CustomerAccessSettingsActionResponse {
  ok: boolean
  message: string
  settings: CustomerAccessSettings
}

export interface UpdateCustomerAccessTenantPolicyRequest {
  tenantId: string
  tenantName?: string
  verificationMode?: CustomerAccessVerificationMode
  serviceCodes?: string[]
  enabled?: boolean
}

export interface UpdateCustomerAccessSettingsRequest {
  templateIntro?: string
  tenantPolicies?: UpdateCustomerAccessTenantPolicyRequest[]
}

export type RuntimeMemoryMode = "platform_stateless"

export type MemoryNamespaceStrategy = "tenant" | "tenant_customer" | "tenant_session" | "tenant_task"

export interface ProtocolBinding {
  bindingId: string
  tenantId: string
  agentId: string
  protocolId: string
  protocolVersion: string
  targetProvider: string
  targetInstanceId: string | null
  targetBaseUrl: string | null
  runtimeMemoryMode: RuntimeMemoryMode
  memoryNamespaceStrategy: MemoryNamespaceStrategy
  enabled: boolean
  metadata: Record<string, unknown>
  createdAt: string | null
  updatedAt: string | null
}

export interface ProtocolBindingListResponse {
  items: ProtocolBinding[]
  total: number
}

export interface ProtocolBindingActionResponse {
  ok: boolean
  message: string
  binding: ProtocolBinding
}

export interface ProtocolBindingUpsertRequest {
  bindingId?: string
  tenantId: string
  agentId: string
  protocolId: string
  protocolVersion?: string
  targetProvider?: string
  targetInstanceId?: string
  targetBaseUrl?: string
  runtimeMemoryMode?: RuntimeMemoryMode
  memoryNamespaceStrategy?: MemoryNamespaceStrategy
  enabled?: boolean
  metadata?: Record<string, unknown>
}

export interface ProtocolBindingDeleteRequest {
  bindingId?: string
  tenantId?: string
  agentId?: string
}
