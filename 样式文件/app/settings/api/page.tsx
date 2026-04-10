"use client"

import { useEffect, useMemo, useState } from "react"
import { Bot, Braces, KeyRound, Link2, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useAgentApiSettings, useUpdateAgentApiSettings } from "@/hooks/use-settings"
import { toast } from "@/hooks/use-toast"
import type {
  AgentApiProviderSettings,
  AgentApiSettings,
  UpdateAgentApiSettingsRequest,
  UpdateAgentApiProviderSettingsRequest,
} from "@/types"

const providerOrder = [
  "openai",
  "codex",
  "claude",
  "kimi",
  "minimax",
  "gemini",
  "deepseek",
  "openapi",
] as const

type ProviderKey = (typeof providerOrder)[number]
type ProviderField = "organizationId" | "projectId" | "groupId"
type AgentApiProviderDraft = Omit<AgentApiProviderSettings, "hasApiKey" | "apiKeyMasked"> & {
  apiKey: string
  clearApiKey: boolean
}
type AgentApiDraftSettings = {
  providers: Record<ProviderKey, AgentApiProviderDraft>
}

const defaultProviderSettings: AgentApiProviderSettings = {
  enabled: false,
  baseUrl: "",
  model: "",
  organizationId: "",
  projectId: "",
  groupId: "",
  endpointPath: "",
  notes: "",
  hasApiKey: false,
  apiKeyMasked: null,
}

const defaultSettings: AgentApiSettings = {
  providers: {
    openai: {
      ...defaultProviderSettings,
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-5.4",
      endpointPath: "/responses",
      notes: "OpenAI 标准 Responses API。",
    },
    codex: {
      ...defaultProviderSettings,
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-5-codex",
      endpointPath: "/responses",
      notes: "用于编码类 Agent 的 Codex / OpenAI 兼容入口。",
    },
    claude: {
      ...defaultProviderSettings,
      baseUrl: "https://api.anthropic.com/v1",
      model: "claude-sonnet-4-0",
      endpointPath: "/messages",
      notes: "Anthropic Claude Messages API。",
    },
    kimi: {
      ...defaultProviderSettings,
      baseUrl: "https://api.moonshot.cn/v1",
      model: "moonshot-v1-128k",
      endpointPath: "/chat/completions",
      notes: "Moonshot / Kimi 兼容 OpenAI 风格接口。",
    },
    minimax: {
      ...defaultProviderSettings,
      baseUrl: "https://api.minimaxi.com/v1",
      model: "MiniMax-M1",
      endpointPath: "/text/chatcompletion_v2",
      notes: "MiniMax 需要额外填写 Group ID。",
    },
    gemini: {
      ...defaultProviderSettings,
      baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
      model: "gemini-2.5-pro",
      endpointPath: "/chat/completions",
      notes: "Gemini OpenAI-compatible 入口。",
    },
    deepseek: {
      ...defaultProviderSettings,
      baseUrl: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      endpointPath: "/chat/completions",
      notes: "DeepSeek OpenAI-compatible 入口。",
    },
    openapi: {
      ...defaultProviderSettings,
      baseUrl: "https://api.example.com/v1",
      model: "",
      endpointPath: "/chat/completions",
      notes: "自定义 OpenAI-compatible 网关。",
    },
  },
}

const providerMeta: Array<{
  key: ProviderKey
  label: string
  description: string
  icon: typeof Sparkles
  accent: string
  fields: ProviderField[]
}> = [
  {
    key: "openai",
    label: "OpenAI",
    description: "通用 OpenAI Agent 执行入口",
    icon: Sparkles,
    accent: "text-primary",
    fields: ["organizationId", "projectId"],
  },
  {
    key: "codex",
    label: "Codex",
    description: "代码生成 / 修复型 Agent",
    icon: Bot,
    accent: "text-success",
    fields: [],
  },
  {
    key: "claude",
    label: "Claude",
    description: "Anthropic Claude 对话执行入口",
    icon: KeyRound,
    accent: "text-warning-foreground",
    fields: [],
  },
  {
    key: "kimi",
    label: "Kimi",
    description: "Moonshot / Kimi 长上下文入口",
    icon: Link2,
    accent: "text-primary",
    fields: [],
  },
  {
    key: "minimax",
    label: "MiniMax",
    description: "MiniMax 模型与 Group ID 配置",
    icon: Braces,
    accent: "text-success",
    fields: ["groupId"],
  },
  {
    key: "gemini",
    label: "Gemini",
    description: "Google Gemini 兼容入口",
    icon: Sparkles,
    accent: "text-primary",
    fields: [],
  },
  {
    key: "deepseek",
    label: "DeepSeek",
    description: "DeepSeek 推理与对话入口",
    icon: Bot,
    accent: "text-primary",
    fields: [],
  },
  {
    key: "openapi",
    label: "OpenAPI Compatible",
    description: "自定义 OpenAI-compatible 网关",
    icon: Braces,
    accent: "text-muted-foreground",
    fields: [],
  },
]

