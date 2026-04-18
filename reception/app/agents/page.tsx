"use client"

import { useEffect, useMemo, useState } from "react"
import { AgentAvatar } from "@/components/agent-avatar"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useBrainSkills } from "@/hooks/use-brain-skills"
import { useAuth } from "@/hooks/use-auth"
import {
  useAgents,
  useCreateAgent,
  useReloadAgent,
  useUpdateAgentConfig,
} from "@/hooks/use-agents"
import { useAgentApiSettings } from "@/hooks/use-settings"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"
import { AGENT_TYPE_OPTIONS, getAgentTypeLabel } from "@/types"
import type { Agent, AgentBoundSkill, AgentConfigRequest, BrainSkillItem } from "@/types"
import { Clock3, Plus, Search, Settings2 } from "lucide-react"

const statusLabels = {
  idle: "空闲",
  running: "运行中",
  waiting: "待心跳",
  busy: "忙碌",
  degraded: "降级",
  offline: "离线",
  maintenance: "维护中",
  error: "错误",
}

const statusColors = {
  idle: "bg-secondary text-muted-foreground",
  running: "bg-success/20 text-success",
  waiting: "bg-secondary text-muted-foreground",
  busy: "bg-success/20 text-success",
  degraded: "bg-warning/20 text-warning-foreground",
  offline: "bg-secondary text-muted-foreground",
  maintenance: "bg-primary/15 text-primary",
  error: "bg-destructive/15 text-destructive",
}

const runtimeLabels = {
  online: "在线",
  degraded: "降级",
  offline: "离线",
  unknown: "待心跳",
}

const runtimeColors = {
  online: "bg-success/15 text-success",
  degraded: "bg-warning/20 text-warning-foreground",
  offline: "bg-secondary text-muted-foreground",
  unknown: "bg-secondary text-muted-foreground",
}

type ModelOption = {
  value: string
  providerKey: string
  providerLabel: string
  model: string
}

type AgentFormState = {
  name: string
  description: string
  type: string
  enabled: boolean
  selectedModel: string
  selectedSkillIds: string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function normalizeSkillIds(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))]
}

function resolveAgentBoundSkillIds(agent: Agent | null) {
  if (!agent) return []

  const directIds = normalizeSkillIds(agent.boundSkillIds)
  if (directIds.length > 0) return directIds

  const directSkillIds = normalizeSkillIds((agent.boundSkills ?? []).map((skill) => skill.id))
  if (directSkillIds.length > 0) return directSkillIds

  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const runtime = snapshot && isRecord(snapshot.runtime) ? snapshot.runtime : null

  return normalizeSkillIds(
    runtime?.skillIds ??
      runtime?.skill_ids ??
      runtime?.boundSkillIds ??
      runtime?.bound_skill_ids ??
      snapshot?.skillIds ??
      snapshot?.skill_ids,
  )
}

function resolveAgentBoundSkills(agent: Agent, skillMap: Map<string, BrainSkillItem>): AgentBoundSkill[] {
  const directSkills =
    agent.boundSkills?.filter((skill): skill is AgentBoundSkill => Boolean(skill?.id && skill?.name)) ?? []
  if (directSkills.length > 0) {
    return directSkills
  }

  return resolveAgentBoundSkillIds(agent).map((skillId) => {
    const skill = skillMap.get(skillId)
    return {
      id: skillId,
      name: skill?.name ?? skillId,
      fileName: skill?.fileName ?? null,
      format: skill?.format ?? null,
      description: skill?.description ?? null,
      tags: skill?.tags ?? [],
    }
  })
}

function buildModelValue(providerKey: string, model: string) {
  return `${providerKey}::${model}`
}

function parseModelValue(value: string) {
  const [providerKey, ...modelParts] = value.split("::")
  return {
    providerKey: providerKey?.trim() ?? "",
    model: modelParts.join("::").trim(),
  }
}

