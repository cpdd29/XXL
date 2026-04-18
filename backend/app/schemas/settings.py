from app.schemas.base import APIModel


class GeneralSettings(APIModel):
    dashboard_auto_refresh: bool
    show_system_status: bool


class GeneralSettingsResponse(APIModel):
    key: str
    updated_at: str
    settings: GeneralSettings


class UpdateGeneralSettingsRequest(APIModel):
    dashboard_auto_refresh: bool | None = None
    show_system_status: bool | None = None


class SecurityPolicySettings(APIModel):
    message_rate_limit_per_minute: int
    message_rate_limit_cooldown_seconds: int
    message_rate_limit_ban_threshold: int
    message_rate_limit_ban_seconds: int
    security_incident_window_seconds: int
    prompt_rule_block_threshold: int
    prompt_classifier_block_threshold: int
    prompt_injection_enabled: bool
    content_redaction_enabled: bool


class SecurityPolicySettingsResponse(APIModel):
    key: str
    updated_at: str
    settings: SecurityPolicySettings


class UpdateSecurityPolicySettingsRequest(APIModel):
    message_rate_limit_per_minute: int | None = None
    message_rate_limit_cooldown_seconds: int | None = None
    message_rate_limit_ban_threshold: int | None = None
    message_rate_limit_ban_seconds: int | None = None
    security_incident_window_seconds: int | None = None
    prompt_rule_block_threshold: int | None = None
    prompt_classifier_block_threshold: int | None = None
    prompt_injection_enabled: bool | None = None
    content_redaction_enabled: bool | None = None
    approval_id: str | None = None
    approval_reason: str | None = None
    approval_note: str | None = None


class AgentApiProviderSettings(APIModel):
    enabled: bool
    base_url: str
    model: str
    organization_id: str
    project_id: str
    group_id: str
    endpoint_path: str
    notes: str
    has_api_key: bool
    api_key_masked: str | None = None


class AgentApiSettings(APIModel):
    providers: dict[str, AgentApiProviderSettings]


class AgentApiSettingsResponse(APIModel):
    key: str
    updated_at: str
    settings: AgentApiSettings


class UpdateAgentApiProviderSettingsRequest(APIModel):
    enabled: bool | None = None
    base_url: str | None = None
    model: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    group_id: str | None = None
    endpoint_path: str | None = None
    notes: str | None = None
    api_key: str | None = None
    clear_api_key: bool | None = None


class UpdateAgentApiSettingsRequest(APIModel):
    providers: dict[str, UpdateAgentApiProviderSettingsRequest] | None = None


class TelegramChannelIntegrationSettings(APIModel):
    enabled: bool
    api_base_url: str
    http_timeout_seconds: float
    tenant_id: str | None = None
    tenant_name: str | None = None
    has_bot_token: bool
    bot_token_masked: str | None = None
    has_webhook_secret: bool
    webhook_secret_masked: str | None = None


class WeComChannelIntegrationSettings(APIModel):
    enabled: bool
    webhook_secret_header: str
    webhook_secret_query_param: str
    bot_webhook_base_url: str
    http_timeout_seconds: float
    tenant_id: str | None = None
    tenant_name: str | None = None
    has_bot_webhook_key: bool
    bot_webhook_key_masked: str | None = None
    has_webhook_secret: bool
    webhook_secret_masked: str | None = None


class FeishuChannelIntegrationSettings(APIModel):
    enabled: bool
    webhook_secret_header: str
    webhook_secret_query_param: str
    bot_webhook_base_url: str
    http_timeout_seconds: float
    tenant_id: str | None = None
    tenant_name: str | None = None
    has_bot_webhook_key: bool
    bot_webhook_key_masked: str | None = None
    has_webhook_secret: bool
    webhook_secret_masked: str | None = None


class DingTalkChannelIntegrationSettings(APIModel):
    enabled: bool
    app_id: str
    agent_id: str
    client_id: str
    corp_id: str
    api_base_url: str
    http_timeout_seconds: float
    webhook_secret_header: str
    webhook_secret_query_param: str
    tenant_id: str | None = None
    tenant_name: str | None = None
    has_client_secret: bool
    client_secret_masked: str | None = None
    has_webhook_secret: bool
    webhook_secret_masked: str | None = None


class ChannelIntegrationSettings(APIModel):
    telegram: TelegramChannelIntegrationSettings
    wecom: WeComChannelIntegrationSettings
    feishu: FeishuChannelIntegrationSettings
    dingtalk: DingTalkChannelIntegrationSettings


class ChannelIntegrationSettingsResponse(APIModel):
    key: str
    updated_at: str
    settings: ChannelIntegrationSettings


class UpdateTelegramChannelIntegrationSettingsRequest(APIModel):
    enabled: bool | None = None
    api_base_url: str | None = None
    http_timeout_seconds: float | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    bot_token: str | None = None
    clear_bot_token: bool | None = None
    webhook_secret: str | None = None
    clear_webhook_secret: bool | None = None


class UpdateWeComChannelIntegrationSettingsRequest(APIModel):
    enabled: bool | None = None
    webhook_secret_header: str | None = None
    webhook_secret_query_param: str | None = None
    bot_webhook_base_url: str | None = None
    http_timeout_seconds: float | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    bot_webhook_key: str | None = None
    clear_bot_webhook_key: bool | None = None
    webhook_secret: str | None = None
    clear_webhook_secret: bool | None = None


class UpdateFeishuChannelIntegrationSettingsRequest(APIModel):
    enabled: bool | None = None
    webhook_secret_header: str | None = None
    webhook_secret_query_param: str | None = None
    bot_webhook_base_url: str | None = None
    http_timeout_seconds: float | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    bot_webhook_key: str | None = None
    clear_bot_webhook_key: bool | None = None
    webhook_secret: str | None = None
    clear_webhook_secret: bool | None = None


class UpdateDingTalkChannelIntegrationSettingsRequest(APIModel):
    enabled: bool | None = None
    app_id: str | None = None
    agent_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    clear_client_secret: bool | None = None
    corp_id: str | None = None
    api_base_url: str | None = None
    http_timeout_seconds: float | None = None
    webhook_secret_header: str | None = None
    webhook_secret_query_param: str | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    webhook_secret: str | None = None
    clear_webhook_secret: bool | None = None


class UpdateChannelIntegrationSettingsRequest(APIModel):
    telegram: UpdateTelegramChannelIntegrationSettingsRequest | None = None
    wecom: UpdateWeComChannelIntegrationSettingsRequest | None = None
    feishu: UpdateFeishuChannelIntegrationSettingsRequest | None = None
    dingtalk: UpdateDingTalkChannelIntegrationSettingsRequest | None = None


class ConfigGovernanceSummary(APIModel):
    total_sections: int
    runtime_mutable_sections: int
    deployment_immutable_sections: int
    warning_count: int


class ConfigReadPriorityModel(APIModel):
    runtime_mutable: list[str]
    deployment_immutable: list[str]


class ConfigGovernanceSection(APIModel):
    key: str
    label: str
    category: str
    mutability: str
    effective_source: str
    read_priority: list[str]
    updated_at: str
    defaults_from: str
    current: dict[str, object]
    defaults: dict[str, object]
    warnings: list[str]
    risk_level: str


class ConfigChangeAuditItem(APIModel):
    id: str
    timestamp: str
    action: str
    user: str
    resource: str
    details: str
    status: str


class ConfigGovernanceResponse(APIModel):
    summary: ConfigGovernanceSummary
    read_priority_model: ConfigReadPriorityModel
    sections: list[ConfigGovernanceSection]
    recent_change_audits: list[ConfigChangeAuditItem]