function toDraftProvider(settings?: AgentApiProviderSettings): AgentApiProviderDraft {
  const source = settings ?? defaultProviderSettings
  return {
    enabled: source.enabled,
    baseUrl: source.baseUrl,
    model: source.model,
    organizationId: source.organizationId,
    projectId: source.projectId,
    groupId: source.groupId,
    endpointPath: source.endpointPath,
    notes: source.notes,
    apiKey: "",
    clearApiKey: false,
  }
}

function toDraftSettings(settings?: AgentApiSettings): AgentApiDraftSettings {
  const source = settings ?? defaultSettings
  return {
    providers: providerOrder.reduce((result, providerKey) => {
      result[providerKey] = toDraftProvider(source.providers[providerKey])
      return result
    }, {} as Record<ProviderKey, AgentApiProviderDraft>),
  }
}

function buildUpdatePayload(draft: AgentApiDraftSettings): UpdateAgentApiSettingsRequest {
  return {
    providers: providerOrder.reduce((result, providerKey) => {
      const provider = draft.providers[providerKey]
      const payload: UpdateAgentApiProviderSettingsRequest = {
        enabled: provider.enabled,
        baseUrl: provider.baseUrl,
        model: provider.model,
        organizationId: provider.organizationId,
        projectId: provider.projectId,
        groupId: provider.groupId,
        endpointPath: provider.endpointPath,
        notes: provider.notes,
      }
      if (provider.apiKey.trim()) {
        payload.apiKey = provider.apiKey.trim()
      }
      if (provider.clearApiKey) {
        payload.clearApiKey = true
      }
      result[providerKey] = payload
      return result
    }, {} as Record<ProviderKey, UpdateAgentApiProviderSettingsRequest>),
  }
}

