"use client"

import type { ReactNode } from "react"
import { useEffect, useMemo, useState } from "react"
import { RadioTower, Send, ShieldCheck, Webhook } from "lucide-react"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Switch } from "@/shared/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import { useAuth } from "@/modules/auth/hooks/use-auth"
import {
  useChannelIntegrationSettings,
  useUpdateChannelIntegrationSettings,
} from "@/modules/settings/hooks/use-settings"
import { useManagedUserTenants } from "@/modules/organization/hooks/use-users"
import { toast } from "@/shared/hooks/use-toast"
import type {
  ChannelIntegrationSettings,
  UpdateChannelIntegrationSettingsRequest,
  UpdateDingTalkChannelIntegrationSettingsRequest,
  UpdateFeishuChannelIntegrationSettingsRequest,
  UpdateTelegramChannelIntegrationSettingsRequest,
  UpdateWeComChannelIntegrationSettingsRequest,
  UserTenantOption,
} from "@/shared/types"

type ChannelKey = keyof ChannelIntegrationSettings

const UNBOUND_TENANT_VALUE = "__channel-unbound__"

type TenantBindingDraft = {
  tenantId: string
  tenantName: string
}

type TelegramDraft = TenantBindingDraft & {
  enabled: boolean
  apiBaseUrl: string
  httpTimeoutSeconds: number
  botToken: string
  clearBotToken: boolean
  webhookSecret: string
  clearWebhookSecret: boolean
}

type DingTalkDraft = TenantBindingDraft & {
  enabled: boolean
  apiBaseUrl: string
  httpTimeoutSeconds: number
  appId: string
  agentId: string
  clientId: string
  corpId: string
  clientSecret: string
  clearClientSecret: boolean
  webhookSecretHeader: string
  webhookSecretQueryParam: string
  webhookSecret: string
  clearWebhookSecret: boolean
}

type WebhookBotDraft = TenantBindingDraft & {
  enabled: boolean
  webhookSecretHeader: string
  webhookSecretQueryParam: string
  botWebhookBaseUrl: string
  httpTimeoutSeconds: number
  botWebhookKey: string
  clearBotWebhookKey: boolean
  webhookSecret: string
  clearWebhookSecret: boolean
}

type ChannelDraft = {
  telegram: TelegramDraft
  dingtalk: DingTalkDraft
  wecom: WebhookBotDraft
  feishu: WebhookBotDraft
}

const defaultSettings: ChannelIntegrationSettings = {
  telegram: {
    enabled: true,
    apiBaseUrl: "https://api.telegram.org",
    httpTimeoutSeconds: 10,
    tenantId: null,
    tenantName: null,
    hasBotToken: false,
    botTokenMasked: null,
    hasWebhookSecret: false,
    webhookSecretMasked: null,
  },
  dingtalk: {
    enabled: true,
    apiBaseUrl: "https://oapi.dingtalk.com",
    httpTimeoutSeconds: 10,
    tenantId: null,
    tenantName: null,
    appId: "",
    agentId: "",
    clientId: "",
    corpId: "",
    webhookSecretHeader: "X-WorkBot-Webhook-Secret",
    webhookSecretQueryParam: "token",
    hasClientSecret: false,
    clientSecretMasked: null,
    hasWebhookSecret: false,
    webhookSecretMasked: null,
  },
  wecom: {
    enabled: true,
    webhookSecretHeader: "X-WorkBot-Webhook-Secret",
    webhookSecretQueryParam: "token",
    botWebhookBaseUrl: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
    httpTimeoutSeconds: 10,
    tenantId: null,
    tenantName: null,
    hasBotWebhookKey: false,
    botWebhookKeyMasked: null,
    hasWebhookSecret: false,
    webhookSecretMasked: null,
  },
  feishu: {
    enabled: true,
    webhookSecretHeader: "X-WorkBot-Webhook-Secret",
    webhookSecretQueryParam: "token",
    botWebhookBaseUrl: "https://open.feishu.cn/open-apis/bot/v2/hook",
    httpTimeoutSeconds: 10,
    tenantId: null,
    tenantName: null,
    hasBotWebhookKey: false,
    botWebhookKeyMasked: null,
    hasWebhookSecret: false,
    webhookSecretMasked: null,
  },
}