function defaultFormState(agent: Agent | null, modelOptions: ModelOption[]): AgentFormState {
  const currentValue =
    agent?.modelBinding?.providerKey && agent.modelBinding.model
      ? buildModelValue(agent.modelBinding.providerKey, agent.modelBinding.model)
      : ""
  const fallbackValue = modelOptions[0]?.value ?? ""
  const selectedModel = modelOptions.some((item) => item.value === currentValue)
    ? currentValue
    : fallbackValue

  return {
    name: agent?.name ?? "",
    description: agent?.description ?? "",
    type: agent?.type ?? "default",
    enabled: agent?.enabled ?? true,
    selectedModel,
    selectedSkillIds: resolveAgentBoundSkillIds(agent),
  }
}

function providerLabel(providerKey: string) {
  if (providerKey === "openapi") return "OpenAPI Compatible"
  if (providerKey === "openai") return "OpenAI"
  if (providerKey === "deepseek") return "DeepSeek"
  if (providerKey === "minimax") return "MiniMax"
  return providerKey.toUpperCase()
}

function buildAgentTypeOptions(currentType: string) {
  if (!currentType.trim() || AGENT_TYPE_OPTIONS.some((item) => item.value === currentType)) {
    return AGENT_TYPE_OPTIONS
  }

  return [
    {
      value: currentType,
      label: `${getAgentTypeLabel(currentType)}（当前值）`,
    },
    ...AGENT_TYPE_OPTIONS,
  ]
}

