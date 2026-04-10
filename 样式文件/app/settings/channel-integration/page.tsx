"use client"

import { useEffect, useMemo, useState } from "react"
import { RadioTower, Send, ShieldCheck, Webhook } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  useChannelIntegrationSettings,
  useUpdateChannelIntegrationSettings,
} from "@/hooks/use-settings"
import { toast } from "@/hooks/use-toast"
import type {
  ChannelIntegrationSettings,
  UpdateChannelIntegrationSettingsRequest,
  UpdateDingTalkChannelIntegrationSettingsRequest,
  UpdateFeishuChannelIntegrationSettingsRequest,
  UpdateTelegramChannelIntegrationSettingsRequest,
  UpdateWeComChannelIntegrationSettingsRequest,
} from "@/types"

type ChannelKey = keyof ChannelIntegrationSettings

type TelegramDraft = {
  enabled: boolean
  apiBaseUrl: string
  httpTimeoutSeconds: number
  botToken: string
  clearBotToken: boolean
  webhookSecret: string
  clearWebhookSecret: boolean
}

type DingTalkDraft = {
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

type WebhookBotDraft = {
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
    hasBotToken: false,
    botTokenMasked: null,
    hasWebhookSecret: false,
    webhookSecretMasked: null,
  },
  dingtalk: {
    enabled: true,
    apiBaseUrl: "https://oapi.dingtalk.com",
    httpTimeoutSeconds: 10,
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
    hasBotWebhookKey: false,
    botWebhookKeyMasked: null,
    hasWebhookSecret: false,
    webhookSecretMasked: null,
  },
}

const channelMeta: Array<{
  key: ChannelKey
  label: string
  description: string
  route: string
  icon: typeof Send
  supportsBotToken: boolean
  supportsBotWebhookKey: boolean
  supportsBotWebhookBaseUrl: boolean
}> = [
  {
    key: "telegram",
    label: "Telegram",
    description: "配置 Bot Token、入站 secret 和 Telegram API 地址。",
    route: "/api/webhooks/telegram",
    icon: Send,
    supportsBotToken: true,
    supportsBotWebhookKey: false,
    supportsBotWebhookBaseUrl: false,
  },
  {
    key: "dingtalk",
    label: "DingTalk",
    description: "配置钉钉应用机器人 Stream 入站与 OpenAPI 回发所需的 Agent ID、Client ID/Secret 等参数。",
    route: "/api/webhooks/dingtalk",
    icon: RadioTower,
    supportsBotToken: false,
    supportsBotWebhookKey: false,
    supportsBotWebhookBaseUrl: false,
  },
  {
    key: "wecom",
    label: "WeCom",
    description: "配置企业微信机器人 webhook base URL、key 与入站鉴权参数。",
    route: "/api/webhooks/wecom",
    icon: Webhook,
    supportsBotToken: false,
    supportsBotWebhookKey: true,
    supportsBotWebhookBaseUrl: true,
  },
  {
    key: "feishu",
    label: "Feishu",
    description: "配置飞书机器人 webhook base URL、key 与入站鉴权参数。",
    route: "/api/webhooks/feishu",
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
      botToken: "",
      clearBotToken: false,
      webhookSecret: "",
      clearWebhookSecret: false,
    },
    dingtalk: {
      enabled: source.dingtalk.enabled,
      apiBaseUrl: source.dingtalk.apiBaseUrl,
      httpTimeoutSeconds: source.dingtalk.httpTimeoutSeconds,
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
      botWebhookKey: "",
      clearBotWebhookKey: false,
      webhookSecret: "",
      clearWebhookSecret: false,
    },
  }
}

