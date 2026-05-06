"use client"

import { useEffect, useMemo, useState } from "react"
import { Bot, KeyRound, RefreshCw, Save } from "lucide-react"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Checkbox } from "@/shared/ui/checkbox"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Switch } from "@/shared/ui/switch"
import { Textarea } from "@/shared/ui/textarea"
import { useAgentApiSettings, useUpdateAgentApiSettings } from "@/modules/settings/hooks/use-settings"
import { toast } from "@/shared/hooks/use-toast"
import type {
  AgentApiProviderSettings,
  AgentApiSettings,
  UpdateAgentApiProviderSettingsRequest,
} from "@/shared/types"

type ProviderDraft = {
  enabled: boolean
  baseUrl: string
  model: string
  requestPath: string
  organizationId: string
  projectId: string
  groupId: string
  endpointPath: string
  notes: string
  apiKey: string
  clearApiKey: boolean
}

const REQUEST_PATH_OPTIONS = [
  { value: "/responses", label: "Responses API (/responses)" },
  { value: "/chat/completions", label: "Chat Completions (/chat/completions)" },
  { value: "/messages", label: "Messages API (/messages)" },
  { value: "/text/chatcompletion_v2", label: "MiniMax V2 (/text/chatcompletion_v2)" },
  { value: "custom", label: "自定义 Endpoint Path" },
] as const

const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  openai: "OpenAI",
  codex: "OpenAI Codex",
  claude: "Claude",
  kimi: "Kimi",
  minimax: "MiniMax",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  openapi: "OpenAPI Compatible",
}

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function getProviderDisplayName(providerKey: string) {
  const normalized = providerKey.trim().toLowerCase()
  return PROVIDER_DISPLAY_NAMES[normalized] ?? providerKey
}

function resolveRequestPath(endpointPath: string) {
  const normalized = endpointPath.trim()
  const matched = REQUEST_PATH_OPTIONS.find((item) => item.value !== "custom" && item.value === normalized)
  return matched ? matched.value : "custom"
}

function toDraftMap(settings?: AgentApiSettings): Record<string, ProviderDraft> {
  const entries = Object.entries(settings?.providers ?? {})
  return Object.fromEntries(
    entries.map(([providerKey, provider]) => [
      providerKey,
      {
        enabled: provider.enabled,
        baseUrl: provider.baseUrl,
        model: provider.model,
        requestPath: resolveRequestPath(provider.endpointPath),
        organizationId: provider.organizationId,
        projectId: provider.projectId,
        groupId: provider.groupId,
        endpointPath: provider.endpointPath,
        notes: provider.notes,
        apiKey: "",
        clearApiKey: false,
      },
    ]),
  )
}

function buildProviderPayload(draft: ProviderDraft): UpdateAgentApiProviderSettingsRequest {
  const apiKey = draft.apiKey.trim()
  const endpointPath = draft.requestPath === "custom" ? draft.endpointPath.trim() : draft.requestPath

  return {
    enabled: draft.enabled,
    baseUrl: draft.baseUrl.trim(),
    model: draft.model.trim(),
    organizationId: draft.organizationId.trim(),
    projectId: draft.projectId.trim(),
    groupId: draft.groupId.trim(),
    endpointPath,
    notes: draft.notes.trim(),
    apiKey: apiKey || undefined,
    clearApiKey: draft.clearApiKey || undefined,
  }
}

function maskSummary(provider: AgentApiProviderSettings) {
  if (!provider.hasApiKey) return "未配置"
  return provider.apiKeyMasked || "已配置"
}

function providerKeyStatus(provider: AgentApiProviderSettings) {
  return provider.hasApiKey ? "已配置" : "未配置"
}