const channelMeta: Array<{
  key: ChannelKey
  label: string
  route: string
  modeLabel: string
  icon: typeof Send
  supportsBotToken: boolean
  supportsBotWebhookKey: boolean
  supportsBotWebhookBaseUrl: boolean
}> = [
  {
    key: "telegram",
    label: "Telegram",
    route: "/api/webhooks/telegram",
    modeLabel: "Bot Token 模式",
    icon: Send,
    supportsBotToken: true,
    supportsBotWebhookKey: false,
    supportsBotWebhookBaseUrl: false,
  },
  {
    key: "dingtalk",
    label: "DingTalk",
    route: "/api/webhooks/dingtalk",
    modeLabel: "应用机器人模式",
    icon: RadioTower,
    supportsBotToken: false,
    supportsBotWebhookKey: false,
    supportsBotWebhookBaseUrl: false,
  },
  {
    key: "wecom",
    label: "WeCom",
    route: "/api/webhooks/wecom",
    modeLabel: "Webhook 机器人模式",
    icon: Webhook,
    supportsBotToken: false,
    supportsBotWebhookKey: true,
    supportsBotWebhookBaseUrl: true,
  },
  {
    key: "feishu",
    label: "Feishu",
    route: "/api/webhooks/feishu",
    modeLabel: "Webhook 机器人模式",
    icon: ShieldCheck,
    supportsBotToken: false,
    supportsBotWebhookKey: true,
    supportsBotWebhookBaseUrl: true,
  },
]

function toDraft(settings?: ChannelIntegrationSettings): ChannelDraft {
  const source = settings ?? defaultSettings
  return {
    telegram: {
      enabled: source.telegram.enabled,
      apiBaseUrl: source.telegram.apiBaseUrl,
      httpTimeoutSeconds: source.telegram.httpTimeoutSeconds,
      tenantId: source.telegram.tenantId ?? "",
      tenantName: source.telegram.tenantName ?? "",
      botToken: "",
      clearBotToken: false,
      webhookSecret: "",
      clearWebhookSecret: false,
    },
    dingtalk: {
      enabled: source.dingtalk.enabled,
      apiBaseUrl: source.dingtalk.apiBaseUrl,
      httpTimeoutSeconds: source.dingtalk.httpTimeoutSeconds,
      tenantId: source.dingtalk.tenantId ?? "",
      tenantName: source.dingtalk.tenantName ?? "",
      appId: source.dingtalk.appId,
      agentId: source.dingtalk.agentId,
      clientId: source.dingtalk.clientId,
      corpId: source.dingtalk.corpId,
      clientSecret: "",
      clearClientSecret: false,
      webhookSecretHeader: source.dingtalk.webhookSecretHeader,
      webhookSecretQueryParam: source.dingtalk.webhookSecretQueryParam,
      webhookSecret: "",
      clearWebhookSecret: false,
    },
    wecom: {
      enabled: source.wecom.enabled,
      webhookSecretHeader: source.wecom.webhookSecretHeader,
      webhookSecretQueryParam: source.wecom.webhookSecretQueryParam,
      botWebhookBaseUrl: source.wecom.botWebhookBaseUrl,
      httpTimeoutSeconds: source.wecom.httpTimeoutSeconds,
      tenantId: source.wecom.tenantId ?? "",
      tenantName: source.wecom.tenantName ?? "",
      botWebhookKey: "",
      clearBotWebhookKey: false,
      webhookSecret: "",
      clearWebhookSecret: false,
    },
    feishu: {
      enabled: source.feishu.enabled,
      webhookSecretHeader: source.feishu.webhookSecretHeader,
      webhookSecretQueryParam: source.feishu.webhookSecretQueryParam,
      botWebhookBaseUrl: source.feishu.botWebhookBaseUrl,
      httpTimeoutSeconds: source.feishu.httpTimeoutSeconds,
      tenantId: source.feishu.tenantId ?? "",
      tenantName: source.feishu.tenantName ?? "",
      botWebhookKey: "",
      clearBotWebhookKey: false,
      webhookSecret: "",
      clearWebhookSecret: false,
    },
  }
}