export default function AgentApiSettingsPage() {
  const { data, isLoading, isFetching, error, refetch } = useAgentApiSettings()
  const updateAgentApiSettings = useUpdateAgentApiSettings()
  const savedSettings = data?.settings ?? defaultSettings
  const savedDraft = useMemo(() => toDraftSettings(savedSettings), [savedSettings])
  const [draft, setDraft] = useState<AgentApiDraftSettings>(savedDraft)

  useEffect(() => {
    setDraft(savedDraft)
  }, [savedDraft])

  const hasLoadedSettings = Boolean(data?.settings)
  const isSaving = updateAgentApiSettings.isPending
  const isDirty = useMemo(
    () => JSON.stringify(buildUpdatePayload(draft)) !== JSON.stringify(buildUpdatePayload(savedDraft)),
    [draft, savedDraft],
  )

  const updateProvider = (provider: ProviderKey, patch: Partial<AgentApiProviderDraft>) => {
    setDraft((current) => ({
      providers: {
        ...current.providers,
        [provider]: {
          ...current.providers[provider],
          ...patch,
        },
      },
    }))
  }

  const handleSave = async () => {
    try {
      const response = await updateAgentApiSettings.mutateAsync(buildUpdatePayload(draft))
      setDraft(toDraftSettings(response.settings))
      toast({
        title: "Agent API 配置已保存",
        description: "新的供应商配置已经写入后端，密钥按掩码方式回显。",
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
          <h1 className="text-2xl font-bold text-foreground">Agent API 配置</h1>
          <p className="text-sm text-muted-foreground">
            为不同 Agent 绑定主流模型供应商入口，统一维护 API Key、模型和网关地址。
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
          <p className="text-xs text-muted-foreground">敏感信息会以加密形式落库。</p>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          配置加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        {providerMeta.map((provider) => {
          const settings = draft.providers[provider.key]
          const savedProvider = savedSettings.providers[provider.key]
          const Icon = provider.icon
          const keyHint = settings.clearApiKey
            ? "当前保存的 API Key 将在下次保存时清空。"
            : settings.apiKey
              ? "已录入新的 API Key，保存后会替换当前密钥。"
              : savedProvider.hasApiKey
                ? `当前已保存密钥：${savedProvider.apiKeyMasked ?? "已配置"}`
                : "当前未保存 API Key。"

          return (
            <Card key={provider.key} className="bg-card">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-xl bg-secondary/60">
                      <Icon className={`size-5 ${provider.accent}`} />
                    </div>
                    <div>
                      <CardTitle className="text-base">{provider.label}</CardTitle>
                      <p className="text-sm text-muted-foreground">{provider.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      {settings.enabled ? "已启用" : "未启用"}
                    </span>
                    <Switch
                      checked={settings.enabled}
                      disabled={!hasLoadedSettings || isSaving}
                      onCheckedChange={(checked) => updateProvider(provider.key, { enabled: checked })}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2 md:col-span-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor={`${provider.key}-api-key`}>API Key</Label>
                      {savedProvider.hasApiKey ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={!hasLoadedSettings || isSaving}
                          onClick={() =>
                            updateProvider(provider.key, {
                              apiKey: "",
                              clearApiKey: !settings.clearApiKey,
                            })
                          }
                        >
                          {settings.clearApiKey ? "保留现有 Key" : "清空已保存 Key"}
                        </Button>
                      ) : null}
                    </div>
                    <Input
                      id={`${provider.key}-api-key`}
                      type="password"
                      autoComplete="off"
                      value={settings.apiKey}
                      disabled={!hasLoadedSettings || isSaving}
                      placeholder="留空表示保留当前 Key，输入则替换"
                      onChange={(event) =>
                        updateProvider(provider.key, {
                          apiKey: event.target.value,
                          clearApiKey: false,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">{keyHint}</p>
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor={`${provider.key}-base-url`}>Base URL</Label>
                    <Input
                      id={`${provider.key}-base-url`}
                      value={settings.baseUrl}
                      disabled={!hasLoadedSettings || isSaving}
                      onChange={(event) => updateProvider(provider.key, { baseUrl: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`${provider.key}-model`}>默认模型</Label>
                    <Input
                      id={`${provider.key}-model`}
                      value={settings.model}
                      disabled={!hasLoadedSettings || isSaving}
                      onChange={(event) => updateProvider(provider.key, { model: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`${provider.key}-endpoint-path`}>Endpoint Path</Label>
                    <Input
                      id={`${provider.key}-endpoint-path`}
                      value={settings.endpointPath}
                      disabled={!hasLoadedSettings || isSaving}
                      onChange={(event) =>
                        updateProvider(provider.key, { endpointPath: event.target.value })
                      }
                    />
                  </div>
                  {provider.fields.includes("organizationId") ? (
                    <div className="space-y-2">
                      <Label htmlFor={`${provider.key}-organization`}>Organization</Label>
                      <Input
                        id={`${provider.key}-organization`}
                        value={settings.organizationId}
                        disabled={!hasLoadedSettings || isSaving}
                        onChange={(event) =>
                          updateProvider(provider.key, { organizationId: event.target.value })
                        }
                      />
                    </div>
                  ) : null}
                  {provider.fields.includes("projectId") ? (
                    <div className="space-y-2">
                      <Label htmlFor={`${provider.key}-project`}>Project</Label>
                      <Input
                        id={`${provider.key}-project`}
                        value={settings.projectId}
                        disabled={!hasLoadedSettings || isSaving}
                        onChange={(event) =>
                          updateProvider(provider.key, { projectId: event.target.value })
                        }
                      />
                    </div>
                  ) : null}
                  {provider.fields.includes("groupId") ? (
                    <div className="space-y-2">
                      <Label htmlFor={`${provider.key}-group-id`}>Group ID</Label>
                      <Input
                        id={`${provider.key}-group-id`}
                        value={settings.groupId}
                        disabled={!hasLoadedSettings || isSaving}
                        onChange={(event) => updateProvider(provider.key, { groupId: event.target.value })}
                      />
                    </div>
                  ) : null}
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor={`${provider.key}-notes`}>备注</Label>
                    <Textarea
                      id={`${provider.key}-notes`}
                      rows={3}
                      value={settings.notes}
                      disabled={!hasLoadedSettings || isSaving}
                      onChange={(event) => updateProvider(provider.key, { notes: event.target.value })}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card className="bg-card">
        <CardHeader>
          <CardTitle className="text-base">联调地址</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="api-base-url">后端 API</Label>
            <Input
              id="api-base-url"
              readOnly
              value={process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080"}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ws-base-url">实时 WebSocket</Label>
            <Input
              id="ws-base-url"
              readOnly
              value={process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://127.0.0.1:8080"}
            />
          </div>
        </CardContent>
      </Card>

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
