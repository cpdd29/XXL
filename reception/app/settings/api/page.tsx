"use client"

import { useEffect, useMemo, useState } from "react"
import { Bot, Braces, KeyRound, Link2, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/hooks/use-auth"
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

function formatSavedAt(value?: string | null): string | null {
  const normalized = String(value ?? "").trim()
  if (!normalized) {
    return null
  }

  const directMatch = normalized.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})/)
  if (directMatch) {
    return `${directMatch[1]} ${directMatch[2]}`
  }

  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return normalized
  }

  const pad = (part: number) => String(part).padStart(2, "0")
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`
}

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
  const { hasPermission } = useAuth()
  const { data, isLoading, isFetching, error, refetch } = useAgentApiSettings()
  const updateAgentApiSettings = useUpdateAgentApiSettings()
  const savedSettings = data?.settings ?? defaultSettings
  const savedDraft = useMemo(() => toDraftSettings(savedSettings), [savedSettings])
  const [draft, setDraft] = useState<AgentApiDraftSettings>(savedDraft)
  const [activeProvider, setActiveProvider] = useState<ProviderKey>("openai")

  useEffect(() => {
    setDraft(savedDraft)
  }, [savedDraft])

  const hasLoadedSettings = Boolean(data?.settings)
  const isSaving = updateAgentApiSettings.isPending
  const canEditSettings = hasPermission("settings:agent-api:write")
  const isDirty = useMemo(
    () => JSON.stringify(buildUpdatePayload(draft)) !== JSON.stringify(buildUpdatePayload(savedDraft)),
    [draft, savedDraft],
  )
  const currentProviderMeta =
    providerMeta.find((provider) => provider.key === activeProvider) ?? providerMeta[0]
  const currentSettings = draft.providers[activeProvider]
  const currentSavedProvider = savedSettings.providers[activeProvider]

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
        title: "模型接入已保存",
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
    <div className="space-y-4 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-foreground">模型接入</h1>
          <p className="text-sm text-muted-foreground">统一维护模型入口、默认模型和网关地址。</p>
        </div>
        <div className="space-y-1 text-right">
          <p className="text-xs text-muted-foreground">
            {hasLoadedSettings
              ? data?.updatedAt
                ? `最近保存：${formatSavedAt(data.updatedAt) ?? data.updatedAt}`
                : "当前为默认配置"
              : isLoading
                ? "正在读取配置..."
                : "尚未加载到可编辑配置"}
          </p>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          配置加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      {!canEditSettings ? (
        <div className="rounded-lg border border-border bg-secondary/30 p-3 text-sm text-muted-foreground">
          当前账号只有查看权限，不能修改 Agent API 与密钥配置。
        </div>
      ) : null}

      <Card className="bg-card">
        <CardHeader className="space-y-4 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-secondary/60">
                <currentProviderMeta.icon className={`size-5 ${currentProviderMeta.accent}`} />
              </div>
              <div>
                <CardTitle className="text-base">{currentProviderMeta.label}</CardTitle>
                <p className="text-sm text-muted-foreground">{currentProviderMeta.description}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {currentSettings.enabled ? "已启用" : "未启用"}
              </span>
              <Switch
                checked={currentSettings.enabled}
                disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                onCheckedChange={(checked) => updateProvider(activeProvider, { enabled: checked })}
              />
            </div>
          </div>
          <Tabs value={activeProvider} onValueChange={(value) => setActiveProvider(value as ProviderKey)}>
            <TabsList className="flex h-auto w-full flex-wrap justify-start gap-2 bg-transparent p-0">
              {providerMeta.map((provider) => (
                <TabsTrigger
                  key={provider.key}
                  value={provider.key}
                  className="h-8 rounded-md border border-border bg-background px-3 text-xs data-[state=active]:border-primary data-[state=active]:bg-primary/10"
                >
                  {provider.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </CardHeader>
        <CardContent className="space-y-4 pt-0">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor={`${activeProvider}-api-key`}>API Key</Label>
                {currentSavedProvider.hasApiKey ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                    onClick={() =>
                      updateProvider(activeProvider, {
                        apiKey: "",
                        clearApiKey: !currentSettings.clearApiKey,
                      })
                    }
                  >
                    {currentSettings.clearApiKey ? "保留现有 Key" : "清空已保存 Key"}
                  </Button>
                ) : null}
              </div>
              <Input
                id={`${activeProvider}-api-key`}
                type="password"
                autoComplete="off"
                value={currentSettings.apiKey}
                disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                placeholder="留空表示保留当前 Key，输入则替换"
                onChange={(event) =>
                  updateProvider(activeProvider, {
                    apiKey: event.target.value,
                    clearApiKey: false,
                  })
                }
              />
              <p className="text-xs text-muted-foreground">
                {currentSettings.clearApiKey
                  ? "当前保存的 API Key 将在下次保存时清空。"
                  : currentSettings.apiKey
                    ? "已录入新的 API Key，保存后会替换当前密钥。"
                    : currentSavedProvider.hasApiKey
                      ? `当前已保存密钥：${currentSavedProvider.apiKeyMasked ?? "已配置"}`
                      : "当前未保存 API Key。"}
              </p>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor={`${activeProvider}-base-url`}>Base URL</Label>
              <Input
                id={`${activeProvider}-base-url`}
                value={currentSettings.baseUrl}
                disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                onChange={(event) => updateProvider(activeProvider, { baseUrl: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${activeProvider}-model`}>默认模型</Label>
              <Input
                id={`${activeProvider}-model`}
                value={currentSettings.model}
                disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                onChange={(event) => updateProvider(activeProvider, { model: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`${activeProvider}-endpoint-path`}>Endpoint Path</Label>
              <Input
                id={`${activeProvider}-endpoint-path`}
                value={currentSettings.endpointPath}
                disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                onChange={(event) => updateProvider(activeProvider, { endpointPath: event.target.value })}
              />
            </div>
            {currentProviderMeta.fields.includes("organizationId") ? (
              <div className="space-y-2">
                <Label htmlFor={`${activeProvider}-organization`}>Organization</Label>
                <Input
                  id={`${activeProvider}-organization`}
                  value={currentSettings.organizationId}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) => updateProvider(activeProvider, { organizationId: event.target.value })}
                />
              </div>
            ) : null}
            {currentProviderMeta.fields.includes("projectId") ? (
              <div className="space-y-2">
                <Label htmlFor={`${activeProvider}-project`}>Project</Label>
                <Input
                  id={`${activeProvider}-project`}
                  value={currentSettings.projectId}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) => updateProvider(activeProvider, { projectId: event.target.value })}
                />
              </div>
            ) : null}
            {currentProviderMeta.fields.includes("groupId") ? (
              <div className="space-y-2">
                <Label htmlFor={`${activeProvider}-group-id`}>Group ID</Label>
                <Input
                  id={`${activeProvider}-group-id`}
                  value={currentSettings.groupId}
                  disabled={!canEditSettings || !hasLoadedSettings || isSaving}
                  onChange={(event) => updateProvider(activeProvider, { groupId: event.target.value })}
                />
              </div>
            ) : null}
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