export default function AgentApiSettingsPage() {
  const settingsQuery = useAgentApiSettings()
  const updateMutation = useUpdateAgentApiSettings()
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({})
  const [activeProviderKey, setActiveProviderKey] = useState<string>("")

  const settings = settingsQuery.data?.settings
  const providerEntries = useMemo(
    () =>
      Object.entries(settings?.providers ?? {}).sort(([leftKey, leftProvider], [rightKey, rightProvider]) => {
        if (leftProvider.enabled !== rightProvider.enabled) {
          return leftProvider.enabled ? -1 : 1
        }
        return leftKey.localeCompare(rightKey)
      }),
    [settings?.providers],
  )
  const providerKeys = useMemo(() => providerEntries.map(([providerKey]) => providerKey), [providerEntries])
  const providerDisplayNameMap = useMemo(() => {
    const baseCount = new Map<string, number>()
    providerEntries.forEach(([providerKey]) => {
      const baseName = getProviderDisplayName(providerKey)
      baseCount.set(baseName, (baseCount.get(baseName) ?? 0) + 1)
    })

    return Object.fromEntries(
      providerEntries.map(([providerKey]) => {
        const baseName = getProviderDisplayName(providerKey)
        const hasDuplicateName = (baseCount.get(baseName) ?? 0) > 1
        const displayName = hasDuplicateName ? `${baseName} (${providerKey})` : baseName
        return [providerKey, displayName]
      }),
    ) as Record<string, string>
  }, [providerEntries])
  const enabledCount = useMemo(
    () => providerEntries.filter(([, provider]) => provider.enabled).length,
    [providerEntries],
  )

  useEffect(() => {
    setDrafts(toDraftMap(settings))
  }, [settings])

  useEffect(() => {
    if (providerKeys.length === 0) {
      setActiveProviderKey("")
      return
    }

    setActiveProviderKey((current) => (current && providerKeys.includes(current) ? current : providerKeys[0]))
  }, [providerKeys])

  const activeProvider = activeProviderKey ? settings?.providers?.[activeProviderKey] : undefined
  const activeDraft = activeProviderKey ? drafts[activeProviderKey] : undefined

  const updateDraft = (providerKey: string, updater: (current: ProviderDraft) => ProviderDraft) => {
    setDrafts((current) => {
      const currentDraft = current[providerKey]
      if (!currentDraft) return current
      return {
        ...current,
        [providerKey]: updater(currentDraft),
      }
    })
  }

  const saveProvider = async () => {
    if (!activeProviderKey || !activeDraft) return

    try {
      await updateMutation.mutateAsync({
        providers: {
          [activeProviderKey]: buildProviderPayload(activeDraft),
        },
      })

      setDrafts((current) => ({
        ...current,
        [activeProviderKey]: {
          ...current[activeProviderKey],
          apiKey: "",
          clearApiKey: false,
        },
      }))

      toast({
        title: "模型接入已保存",
        description: `${providerDisplayNameMap[activeProviderKey] ?? activeProviderKey} 配置已更新。`,
      })
    } catch (error) {
      toast({
        title: "保存失败",
        description: error instanceof Error ? error.message : "模型接入配置更新失败。",
        variant: "destructive",
      })
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-6">
      <Card className="bg-card">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-foreground">
                <span className="text-xl font-semibold text-muted-foreground">Provider 总数：</span>
                <span className="ml-2 text-base font-medium">{providerEntries.length}</span>
                <span className="mx-2 text-base text-muted-foreground">/</span>
                <span className="text-base font-medium text-green-600">{enabledCount}</span>
                <span className="ml-1 text-base text-muted-foreground">已启用</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                最近更新时间：{formatTimestamp(settingsQuery.data?.updatedAt)}
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => settingsQuery.refetch()}
                disabled={settingsQuery.isFetching}
              >
                <RefreshCw className="mr-2 size-4" />
                刷新
              </Button>
              <Button onClick={saveProvider} disabled={!activeProviderKey || updateMutation.isPending}>
                <Save className="mr-2 size-4" />
                保存当前 Provider
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {settingsQuery.error ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            模型接入配置加载失败：{settingsQuery.error instanceof Error ? settingsQuery.error.message : "未知错误"}
          </CardContent>
        </Card>
      ) : null}

      {providerEntries.length === 0 && !settingsQuery.isLoading ? (
        <Card className="bg-card">
          <CardContent className="flex min-h-64 flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="rounded-2xl bg-secondary p-3 text-muted-foreground">
              <Bot className="size-6" />
            </div>
            <div className="space-y-1">
              <div className="text-base font-medium text-foreground">当前没有可配置的 Provider</div>
              <div className="text-sm text-muted-foreground">
                后端返回的 Provider 列表为空，先补齐后端配置源，再回到这里进行管理。
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {providerEntries.length > 0 ? (
        <div className="grid min-h-0 flex-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="flex min-h-0 flex-col bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-medium">Provider 列表</CardTitle>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
              {providerEntries.map(([providerKey, provider]) => {
                const isActive = providerKey === activeProviderKey
                return (
                  <button
                    key={providerKey}
                    type="button"
                    onClick={() => setActiveProviderKey(providerKey)}
                    className={`w-full rounded-xl border p-4 text-left transition-colors ${
                      isActive
                        ? "border-primary bg-primary/5"
                        : "border-border bg-secondary/20 hover:border-primary/30"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium text-foreground">
                          {providerDisplayNameMap[providerKey] ?? providerKey}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">key: {providerKey}</div>
                        <div className="mt-1 text-sm text-muted-foreground">{provider.model || "未配置默认模型"}</div>
                      </div>
                      <Badge variant="secondary" className={provider.enabled ? "bg-success/10 text-success" : ""}>
                        {provider.enabled ? "已启用" : "已停用"}
                      </Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      <span>密钥：{providerKeyStatus(provider)}</span>
                      <span>Endpoint：{provider.endpointPath || "/"}</span>
                    </div>
                  </button>
                )
              })}
            </CardContent>
          </Card>

          <Card className="flex min-h-0 flex-col bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base font-medium">
                    {activeProviderKey ? (providerDisplayNameMap[activeProviderKey] ?? activeProviderKey) : "Provider 详情"}
                  </CardTitle>
                  <div className="mt-1 text-sm text-muted-foreground">
                    调整模型接入参数后立即写回 `/api/settings/agent-api`。
                  </div>
                </div>
                {activeProvider ? (
                  <Badge variant="secondary" className={activeProvider.enabled ? "bg-success/10 text-success" : ""}>
                    {activeProvider.enabled ? "启用中" : "停用中"}
                  </Badge>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
              {activeDraft && activeProvider ? (
                <>
                  <div className="flex items-center justify-between rounded-xl border border-border bg-secondary/20 px-4 py-3">
                    <div>
                      <div className="font-medium text-foreground">启用状态</div>
                      <div className="text-sm text-muted-foreground">
                        关闭后该 Provider 不再进入 Agent 模型选择范围。
                      </div>
                    </div>
                    <Switch
                      checked={activeDraft.enabled}
                      onCheckedChange={(checked) =>
                        updateDraft(activeProviderKey, (current) => ({ ...current, enabled: checked }))
                      }
                    />
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="provider-base-url">Base URL</Label>
                      <Input
                        id="provider-base-url"
                        value={activeDraft.baseUrl}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({ ...current, baseUrl: event.target.value }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="provider-model">默认模型</Label>
                      <Input
                        id="provider-model"
                        value={activeDraft.model}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({ ...current, model: event.target.value }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>请求方式</Label>
                      <Select
                        value={activeDraft.requestPath}
                        onValueChange={(value) =>
                          updateDraft(activeProviderKey, (current) => ({
                            ...current,
                            requestPath: value,
                            endpointPath: value === "custom" ? current.endpointPath : value,
                          }))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="选择请求方式" />
                        </SelectTrigger>
                        <SelectContent>
                          {REQUEST_PATH_OPTIONS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {activeDraft.requestPath === "custom" ? (
                    <div className="space-y-2">
                      <Label htmlFor="provider-endpoint">自定义 Endpoint Path</Label>
                      <Input
                        id="provider-endpoint"
                        placeholder="/custom/path"
                        value={activeDraft.endpointPath}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({
                            ...current,
                            endpointPath: event.target.value,
                          }))
                        }
                      />
                    </div>
                  ) : null}

                  <div className="space-y-2">
                    <Label htmlFor="provider-api-key">API Key</Label>
                    <Input
                      id="provider-api-key"
                      type="password"
                      placeholder={activeProvider.hasApiKey ? "留空表示保持现有密钥" : "输入新的 API Key"}
                      value={activeDraft.apiKey}
                      onChange={(event) =>
                        updateDraft(activeProviderKey, (current) => ({ ...current, apiKey: event.target.value }))
                      }
                    />
                    <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <KeyRound className="size-4" />
                        当前状态：{maskSummary(activeProvider)}
                      </span>
                      <label className="inline-flex items-center gap-2">
                        <Checkbox
                          checked={activeDraft.clearApiKey}
                          onCheckedChange={(checked) =>
                            updateDraft(activeProviderKey, (current) => ({
                              ...current,
                              clearApiKey: checked === true,
                            }))
                          }
                        />
                        清空已保存密钥
                      </label>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="provider-notes">备注</Label>
                    <Textarea
                      id="provider-notes"
                      value={activeDraft.notes}
                      onChange={(event) =>
                        updateDraft(activeProviderKey, (current) => ({ ...current, notes: event.target.value }))
                      }
                      />
                    </div>

                </>
              ) : (
                <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                  选择左侧 Provider 后查看并编辑详情。
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