function buildTenantBindingPayload(draft: TenantBindingDraft) {
  const tenantId = draft.tenantId.trim()
  const tenantName = draft.tenantName.trim()

  return {
    tenantId,
    tenantName: tenantId ? tenantName : "",
  }
}

function buildTenantOptions(
  tenants: UserTenantOption[],
  binding: TenantBindingDraft,
): UserTenantOption[] {
  if (!binding.tenantId.trim()) {
    return tenants
  }

  const alreadyExists = tenants.some((tenant) => tenant.id === binding.tenantId)
  if (alreadyExists) {
    return tenants
  }

  return [
    {
      id: binding.tenantId,
      name: binding.tenantName.trim() || binding.tenantId,
      status: "active",
      profileCount: 0,
      description: "当前已绑定租户未出现在可选列表中",
    },
    ...tenants,
  ]
}

function buildTelegramPayload(draft: TelegramDraft): UpdateTelegramChannelIntegrationSettingsRequest {
  const payload: UpdateTelegramChannelIntegrationSettingsRequest = {
    enabled: draft.enabled,
    apiBaseUrl: draft.apiBaseUrl,
    httpTimeoutSeconds: draft.httpTimeoutSeconds,
    ...buildTenantBindingPayload(draft),
  }
  if (draft.botToken.trim()) {
    payload.botToken = draft.botToken.trim()
  }
  if (draft.clearBotToken) {
    payload.clearBotToken = true
  }
  if (draft.webhookSecret.trim()) {
    payload.webhookSecret = draft.webhookSecret.trim()
  }
  if (draft.clearWebhookSecret) {
    payload.clearWebhookSecret = true
  }
  return payload
}

function buildDingTalkPayload(draft: DingTalkDraft): UpdateDingTalkChannelIntegrationSettingsRequest {
  const payload: UpdateDingTalkChannelIntegrationSettingsRequest = {
    enabled: draft.enabled,
    apiBaseUrl: draft.apiBaseUrl.trim(),
    httpTimeoutSeconds: draft.httpTimeoutSeconds,
    ...buildTenantBindingPayload(draft),
    appId: draft.appId.trim(),
    agentId: draft.agentId.trim(),
    clientId: draft.clientId.trim(),
    corpId: draft.corpId.trim(),
    webhookSecretHeader: draft.webhookSecretHeader.trim(),
    webhookSecretQueryParam: draft.webhookSecretQueryParam.trim(),
  }
  if (draft.clientSecret.trim()) {
    payload.clientSecret = draft.clientSecret.trim()
  }
  if (draft.clearClientSecret) {
    payload.clearClientSecret = true
  }
  if (draft.webhookSecret.trim()) {
    payload.webhookSecret = draft.webhookSecret.trim()
  }
  if (draft.clearWebhookSecret) {
    payload.clearWebhookSecret = true
  }
  return payload
}

function buildWebhookBotPayload(
  draft: WebhookBotDraft,
): UpdateWeComChannelIntegrationSettingsRequest | UpdateFeishuChannelIntegrationSettingsRequest {
  const payload = {
    enabled: draft.enabled,
    webhookSecretHeader: draft.webhookSecretHeader,
    webhookSecretQueryParam: draft.webhookSecretQueryParam,
    botWebhookBaseUrl: draft.botWebhookBaseUrl,
    httpTimeoutSeconds: draft.httpTimeoutSeconds,
    ...buildTenantBindingPayload(draft),
  }
  const nextPayload:
    | UpdateWeComChannelIntegrationSettingsRequest
    | UpdateFeishuChannelIntegrationSettingsRequest = { ...payload }
  if (draft.botWebhookKey.trim()) {
    nextPayload.botWebhookKey = draft.botWebhookKey.trim()
  }
  if (draft.clearBotWebhookKey) {
    nextPayload.clearBotWebhookKey = true
  }
  if (draft.webhookSecret.trim()) {
    nextPayload.webhookSecret = draft.webhookSecret.trim()
  }
  if (draft.clearWebhookSecret) {
    nextPayload.clearWebhookSecret = true
  }
  return nextPayload
}

