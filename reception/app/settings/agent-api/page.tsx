"use client"

import { useEffect, useMemo, useState } from "react"
import { Bot, KeyRound, RefreshCw, Save } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useAgentApiSettings, useUpdateAgentApiSettings } from "@/hooks/use-settings"
import { toast } from "@/hooks/use-toast"
import type {
  AgentApiProviderSettings,
  AgentApiSettings,
  UpdateAgentApiProviderSettingsRequest,
} from "@/types"

type ProviderDraft = {
  enabled: boolean
  baseUrl: string
  model: string
  organizationId: string
  projectId: string
  groupId: string
  endpointPath: string
  notes: string
  apiKey: string
  clearApiKey: boolean
}

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
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

  return {
    enabled: draft.enabled,
    baseUrl: draft.baseUrl.trim(),
    model: draft.model.trim(),
    organizationId: draft.organizationId.trim(),
    projectId: draft.projectId.trim(),
    groupId: draft.groupId.trim(),
    endpointPath: draft.endpointPath.trim(),
    notes: draft.notes.trim(),
    apiKey: apiKey || undefined,
    clearApiKey: draft.clearApiKey || undefined,
  }
}

function maskSummary(provider: AgentApiProviderSettings) {
  if (!provider.hasApiKey) return "未配置"
  return provider.apiKeyMasked || "已配置"
}

export default function AgentApiSettingsPage() {
  const settingsQuery = useAgentApiSettings()
  const updateMutation = useUpdateAgentApiSettings()
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({})
  const [activeProviderKey, setActiveProviderKey] = useState<string>("")

  const settings = settingsQuery.data?.settings
  const providerEntries = Object.entries(settings?.providers ?? {})
  const providerKeys = useMemo(() => providerEntries.map(([providerKey]) => providerKey), [providerEntries])
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
        description: `${activeProviderKey} 配置已更新。`,
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
    <div className="space-y-6 p-6">
      <Card className="bg-card">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base font-medium">模型接入</CardTitle>
              <div className="mt-1 text-sm text-muted-foreground">
                统一管理 Provider、模型、Endpoint 和密钥状态，模型接入配置只保留当前这一处入口。
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
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3">
            <div className="text-xs text-muted-foreground">Provider 总数</div>
            <div className="mt-1 text-2xl font-semibold text-foreground">{providerEntries.length}</div>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3">
            <div className="text-xs text-muted-foreground">已启用</div>
            <div className="mt-1 text-2xl font-semibold text-foreground">{enabledCount}</div>
          </div>
          <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3">
            <div className="text-xs text-muted-foreground">最近更新时间</div>
            <div className="mt-1 text-sm font-medium leading-6 text-foreground">
              {formatTimestamp(settingsQuery.data?.updatedAt)}
            </div>
          </div>
        </CardContent>
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
        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-medium">Provider 列表</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
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
                        <div className="font-medium text-foreground">{providerKey}</div>
                        <div className="mt-1 text-sm text-muted-foreground">{provider.model || "未配置默认模型"}</div>
                      </div>
                      <Badge variant="secondary" className={provider.enabled ? "bg-success/10 text-success" : ""}>
                        {provider.enabled ? "已启用" : "已停用"}
                      </Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      <span>密钥：{maskSummary(provider)}</span>
                      <span>Endpoint：{provider.endpointPath || "/"}</span>
                    </div>
                  </button>
                )
              })}
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base font-medium">{activeProviderKey || "Provider 详情"}</CardTitle>
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
            <CardContent className="space-y-6">
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
                      <Label htmlFor="provider-endpoint">Endpoint Path</Label>
                      <Input
                        id="provider-endpoint"
                        value={activeDraft.endpointPath}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({
                            ...current,
                            endpointPath: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="provider-org-id">Organization ID</Label>
                      <Input
                        id="provider-org-id"
                        value={activeDraft.organizationId}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({
                            ...current,
                            organizationId: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="provider-project-id">Project ID</Label>
                      <Input
                        id="provider-project-id"
                        value={activeDraft.projectId}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({
                            ...current,
                            projectId: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="provider-group-id">Group ID</Label>
                      <Input
                        id="provider-group-id"
                        value={activeDraft.groupId}
                        onChange={(event) =>
                          updateDraft(activeProviderKey, (current) => ({ ...current, groupId: event.target.value }))
                        }
                      />
                    </div>
                  </div>

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