function buildTelegramPayload(draft: TelegramDraft): UpdateTelegramChannelIntegrationSettingsRequest {
  const payload: UpdateTelegramChannelIntegrationSettingsRequest = {
    enabled: draft.enabled,
    apiBaseUrl: draft.apiBaseUrl,
    httpTimeoutSeconds: draft.httpTimeoutSeconds,
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

export default function ChannelIntegrationSettingsPage() {
  const { data, isLoading, isFetching, error, refetch } = useChannelIntegrationSettings()
  const updateChannelIntegrationSettings = useUpdateChannelIntegrationSettings()
  const savedSettings = data?.settings ?? defaultSettings
  const savedDraft = useMemo(() => toDraft(savedSettings), [savedSettings])
  const [draft, setDraft] = useState<ChannelDraft>(savedDraft)

  useEffect(() => {
    setDraft(savedDraft)
  }, [savedDraft])

  const hasLoadedSettings = Boolean(data?.settings)
  const isSaving = updateChannelIntegrationSettings.isPending
  const isDirty = useMemo(
    () => JSON.stringify(buildUpdatePayload(draft)) !== JSON.stringify(buildUpdatePayload(savedDraft)),
    [draft, savedDraft],
  )

  const updateChannel = <K extends ChannelKey>(channel: K, patch: Partial<ChannelDraft[K]>) => {
    setDraft((current) => ({
      ...current,
      [channel]: {
        ...current[channel],
        ...patch,
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

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-foreground">渠道接入配置</h1>
          <p className="text-sm text-muted-foreground">
            统一维护 Telegram、DingTalk、WeCom、Feishu 的入站鉴权和出站机器人配置。
          </p>
        </div>
        <div className="space-y-1 text-right">
          <p className="text-xs text-muted-foreground">
            {hasLoadedSettings
              ? data?.updatedAt
                ? `最近保存：${data.updatedAt}`
                : "当前为默认配置"
              : isLoading
                ? "正在读取配置..."
                : "尚未加载到可编辑配置"}
          </p>
          <p className="text-xs text-muted-foreground">敏感信息会按掩码回显并以加密形式落库。</p>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          配置加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        {channelMeta.map((channel) => {
          const Icon = channel.icon
          const settings = draft[channel.key]
          const savedProvider = savedSettings[channel.key]

          return (
            <Card key={channel.key} className="bg-card">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-xl bg-secondary/60">
                      <Icon className="size-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{channel.label}</CardTitle>
                      <p className="text-sm text-muted-foreground">{channel.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      {settings.enabled ? "已启用" : "已停用"}
                    </span>
                    <Switch
                      checked={settings.enabled}
                      disabled={!hasLoadedSettings || isSaving}
                      onCheckedChange={(checked) => updateChannel(channel.key, { enabled: checked })}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor={`${channel.key}-route`}>Webhook 路径</Label>
                  <Input id={`${channel.key}-route`} readOnly value={channel.route} />
                </div>

                {"apiBaseUrl" in settings ? (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor={`${channel.key}-api-base-url`}>API Base URL</Label>
                      <Input
                        id={`${channel.key}-api-base-url`}
                        value={settings.apiBaseUrl}
                        disabled={!hasLoadedSettings || isSaving}
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
                        disabled={!hasLoadedSettings || isSaving}
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
                        disabled={!hasLoadedSettings || isSaving}
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
                        disabled={!hasLoadedSettings || isSaving}
                        onChange={(event) =>
                          updateChannel(channel.key, {
                            httpTimeoutSeconds: Number(event.target.value) || 1,
                          })
                        }
                      />
                    </div>
                  </div>
                ) : null}

                {channel.key === "telegram" && "botToken" in settings ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor={`${channel.key}-bot-token`}>Bot Token</Label>
                      {savedSettings.telegram.hasBotToken ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={!hasLoadedSettings || isSaving}
                          onClick={() =>
                            updateChannel(channel.key, {
                              botToken: "",
                              clearBotToken: !settings.clearBotToken,
                            })
                          }
                        >
                          {settings.clearBotToken ? "保留现有 Token" : "清空已保存 Token"}
                        </Button>
                      ) : null}
                    </div>
                    <Input
                      id={`${channel.key}-bot-token`}
                      type="password"
                      autoComplete="off"
                      value={settings.botToken}
                      disabled={!hasLoadedSettings || isSaving}
                      placeholder="留空表示保留当前 Token，输入则替换"
                      onChange={(event) =>
                        updateChannel(channel.key, {
                          botToken: event.target.value,
                          clearBotToken: false,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      {buildSecretHint({
                        value: settings.botToken,
                        clear: settings.clearBotToken,
                        hasSaved: savedSettings.telegram.hasBotToken,
                        masked: savedSettings.telegram.botTokenMasked,
                        emptyText: "当前未保存 Bot Token。",
                        savingText: "已录入新的 Bot Token，保存后会替换当前配置。",
                        clearingText: "当前保存的 Bot Token 将在下次保存时清空。",
                      })}
                    </p>
                  </div>
                ) : null}

                {channel.key === "dingtalk" && "appId" in settings && "hasClientSecret" in savedProvider ? (
                  <>
                    <div className="rounded-lg border border-border/60 bg-muted/30 p-3 text-sm text-muted-foreground">
                      当前使用钉钉应用机器人模式。保存后后端会自动启动 DingTalk Stream 入站；任务回发优先使用会话
                      `sessionWebhook`，配置 `Agent ID` 后也可以使用 OpenAPI 主动回发。
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="space-y-2">
                        <Label htmlFor={`${channel.key}-app-id`}>App ID</Label>
                        <Input
                          id={`${channel.key}-app-id`}
                          value={settings.appId}
                          disabled={!hasLoadedSettings || isSaving}
                          placeholder="钉钉应用 App ID"
                          onChange={(event) =>
                            updateChannel(channel.key, { appId: event.target.value })
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`${channel.key}-agent-id`}>Agent ID</Label>
                        <Input
                          id={`${channel.key}-agent-id`}
                          value={settings.agentId}
                          disabled={!hasLoadedSettings || isSaving}
                          placeholder="用于 OpenAPI 主动发送的 Agent ID"
                          onChange={(event) =>
                            updateChannel(channel.key, { agentId: event.target.value })
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`${channel.key}-client-id`}>Client ID</Label>
                        <Input
                          id={`${channel.key}-client-id`}
                          value={settings.clientId}
                          disabled={!hasLoadedSettings || isSaving}
                          placeholder="应用 clientId"
                          onChange={(event) =>
                            updateChannel(channel.key, { clientId: event.target.value })
                          }
                        />
                      </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <div className="flex items-center justify-between gap-3">
                          <Label htmlFor={`${channel.key}-client-secret`}>Client Secret</Label>
                          {savedProvider.hasClientSecret ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              disabled={!hasLoadedSettings || isSaving}
                              onClick={() =>
                                updateChannel(channel.key, {
                                  clientSecret: "",
                                  clearClientSecret: !settings.clearClientSecret,
                                })
                              }
                            >
                              {settings.clearClientSecret ? "保留现有 Secret" : "清空已保存 Secret"}
                            </Button>
                          ) : null}
                        </div>
                        <Input
                          id={`${channel.key}-client-secret`}
                          type="password"
                          autoComplete="off"
                          value={settings.clientSecret}
                          disabled={!hasLoadedSettings || isSaving}
                          placeholder="留空表示保留当前 Secret，输入则替换"
                          onChange={(event) =>
                            updateChannel(channel.key, {
                              clientSecret: event.target.value,
                              clearClientSecret: false,
                            })
                          }
                        />
                        <p className="text-xs text-muted-foreground">
                          {buildSecretHint({
                            value: settings.clientSecret,
                            clear: settings.clearClientSecret,
                            hasSaved: savedProvider.hasClientSecret,
                            masked: savedProvider.clientSecretMasked,
                            emptyText: "当前未保存 client secret。",
                            savingText: "已录入新的 client secret，保存后会替换当前配置。",
                            clearingText: "当前保存的 client secret 将在下次保存时清空。",
                          })}
                        </p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`${channel.key}-corp-id`}>Corp ID</Label>
                        <Input
                          id={`${channel.key}-corp-id`}
                          value={settings.corpId}
                          disabled={!hasLoadedSettings || isSaving}
                          placeholder="可选，用于企业内部应用场景"
                          onChange={(event) =>
                            updateChannel(channel.key, { corpId: event.target.value })
                          }
                        />
                        <p className="text-xs text-muted-foreground">
                          非必填；当后端按租户或企业身份调用钉钉开放平台时可复用该字段。
                        </p>
                      </div>
                    </div>
                  </>
                ) : null}

                {"webhookSecret" in settings && "hasWebhookSecret" in savedProvider ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor={`${channel.key}-webhook-secret`}>Webhook Secret</Label>
                      {savedProvider.hasWebhookSecret ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={!hasLoadedSettings || isSaving}
                          onClick={() =>
                            updateChannel(channel.key, {
                              webhookSecret: "",
                              clearWebhookSecret: !settings.clearWebhookSecret,
                            })
                          }
                        >
                          {settings.clearWebhookSecret ? "保留现有 Secret" : "清空已保存 Secret"}
                        </Button>
                      ) : null}
                    </div>
                    <Input
                      id={`${channel.key}-webhook-secret`}
                      type="password"
                      autoComplete="off"
                      value={settings.webhookSecret}
                      disabled={!hasLoadedSettings || isSaving}
                      placeholder="留空表示保留当前 Secret，输入则替换"
                      onChange={(event) =>
                        updateChannel(channel.key, {
                          webhookSecret: event.target.value,
                          clearWebhookSecret: false,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      {buildSecretHint({
                        value: settings.webhookSecret,
                        clear: settings.clearWebhookSecret,
                        hasSaved: savedProvider.hasWebhookSecret,
                        masked: savedProvider.webhookSecretMasked,
                        emptyText: "当前未保存 webhook secret。",
                        savingText: "已录入新的 webhook secret，保存后会替换当前配置。",
                        clearingText: "当前保存的 webhook secret 将在下次保存时清空。",
                      })}
                    </p>
                  </div>
                ) : null}

                {channel.supportsBotWebhookKey && "botWebhookKey" in settings && "hasBotWebhookKey" in savedProvider ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor={`${channel.key}-bot-webhook-key`}>机器人 Webhook Key</Label>
                      {savedProvider.hasBotWebhookKey ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={!hasLoadedSettings || isSaving}
                          onClick={() =>
                            updateChannel(channel.key, {
                              botWebhookKey: "",
                              clearBotWebhookKey: !settings.clearBotWebhookKey,
                            })
                          }
                        >
                          {settings.clearBotWebhookKey ? "保留现有 Key" : "清空已保存 Key"}
                        </Button>
                      ) : null}
                    </div>
                    <Input
                      id={`${channel.key}-bot-webhook-key`}
                      type="password"
                      autoComplete="off"
                      value={settings.botWebhookKey}
                      disabled={!hasLoadedSettings || isSaving}
                      placeholder="留空表示保留当前 Key，输入则替换"
                      onChange={(event) =>
                        updateChannel(channel.key, {
                          botWebhookKey: event.target.value,
                          clearBotWebhookKey: false,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      {buildSecretHint({
                        value: settings.botWebhookKey,
                        clear: settings.clearBotWebhookKey,
                        hasSaved: savedProvider.hasBotWebhookKey,
                        masked: savedProvider.botWebhookKeyMasked,
                        emptyText: "当前未保存机器人 webhook key。",
                        savingText: "已录入新的 webhook key，保存后会替换当前配置。",
                        clearingText: "当前保存的 webhook key 将在下次保存时清空。",
                      })}
                    </p>
                  </div>
                ) : null}

                {"webhookSecretHeader" in settings ? (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor={`${channel.key}-webhook-secret-header`}>Secret Header</Label>
                      <Input
                        id={`${channel.key}-webhook-secret-header`}
                        value={settings.webhookSecretHeader}
                        disabled={!hasLoadedSettings || isSaving}
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
                        disabled={!hasLoadedSettings || isSaving}
                        onChange={(event) =>
                          updateChannel(channel.key, { webhookSecretQueryParam: event.target.value })
                        }
                      />
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void refetch()} disabled={isSaving || isFetching}>
          {isFetching ? "刷新中..." : "重新加载"}
        </Button>
        <Button
          variant="outline"
          onClick={resetToSaved}
          disabled={!hasLoadedSettings || !isDirty || isSaving}
        >
          撤销修改
        </Button>
        <Button onClick={() => void handleSave()} disabled={!hasLoadedSettings || !isDirty || isSaving}>
          {isSaving ? "保存中..." : "保存设置"}
        </Button>
      </div>
    </div>
  )
}