function buildUpdatePayload(draft: ChannelDraft): UpdateChannelIntegrationSettingsRequest {
  return {
    telegram: buildTelegramPayload(draft.telegram),
    dingtalk: buildDingTalkPayload(draft.dingtalk),
    wecom: buildWebhookBotPayload(draft.wecom),
    feishu: buildWebhookBotPayload(draft.feishu),
  }
}

function buildSecretHint(config: {
  value: string
  clear: boolean
  hasSaved: boolean
  masked: string | null
  emptyText: string
  savingText: string
  clearingText: string
}): string {
  if (config.clear) {
    return config.clearingText
  }
  if (config.value.trim()) {
    return config.savingText
  }
  if (config.hasSaved) {
    return `当前已保存：${config.masked ?? "已配置"}`
  }
  return config.emptyText
}

function buildChannelPayload(channel: ChannelKey, draft: ChannelDraft[ChannelKey]) {
  switch (channel) {
    case "telegram":
      return buildTelegramPayload(draft as TelegramDraft)
    case "dingtalk":
      return buildDingTalkPayload(draft as DingTalkDraft)
    case "wecom":
    case "feishu":
      return buildWebhookBotPayload(draft as WebhookBotDraft)
  }
}

function isChannelDirty(channel: ChannelKey, draft: ChannelDraft, savedDraft: ChannelDraft) {
  return (
    JSON.stringify(buildChannelPayload(channel, draft[channel])) !==
    JSON.stringify(buildChannelPayload(channel, savedDraft[channel]))
  )
}

function countSavedCredentials(
  channel: ChannelKey,
  settings: ChannelIntegrationSettings[ChannelKey],
): number {
  switch (channel) {
    case "telegram": {
      const telegramSettings = settings as ChannelIntegrationSettings["telegram"]
      return Number(telegramSettings.hasBotToken) + Number(telegramSettings.hasWebhookSecret)
    }
    case "dingtalk": {
      const dingtalkSettings = settings as ChannelIntegrationSettings["dingtalk"]
      return Number(dingtalkSettings.hasClientSecret) + Number(dingtalkSettings.hasWebhookSecret)
    }
    case "wecom":
    case "feishu": {
      const webhookSettings = settings as
        | ChannelIntegrationSettings["wecom"]
        | ChannelIntegrationSettings["feishu"]
      return Number(webhookSettings.hasBotWebhookKey) + Number(webhookSettings.hasWebhookSecret)
    }
  }
}

function buildCredentialSummary(channel: ChannelKey, settings: ChannelIntegrationSettings[ChannelKey]) {
  const savedCredentialCount = countSavedCredentials(channel, settings)
  return savedCredentialCount > 0 ? `${savedCredentialCount} 项密钥已保存` : "待录入凭据"
}