function AgentConfigDialog({
  open,
  agent,
  modelOptions,
  brainSkills,
  brainSkillsLoading,
  brainSkillsError,
  canEdit,
  isSaving,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  agent: Agent | null
  modelOptions: ModelOption[]
  brainSkills: BrainSkillItem[]
  brainSkillsLoading: boolean
  brainSkillsError: Error | null
  canEdit: boolean
  isSaving: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: AgentConfigRequest) => Promise<void>
}) {
  const [form, setForm] = useState<AgentFormState>(() => defaultFormState(agent, modelOptions))
  const agentTypeOptions = useMemo(() => buildAgentTypeOptions(form.type), [form.type])
  const selectedSkillIds = useMemo(() => new Set(form.selectedSkillIds), [form.selectedSkillIds])

  useEffect(() => {
    if (!open) return
    setForm(defaultFormState(agent, modelOptions))
  }, [agent, modelOptions, open])

  const handleSubmit = async () => {
    const name = form.name.trim()
    if (!name) {
      toast({
        title: "名称不能为空",
        description: "请先填写 Agent 名称。",
      })
      return
    }

    if (!form.selectedModel.trim()) {
      toast({
        title: "请选择模型",
        description: "请从项目内已启用模型中选择一个。",
      })
      return
    }

    const { providerKey, model } = parseModelValue(form.selectedModel)
    await onSubmit({
      name,
      description: form.description.trim(),
      type: form.type,
      enabled: form.enabled,
      providerKey,
      model,
      skillIds: form.selectedSkillIds,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{agent ? `${agent.name} 配置` : "新增 Agent 配置"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="agent-name">Agent 名称</Label>
            <Input
              id="agent-name"
              value={form.name}
              disabled={!canEdit || isSaving}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-type">Agent 类型</Label>
            <Select
              value={form.type}
              disabled={!canEdit || isSaving}
              onValueChange={(value) => setForm((current) => ({ ...current, type: value }))}
            >
              <SelectTrigger id="agent-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {agentTypeOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-model">项目内启用模型</Label>
            <Select
              value={form.selectedModel}
              disabled={!canEdit || isSaving || modelOptions.length === 0}
              onValueChange={(value) => setForm((current) => ({ ...current, selectedModel: value }))}
            >
              <SelectTrigger id="agent-model">
                <SelectValue placeholder="选择项目内启用模型" />
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.providerLabel} · {item.model}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-description">介绍</Label>
            <Textarea
              id="agent-description"
              rows={3}
              value={form.description}
              disabled={!canEdit || isSaving}
              onChange={(event) =>
                setForm((current) => ({ ...current, description: event.target.value }))
              }
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>绑定 Skill</Label>
              <span className="text-xs text-muted-foreground">已选 {form.selectedSkillIds.length}</span>
            </div>

            {brainSkillsLoading ? (
              <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
                正在加载本地 Skill...
              </div>
            ) : brainSkillsError ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                本地 Skill 加载失败：{brainSkillsError.message}
              </div>
            ) : brainSkills.length === 0 ? (
              <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
                暂未上传本地 Skill
              </div>
            ) : (
              <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-border bg-secondary/10 p-3">
                {brainSkills.map((skill) => {
                  const checked = selectedSkillIds.has(skill.id)
                  const meta = [skill.fileName, skill.format].filter(Boolean).join(" · ")

                  return (
                    <label
                      key={skill.id}
                      htmlFor={`agent-skill-${skill.id}`}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-lg border border-transparent px-3 py-2 transition-colors",
                        checked ? "bg-card shadow-sm ring-1 ring-border" : "hover:bg-card/70",
                        (!canEdit || isSaving) && "cursor-not-allowed opacity-70",
                      )}
                    >
                      <Checkbox
                        id={`agent-skill-${skill.id}`}
                        checked={checked}
                        disabled={!canEdit || isSaving}
                        onCheckedChange={(nextChecked) =>
                          setForm((current) => ({
                            ...current,
                            selectedSkillIds:
                              nextChecked === true
                                ? [...new Set([...current.selectedSkillIds, skill.id])]
                                : current.selectedSkillIds.filter((item) => item !== skill.id),
                          }))
                        }
                      />
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-foreground">{skill.name}</div>
                          {meta ? (
                            <div className="truncate text-xs text-muted-foreground">{meta}</div>
                          ) : null}
                        </div>
                        {skill.tags.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {skill.tags.slice(0, 4).map((tag) => (
                              <Badge key={`${skill.id}-${tag}`} variant="secondary" className="text-[11px]">
                                {tag}
                              </Badge>
                            ))}
                            {skill.tags.length > 4 ? (
                              <Badge variant="secondary" className="text-[11px] text-muted-foreground">
                                +{skill.tags.length - 4}
                              </Badge>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/20 px-4 py-3">
            <div>
              <div className="text-sm font-medium text-foreground">启用状态</div>
              <div className="text-xs text-muted-foreground">
                {form.enabled ? "当前 Agent 已启用" : "当前 Agent 已停用"}
              </div>
            </div>
            <Switch
              checked={form.enabled}
              disabled={!canEdit || isSaving}
              onCheckedChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  enabled: checked,
                }))
              }
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={isSaving} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!canEdit || isSaving || modelOptions.length === 0} onClick={() => void handleSubmit()}>
            {isSaving ? "保存中..." : "保存配置"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AgentCard({
  agent,
  boundSkills,
  onConfigure,
  onReload,
}: {
  agent: Agent
  boundSkills: AgentBoundSkill[]
  onConfigure: (agent: Agent) => void
  onReload: (agentId: string) => Promise<void>
}) {
  const runtimeStatus = agent.runtimeStatus ?? "unknown"
  const visibleSkills = boundSkills.slice(0, 3)
  const hiddenSkillCount = Math.max(boundSkills.length - visibleSkills.length, 0)

  return (
    <Card className={cn("bg-card", !agent.enabled && "opacity-60")}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <AgentAvatar
              name={agent.name}
              type={agent.type}
              status={agent.status}
              size="lg"
            />
            <div>
              <CardTitle className="text-base">{agent.name}</CardTitle>
              <p className="text-xs text-muted-foreground">{agent.description}</p>
            </div>
          </div>
          <Switch checked={agent.enabled} disabled />
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className={cn("text-xs", statusColors[agent.status])}>
              {statusLabels[agent.status]}
            </Badge>
            <Badge
              variant="secondary"
              className={cn("text-xs", runtimeColors[runtimeStatus])}
            >
              {runtimeLabels[runtimeStatus]}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">最后活跃: {agent.lastActive}</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-secondary/50 p-3">
            <div className="text-xs text-muted-foreground">当前模型</div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.modelBinding?.model ?? "未配置"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {agent.modelBinding?.providerLabel ?? "未绑定 Provider"}
            </div>
          </div>

          <div className="rounded-lg bg-secondary/50 p-3">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock3 className="size-3" />
              平均响应
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.avgResponseTime || "--"}
            </div>
          </div>
        </div>

        <div className="rounded-lg bg-secondary/50 p-3">
          <div className="text-xs text-muted-foreground">已绑定 Skill</div>
          {boundSkills.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {visibleSkills.map((skill) => (
                <Badge key={`${agent.id}-${skill.id}`} variant="secondary" className="text-xs">
                  {skill.name}
                </Badge>
              ))}
              {hiddenSkillCount > 0 ? (
                <Badge variant="secondary" className="text-xs text-muted-foreground">
                  +{hiddenSkillCount}
                </Badge>
              ) : null}
            </div>
          ) : (
            <div className="mt-1 text-sm text-muted-foreground">未绑定</div>
          )}
        </div>

        <div className="flex gap-2">
          <Button variant="secondary" size="sm" className="flex-1" onClick={() => onConfigure(agent)}>
            <Settings2 className="mr-2 size-4" />
            Agent 配置
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => void onReload(agent.id)}
          >
            热重载
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function AgentsPage() {
  const { hasPermission } = useAuth()
  const [searchQuery, setSearchQuery] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const { data, isLoading, error } = useAgents()
  const {
    data: brainSkillsData,
    isLoading: brainSkillsLoading,
    error: brainSkillsQueryError,
  } = useBrainSkills()
  const { data: agentApiSettings } = useAgentApiSettings()
  const reloadAgentMutation = useReloadAgent()
  const createAgentMutation = useCreateAgent()
  const updateAgentConfigMutation = useUpdateAgentConfig()
  const agents = data?.items ?? []
  const brainSkills = brainSkillsData?.items ?? []
  const brainSkillsError = brainSkillsQueryError instanceof Error ? brainSkillsQueryError : null
  const canEditConfiguration = hasPermission("agents:reload")
  const brainSkillMap = useMemo(
    () => new Map(brainSkills.map((skill) => [skill.id, skill])),
    [brainSkills],
  )

  const modelOptions = useMemo<ModelOption[]>(() => {
    const providers = agentApiSettings?.settings?.providers ?? {}
    return Object.entries(providers)
      .filter(([, provider]) => provider.enabled && provider.model.trim())
      .map(([providerKey, provider]) => ({
        value: buildModelValue(providerKey, provider.model.trim()),
        providerKey,
        providerLabel: providerLabel(providerKey),
        model: provider.model.trim(),
      }))
  }, [agentApiSettings?.settings?.providers])

  const filteredAgents = agents.filter((agent) => {
    const keyword = searchQuery.trim().toLowerCase()
    if (!keyword) return true
    return (
      agent.name.toLowerCase().includes(keyword) ||
      agent.description.toLowerCase().includes(keyword) ||
      String(agent.modelBinding?.model ?? "").toLowerCase().includes(keyword) ||
      resolveAgentBoundSkills(agent, brainSkillMap).some((skill) =>
        skill.name.toLowerCase().includes(keyword),
      )
    )
  })

  const activeCount = agents.filter((item) => item.enabled).length
  const runningCount = agents.filter((item) => item.status === "running").length
  const onlineCount = agents.filter((item) => (item.runtimeStatus ?? "unknown") === "online").length

  const handleReload = async (agentId: string) => {
    try {
      const result = await reloadAgentMutation.mutateAsync(agentId)
      toast({
        title: "Agent 已热重载",
        description: `${result.agent.name} 已重新加载配置。`,
      })
    } catch (reloadError) {
      toast({
        title: "热重载失败",
        description: reloadError instanceof Error ? reloadError.message : "未知错误",
      })
    }
  }

  const handleSaveAgent = async (payload: AgentConfigRequest) => {
    try {
      if (selectedAgent) {
        const result = await updateAgentConfigMutation.mutateAsync({
          agentId: selectedAgent.id,
          payload,
        })
        toast({
          title: "Agent 配置已更新",
          description: `${result.agent.name} 已绑定 ${result.agent.modelBinding?.model ?? "--"}`,
        })
      } else {
        const result = await createAgentMutation.mutateAsync(payload)
        toast({
          title: "Agent 已创建",
          description: `${result.agent.name} 已加入当前项目。`,
        })
      }
      setDialogOpen(false)
      setSelectedAgent(null)
    } catch (saveError) {
      toast({
        title: "保存失败",
        description: saveError instanceof Error ? saveError.message : "未知错误",
      })
    }
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agent 运行管理</h1>
          <p className="text-sm text-muted-foreground">查看 Agent 状态，并直接配置绑定模型</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>活跃: {activeCount}</span>
            <span>|</span>
            <span className="text-success">运行中: {runningCount}</span>
            <span>|</span>
            <span className="text-success">在线: {onlineCount}</span>
          </div>
          <Button
            size="sm"
            disabled={!canEditConfiguration || modelOptions.length === 0}
            onClick={() => {
              setSelectedAgent(null)
              setDialogOpen(true)
            }}
          >
            <Plus className="mr-2 size-4" />
            新增 Agent 配置
          </Button>
        </div>
      </div>

      {modelOptions.length === 0 ? (
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-foreground">
          当前没有可选的启用模型，请先到“模型接入”页面启用模型。
        </div>
      ) : null}

      <div className="mb-4 flex items-center gap-4">
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索 Agent..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="bg-secondary pl-10"
          />
        </div>
      </div>

      {error ? (
        <div className="mb-4 text-sm text-destructive">
          Agent 数据加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      <Tabs defaultValue="all" className="flex-1">
        <TabsList className="mb-4 bg-secondary">
          <TabsTrigger value="all">全部 ({agents.length})</TabsTrigger>
          <TabsTrigger value="active">活跃 ({agents.filter((a) => a.enabled).length})</TabsTrigger>
          <TabsTrigger value="inactive">停用 ({agents.filter((a) => !a.enabled).length})</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-0">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                boundSkills={resolveAgentBoundSkills(agent, brainSkillMap)}
                onConfigure={(nextAgent) => {
                  setSelectedAgent(nextAgent)
                  setDialogOpen(true)
                }}
                onReload={handleReload}
              />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="active" className="mt-0">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents
              .filter((agent) => agent.enabled)
              .map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  boundSkills={resolveAgentBoundSkills(agent, brainSkillMap)}
                  onConfigure={(nextAgent) => {
                    setSelectedAgent(nextAgent)
                    setDialogOpen(true)
                  }}
                  onReload={handleReload}
                />
              ))}
          </div>
        </TabsContent>

        <TabsContent value="inactive" className="mt-0">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents
              .filter((agent) => !agent.enabled)
              .map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  boundSkills={resolveAgentBoundSkills(agent, brainSkillMap)}
                  onConfigure={(nextAgent) => {
                    setSelectedAgent(nextAgent)
                    setDialogOpen(true)
                  }}
                  onReload={handleReload}
                />
              ))}
          </div>
        </TabsContent>
      </Tabs>

      {isLoading ? (
        <div className="pt-4 text-sm text-muted-foreground">正在加载 Agent 数据...</div>
      ) : null}

      <AgentConfigDialog
        open={dialogOpen}
        agent={selectedAgent}
        modelOptions={modelOptions}
        brainSkills={brainSkills}
        brainSkillsLoading={brainSkillsLoading}
        brainSkillsError={brainSkillsError}
        canEdit={canEditConfiguration}
        isSaving={createAgentMutation.isPending || updateAgentConfigMutation.isPending}
        onOpenChange={(open) => {
          setDialogOpen(open)
          if (!open) {
            setSelectedAgent(null)
          }
        }}
        onSubmit={handleSaveAgent}
      />
    </div>
  )
}
