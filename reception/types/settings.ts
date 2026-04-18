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

export interface ConfigGovernanceSummary {
  totalSections: number
  runtimeMutableSections: number
  deploymentImmutableSections: number
  warningCount: number
}

export interface ConfigReadPriorityModel {
  runtimeMutable: string[]
  deploymentImmutable: string[]
}

export interface ConfigGovernanceSection {
  key: string
  label: string
  category: string
  mutability: string
  effectiveSource: string
  readPriority: string[]
  updatedAt: string
  defaultsFrom: string
  current: Record<string, unknown>
  defaults: Record<string, unknown>
  warnings: string[]
  riskLevel: string
}

export interface ConfigChangeAuditItem {
  id: string
  timestamp: string
  action: string
  user: string
  resource: string
  details: string
  status: string
}

export interface ConfigGovernanceResponse {
  summary: ConfigGovernanceSummary
  readPriorityModel: ConfigReadPriorityModel
  sections: ConfigGovernanceSection[]
  recentChangeAudits: ConfigChangeAuditItem[]
}