export default function ChannelIntegrationSettingsPage() {
  const { hasPermission } = useAuth()
  const { data, isFetching, error, refetch } = useChannelIntegrationSettings()
  const {
    data: tenantOptionsData,
    isLoading: isTenantsLoading,
    error: tenantOptionsError,
  } = useManagedUserTenants()
  const updateChannelIntegrationSettings = useUpdateChannelIntegrationSettings()
  const savedSettings = data?.settings ?? defaultSettings
  const managedTenants = tenantOptionsData?.items ?? []
  const savedDraft = useMemo(() => toDraft(savedSettings), [savedSettings])
  const [draft, setDraft] = useState<ChannelDraft>(savedDraft)
  const [activeChannel, setActiveChannel] = useState<ChannelKey>(channelMeta[0]?.key ?? "telegram")

  useEffect(() => {
    setDraft(savedDraft)
  }, [savedDraft])

  const hasLoadedSettings = Boolean(data?.settings)
  const isSaving = updateChannelIntegrationSettings.isPending
  const canEditSettings = hasPermission("settings:channel-integrations:write")
  const isDirty = useMemo(
    () => JSON.stringify(buildUpdatePayload(draft)) !== JSON.stringify(buildUpdatePayload(savedDraft)),
    [draft, savedDraft],
  )
  const currentChannelMeta = channelMeta.find((channel) => channel.key === activeChannel) ?? channelMeta[0]!
  const currentSettings = draft[currentChannelMeta.key]
  const currentSavedProvider = savedSettings[currentChannelMeta.key]
  const currentTenantSummary =
    currentSettings.tenantName.trim() || currentSettings.tenantId.trim() || "未绑定租户"
  const currentCredentialSummary = buildCredentialSummary(currentChannelMeta.key, currentSavedProvider)
  const currentChannelDirty = isChannelDirty(currentChannelMeta.key, draft, savedDraft)
  const CurrentIcon = currentChannelMeta.icon

  const updateChannel = <K extends ChannelKey>(channel: K, patch: Partial<ChannelDraft[K]>) => {
    setDraft((current) => ({
      ...current,
      [channel]: {
        ...current[channel],
        ...patch,
      },
    }))
  }

  const handleTenantBindingChange = (channel: ChannelKey, value: string) => {
    const selectedTenant = managedTenants.find((tenant) => tenant.id === value)
    const tenantPatch =
      value === UNBOUND_TENANT_VALUE
        ? {
            tenantId: "",
            tenantName: "",
          }
        : {
            tenantId: value,
            tenantName: selectedTenant?.name ?? "",
          }

    setDraft((current) => ({
      ...current,
      [channel]: {
        ...current[channel],
        ...tenantPatch,
      },
    }))
  }

  const handleSave = async () => {
    try {
      const response = await updateChannelIntegrationSettings.mutateAsync(buildUpdatePayload(draft))
      setDraft(toDraft(response.settings))
      toast({
        title: "渠道接入配置已保存",
        description: "新的渠道接入项已经写入后端配置中心。",
      })
    } catch (saveError) {
      toast({
        title: "保存失败",
        description: saveError instanceof Error ? saveError.message : "未知错误",
      })
    }
  }

  const resetToSaved = () => {
    setDraft(savedDraft)
  }

  const renderSecretFieldHeader = (config: {
    id: string
    label: string
    hint: string
    action?: ReactNode
  }) => (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <Label htmlFor={config.id}>{config.label}</Label>
        <span className="text-xs text-muted-foreground">{config.hint}</span>
      </div>
      {config.action}
    </div>
  )

  const renderChannelSections = (channel: (typeof channelMeta)[number]) => {
    const settings = draft[channel.key]
    const savedProvider = savedSettings[channel.key]
    const tenantOptions = buildTenantOptions(managedTenants, settings)
    const tenantSelectValue = settings.tenantId.trim() || UNBOUND_TENANT_VALUE
    const selectedTenantLabel = settings.tenantName.trim() || settings.tenantId.trim() || "未绑定租户"
    const showTenantLoadingState = isTenantsLoading && tenantOptions.length === 0

    return (
      <>
        <section className="space-y-4 rounded-xl border border-border/60 bg-background/60 p-4">
          <h2 className="text-sm font-semibold text-foreground">基础接入</h2>

          <div className="space-y-2">
            <Label htmlFor={`${channel.key}-route`}>Webhook 路径</Label>
            <Input id={`${channel.key}-route`} readOnly value={channel.route} />
          </div>

          <div className="space-y-2">
            <Label htmlFor={`${channel.key}-tenant-binding`}>绑定租户</Label>
            <Select
              value={tenantSelectValue}
              onValueChange={(value) => handleTenantBindingChange(channel.key, value)}
              disabled={!canEditSettings || !hasLoadedSettings || isSaving || showTenantLoadingState}
            >
              <SelectTrigger id={`${channel.key}-tenant-binding`} className="bg-background">
                <SelectValue placeholder="选择已创建租户" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNBOUND_TENANT_VALUE}>不绑定租户</SelectItem>
                {tenantOptions.map((tenant) => (
                  <SelectItem key={tenant.id} value={tenant.id}>
                    {tenant.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {showTenantLoadingState
                ? "正在加载可绑定租户..."
                : tenantOptions.length > 0
                  ? `当前绑定：${selectedTenantLabel}`
                  : "暂无可绑定租户，可先在租户设置中创建。"}
            </p>
            {tenantOptionsError ? (
              <p className="text-xs text-destructive">
                租户列表加载失败：{tenantOptionsError instanceof Error ? tenantOptionsError.message : "未知错误"}
              </p>
            ) : null}
          </div>

          {"apiBaseUrl" in settings ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`${channel.key}-api-base-url`}>API Base URL</Label>
                <Input
                  id={`${channel.key}-api-base-url`}
                  value={settings.apiBaseUrl}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) =>
                    updateChannel(channel.key, { apiBaseUrl: event.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`${channel.key}-http-timeout`}>HTTP Timeout</Label>
                <Input
                  id={`${channel.key}-http-timeout`}
                  type="number"
                  min={1}
                  step={1}
                  value={settings.httpTimeoutSeconds}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) =>
                    updateChannel(channel.key, {
                      httpTimeoutSeconds: Number(event.target.value) || 1,
                    })
                  }
                />
              </div>
            </div>
          ) : null}

          {channel.supportsBotWebhookBaseUrl && "botWebhookBaseUrl" in settings ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`${channel.key}-bot-webhook-base-url`}>Bot Webhook Base URL</Label>
                <Input
                  id={`${channel.key}-bot-webhook-base-url`}
                  value={settings.botWebhookBaseUrl}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) =>
                    updateChannel(channel.key, { botWebhookBaseUrl: event.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`${channel.key}-bot-http-timeout`}>HTTP Timeout</Label>
                <Input
                  id={`${channel.key}-bot-http-timeout`}
                  type="number"
                  min={1}
                  step={1}
                  value={settings.httpTimeoutSeconds}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) =>
                    updateChannel(channel.key, {
                      httpTimeoutSeconds: Number(event.target.value) || 1,
                    })
                  }
                />
              </div>
            </div>
          ) : null}
        </section>

          {channel.key === "dingtalk" && "appId" in settings && "hasClientSecret" in savedProvider ? (
            <section className="space-y-4 rounded-xl border border-border/60 bg-background/60 p-4">
              <h2 className="text-sm font-semibold text-foreground">钉钉应用参数</h2>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`${channel.key}-app-id`}>App ID</Label>
                  <Input
                    id={`${channel.key}-app-id`}
                    value={settings.appId}
                    disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                    placeholder="钉钉应用 App ID"
                    onChange={(event) =>
                      updateChannel(channel.key, { appId: event.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`${channel.key}-client-id`}>Client ID</Label>
                  <Input
                    id={`${channel.key}-client-id`}
                    value={settings.clientId}
                    disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                    placeholder="应用 clientId"
                    onChange={(event) =>
                      updateChannel(channel.key, { clientId: event.target.value })
                    }
                  />
                </div>
              </div>

              <div className="space-y-2">
                {renderSecretFieldHeader({
                  id: `${channel.key}-client-secret`,
                  label: "Client Secret",
                  hint: buildSecretHint({
                    value: settings.clientSecret,
                    clear: settings.clearClientSecret,
                    hasSaved: savedProvider.hasClientSecret,
                    masked: savedProvider.clientSecretMasked,
                    emptyText: "当前未保存 client secret。",
                    savingText: "已录入新的 client secret，保存后会替换当前配置。",
                    clearingText: "当前保存的 client secret 将在下次保存时清空。",
                  }),
                  action: savedProvider.hasClientSecret ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                      onClick={() =>
                        updateChannel(channel.key, {
                          clientSecret: "",
                          clearClientSecret: !settings.clearClientSecret,
                        })
                      }
                    >
                      {settings.clearClientSecret ? "保留现有 Secret" : "清空已保存 Secret"}
                    </Button>
                  ) : undefined,
                })}
                <Input
                  id={`${channel.key}-client-secret`}
                  type="password"
                  autoComplete="off"
                  value={settings.clientSecret}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  placeholder="留空表示保留当前 Secret，输入则替换"
                  onChange={(event) =>
                    updateChannel(channel.key, {
                      clientSecret: event.target.value,
                      clearClientSecret: false,
                    })
                  }
                />
              </div>
            </section>
          ) : null}

          {channel.key !== "dingtalk" ? (
          <section className="space-y-4 rounded-xl border border-border/60 bg-background/60 p-4">
            <h2 className="text-sm font-semibold text-foreground">安全与鉴权</h2>

            {channel.key === "telegram" && "botToken" in settings ? (
              <div className="space-y-2">
                {renderSecretFieldHeader({
                  id: `${channel.key}-bot-token`,
                  label: "Bot Token",
                  hint: buildSecretHint({
                    value: settings.botToken,
                    clear: settings.clearBotToken,
                    hasSaved: savedSettings.telegram.hasBotToken,
                    masked: savedSettings.telegram.botTokenMasked,
                    emptyText: "当前未保存 Bot Token。",
                    savingText: "已录入新的 Bot Token，保存后会替换当前配置。",
                    clearingText: "当前保存的 Bot Token 将在下次保存时清空。",
                  }),
                  action: savedSettings.telegram.hasBotToken ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                      onClick={() =>
                        updateChannel(channel.key, {
                          botToken: "",
                          clearBotToken: !settings.clearBotToken,
                        })
                      }
                    >
                      {settings.clearBotToken ? "保留现有 Token" : "清空已保存 Token"}
                    </Button>
                  ) : undefined,
                })}
                <Input
                  id={`${channel.key}-bot-token`}
                  type="password"
                  autoComplete="off"
                  value={settings.botToken}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  placeholder="留空表示保留当前 Token，输入则替换"
                  onChange={(event) =>
                    updateChannel(channel.key, {
                      botToken: event.target.value,
                      clearBotToken: false,
                    })
                  }
                />
              </div>
            ) : null}

            {"webhookSecret" in settings && "hasWebhookSecret" in savedProvider ? (
              <div className="space-y-2">
                {renderSecretFieldHeader({
                  id: `${channel.key}-webhook-secret`,
                  label: "Webhook Secret",
                  hint: buildSecretHint({
                    value: settings.webhookSecret,
                    clear: settings.clearWebhookSecret,
                    hasSaved: savedProvider.hasWebhookSecret,
                    masked: savedProvider.webhookSecretMasked,
                    emptyText: "当前未保存 webhook secret。",
                    savingText: "已录入新的 webhook secret，保存后会替换当前配置。",
                    clearingText: "当前保存的 webhook secret 将在下次保存时清空。",
                  }),
                  action: savedProvider.hasWebhookSecret ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                      onClick={() =>
                        updateChannel(channel.key, {
                          webhookSecret: "",
                          clearWebhookSecret: !settings.clearWebhookSecret,
                        })
                      }
                    >
                      {settings.clearWebhookSecret ? "保留现有 Secret" : "清空已保存 Secret"}
                    </Button>
                  ) : undefined,
                })}
                <Input
                  id={`${channel.key}-webhook-secret`}
                  type="password"
                  autoComplete="off"
                  value={settings.webhookSecret}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  placeholder="留空表示保留当前 Secret，输入则替换"
                  onChange={(event) =>
                    updateChannel(channel.key, {
                      webhookSecret: event.target.value,
                      clearWebhookSecret: false,
                    })
                  }
                />
              </div>
            ) : null}

            {channel.supportsBotWebhookKey && "botWebhookKey" in settings && "hasBotWebhookKey" in savedProvider ? (
              <div className="space-y-2">
                {renderSecretFieldHeader({
                  id: `${channel.key}-bot-webhook-key`,
                  label: "机器人 Webhook Key",
                  hint: buildSecretHint({
                    value: settings.botWebhookKey,
                    clear: settings.clearBotWebhookKey,
                    hasSaved: savedProvider.hasBotWebhookKey,
                    masked: savedProvider.botWebhookKeyMasked,
                    emptyText: "当前未保存机器人 webhook key。",
                    savingText: "已录入新的 webhook key，保存后会替换当前配置。",
                    clearingText: "当前保存的 webhook key 将在下次保存时清空。",
                  }),
                  action: savedProvider.hasBotWebhookKey ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                      onClick={() =>
                        updateChannel(channel.key, {
                          botWebhookKey: "",
                          clearBotWebhookKey: !settings.clearBotWebhookKey,
                        })
                      }
                    >
                      {settings.clearBotWebhookKey ? "保留现有 Key" : "清空已保存 Key"}
                    </Button>
                  ) : undefined,
                })}
                <Input
                  id={`${channel.key}-bot-webhook-key`}
                  type="password"
                  autoComplete="off"
                  value={settings.botWebhookKey}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  placeholder="留空表示保留当前 Key，输入则替换"
                  onChange={(event) =>
                    updateChannel(channel.key, {
                      botWebhookKey: event.target.value,
                      clearBotWebhookKey: false,
                    })
                  }
                />
              </div>
            ) : null}

            {"webhookSecretHeader" in settings ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`${channel.key}-webhook-secret-header`}>Secret Header</Label>
                  <Input
                    id={`${channel.key}-webhook-secret-header`}
                    value={settings.webhookSecretHeader}
                    disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                    onChange={(event) =>
                      updateChannel(channel.key, { webhookSecretHeader: event.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`${channel.key}-webhook-secret-query-param`}>Secret Query Param</Label>
                  <Input
                    id={`${channel.key}-webhook-secret-query-param`}
                    value={settings.webhookSecretQueryParam}
                    disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                    onChange={(event) =>
                      updateChannel(channel.key, { webhookSecretQueryParam: event.target.value })
                    }
                  />
                </div>
              </div>
            ) : null}
          </section>
          ) : null}
      </>
    )
  }

  return (
    <div className="space-y-4 p-6">
      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          配置加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      {!canEditSettings ? (
        <div className="rounded-lg border border-border bg-secondary/30 p-3 text-sm text-muted-foreground">
          当前账号只有查看权限，不能修改渠道接入、Webhook 密钥和回调地址配置。
        </div>
      ) : null}

      <Card className="bg-card">
        <CardHeader className="space-y-4 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-secondary/60">
                <CurrentIcon className="size-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-base">{currentChannelMeta.label}</CardTitle>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {currentChannelDirty ? (
                <Badge
                  variant="outline"
                  className="rounded-full border-warning/40 bg-warning/10 px-2.5 text-warning-foreground"
                >
                  未保存
                </Badge>
              ) : null}
              <span className="text-xs text-muted-foreground">
                {currentSettings.enabled ? "已启用" : "未启用"}
              </span>
              <Switch
                checked={currentSettings.enabled}
                disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                onCheckedChange={(checked) =>
                  updateChannel(currentChannelMeta.key, { enabled: checked })
                }
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary" className="rounded-full px-2.5">
              {currentCredentialSummary}
            </Badge>
            <Badge variant="outline" className="rounded-full px-2.5">
              {currentTenantSummary}
            </Badge>
            <span className="rounded-full border border-border bg-background px-2.5 py-1">
              {currentChannelMeta.modeLabel}
            </span>
            <span className="font-mono">{currentChannelMeta.route}</span>
          </div>

          <Tabs value={activeChannel} onValueChange={(value) => setActiveChannel(value as ChannelKey)}>
            <TabsList className="flex h-auto w-full flex-wrap justify-start gap-2 bg-transparent p-0">
              {channelMeta.map((channel) => {
                const channelDirty = isChannelDirty(channel.key, draft, savedDraft)

                return (
                  <TabsTrigger
                    key={channel.key}
                    value={channel.key}
                    className="h-8 rounded-md border border-border bg-background px-3 text-xs data-[state=active]:border-primary data-[state=active]:bg-primary/10"
                  >
                    {channel.label}
                    {channelDirty ? <span className="size-1.5 rounded-full bg-warning" /> : null}
                  </TabsTrigger>
                )
              })}
            </TabsList>
          </Tabs>
        </CardHeader>

        <CardContent className="space-y-5 pt-0">
          {renderChannelSections(currentChannelMeta)}
        </CardContent>
      </Card>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void refetch()} disabled={isSaving || isFetching}>
          {isFetching ? "刷新中..." : "重新加载"}
        </Button>
        <Button
          variant="outline"
          onClick={resetToSaved}
          disabled={!canEditSettings || !hasLoadedSettings || !isDirty || isSaving}
        >
          撤销修改
        </Button>
        <Button
          onClick={() => void handleSave()}
          disabled={!canEditSettings || !hasLoadedSettings || !isDirty || isSaving}
        >
          {isSaving ? "保存中..." : "保存设置"}
        </Button>
      </div>
    </div>
  )
}
