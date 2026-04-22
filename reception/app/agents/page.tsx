"use client"

import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react"
import { AgentAvatar } from "@/components/agent-avatar"
import { Checkbox } from "@/components/ui/checkbox"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useBrainSkills } from "@/hooks/use-brain-skills"
import { useAuth } from "@/hooks/use-auth"
import {
  useAgents,
  useAgentMcpTools,
  useCreateAgent,
  useDeleteAgent,
  useReloadAgent,
  useSetAgentEnabled,
  useUpdateAgentConfig,
} from "@/hooks/use-agents"
import { useWorkflows } from "@/hooks/use-workflows"
import { useAgentApiSettings } from "@/hooks/use-settings"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"
import type {
  Agent,
  AgentBindableTool,
  AgentBoundSkill,
  AgentBoundTool,
  AgentConfigRequest,
  BrainSkillItem,
  Workflow,
} from "@/types"
import { Plus, Search, Trash2 } from "lucide-react"

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
  selectedWorkflowId: string
  selectedSkillIds: string[]
  selectedToolIds: string[]
}

type WorkflowOption = {
  value: string
  label: string
  description: string
}

type AgentConfigBuildResult =
  | {
      payload: AgentConfigRequest
      error?: never
    }
  | {
      payload?: never
      error: {
        title: string
        description: string
      }
    }

type AgentFilterMode = "all" | "active" | "inactive"

const UNBOUND_WORKFLOW_VALUE = "__unbound__"

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function normalizeIdentifierList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))]
}

function resolveAgentBoundSkillIds(agent: Agent | null) {
  if (!agent) return []

  const directIds = normalizeIdentifierList(agent.boundSkillIds)
  if (directIds.length > 0) return directIds

  const directSkillIds = normalizeIdentifierList((agent.boundSkills ?? []).map((skill) => skill.id))
  if (directSkillIds.length > 0) return directSkillIds

  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const runtime = snapshot && isRecord(snapshot.runtime) ? snapshot.runtime : null

  return normalizeIdentifierList(
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

function resolveAgentBoundToolIds(agent: Agent | null) {
  if (!agent) return []

  const directIds = normalizeIdentifierList(agent.boundToolIds)
  if (directIds.length > 0) return directIds

  const directToolIds = normalizeIdentifierList((agent.boundTools ?? []).map((tool) => tool.id))
  if (directToolIds.length > 0) return directToolIds

  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const runtime = snapshot && isRecord(snapshot.runtime) ? snapshot.runtime : null
  const toolBinding = runtime && isRecord(runtime.toolBinding) ? runtime.toolBinding : null
  const legacyToolBinding = runtime && isRecord(runtime.tool_binding) ? runtime.tool_binding : null
  const agentDoc = snapshot && isRecord(snapshot.agent) ? snapshot.agent : null

  return normalizeIdentifierList(
    toolBinding?.toolIds ??
      toolBinding?.tool_ids ??
      legacyToolBinding?.toolIds ??
      legacyToolBinding?.tool_ids ??
      runtime?.boundToolIds ??
      runtime?.bound_tool_ids ??
      agentDoc?.toolIds ??
      agentDoc?.tool_ids ??
      snapshot?.toolIds ??
      snapshot?.tool_ids,
  )
}

function resolveAgentBoundTools(agent: Agent, toolMap: Map<string, AgentBindableTool>): AgentBoundTool[] {
  const directTools =
    agent.boundTools?.filter((tool): tool is AgentBoundTool => Boolean(tool?.id && tool?.name)) ?? []
  if (directTools.length > 0) {
    return directTools
  }

  return resolveAgentBoundToolIds(agent).map((toolId) => {
    const tool = toolMap.get(toolId)
    return {
      id: toolId,
      name: tool?.name ?? toolId,
      type: tool?.type ?? "mcp",
      description: tool?.description ?? null,
      source: tool?.source ?? null,
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
    selectedWorkflowId: agent?.agentWorkflowId ?? agent?.agent_workflow_id ?? UNBOUND_WORKFLOW_VALUE,
    selectedSkillIds: resolveAgentBoundSkillIds(agent),
    selectedToolIds: resolveAgentBoundToolIds(agent),
  }
}

function providerLabel(providerKey: string) {
  if (providerKey === "openapi") return "OpenAPI Compatible"
  if (providerKey === "openai") return "OpenAI"
  if (providerKey === "deepseek") return "DeepSeek"
  if (providerKey === "minimax") return "MiniMax"
  return providerKey.toUpperCase()
}

function buildAgentConfigSyncKey(agent: Agent | null) {
  if (!agent) return "agent:null"

  return JSON.stringify({
    id: agent.id,
    name: agent.name,
    description: agent.description,
    type: agent.type,
    enabled: agent.enabled,
    providerKey: agent.modelBinding?.providerKey ?? "",
    model: agent.modelBinding?.model ?? "",
    workflowId: resolveAgentWorkflowId(agent) ?? "",
    skillIds: resolveAgentBoundSkillIds(agent),
    toolIds: resolveAgentBoundToolIds(agent),
  })
}

function buildAgentConfigPayload(form: AgentFormState, agent: Agent | null): AgentConfigBuildResult {
  const name = form.name.trim()
  if (!name) {
    return {
      error: {
        title: "名称不能为空",
        description: "请先填写 Agent 名称。",
      },
    }
  }

  if (!form.selectedModel.trim()) {
    return {
      error: {
        title: "请选择模型",
        description: "请从项目内已启用模型中选择一个。",
      },
    }
  }

  const selectedWorkflowId =
    form.selectedWorkflowId === UNBOUND_WORKFLOW_VALUE ? "" : form.selectedWorkflowId.trim()

  if (form.enabled && !selectedWorkflowId) {
    return {
      error: {
        title: "请选择绑定工作流",
        description: "启用 Agent 前需要先绑定一个工作流。",
      },
    }
  }

  const { providerKey, model } = parseModelValue(form.selectedModel)
  const existingAgentWorkflowId = agent?.agentWorkflowId ?? agent?.agent_workflow_id ?? null
  const existingInputContract = agent?.inputContract ?? agent?.input_contract ?? {}
  const existingOutputContract = agent?.outputContract ?? agent?.output_contract ?? {}
  const existingContractVersion = agent?.contractVersion ?? agent?.contract_version ?? null
  const workflowChanged = (existingAgentWorkflowId ?? "") !== selectedWorkflowId

  return {
    payload: {
      name,
      description: form.description.trim(),
      type: form.type,
      enabled: form.enabled,
      providerKey,
      model,
      skillIds: form.selectedSkillIds,
      toolIds: form.selectedToolIds,
      ...(selectedWorkflowId
        ? {
            agentWorkflowId: selectedWorkflowId,
            inputContract: workflowChanged ? {} : existingInputContract,
            outputContract: workflowChanged ? {} : existingOutputContract,
            contractVersion: workflowChanged ? null : existingContractVersion,
          }
        : {
            agentWorkflowId: null,
            inputContract: null,
            outputContract: null,
            contractVersion: null,
          }),
    } satisfies AgentConfigRequest,
  }
}

function AgentConfigFields({
  form,
  setForm,
  modelOptions,
  workflowOptions,
  workflowsLoading,
  workflowsError,
  brainSkills,
  brainSkillsLoading,
  brainSkillsError,
  mcpTools,
  mcpToolsLoading,
  mcpToolsError,
  canEdit,
  isSaving,
  idPrefix,
  showEnabledField = true,
}: {
  form: AgentFormState
  setForm: Dispatch<SetStateAction<AgentFormState>>
  modelOptions: ModelOption[]
  workflowOptions: WorkflowOption[]
  workflowsLoading: boolean
  workflowsError: Error | null
  brainSkills: BrainSkillItem[]
  brainSkillsLoading: boolean
  brainSkillsError: Error | null
  mcpTools: AgentBindableTool[]
  mcpToolsLoading: boolean
  mcpToolsError: Error | null
  canEdit: boolean
  isSaving: boolean
  idPrefix: string
  showEnabledField?: boolean
}) {
  const selectedSkillIds = useMemo(() => new Set(form.selectedSkillIds), [form.selectedSkillIds])
  const selectedToolIds = useMemo(() => new Set(form.selectedToolIds), [form.selectedToolIds])

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-name`}>Agent 名称</Label>
        <Input
          id={`${idPrefix}-name`}
          value={form.name}
          disabled={!canEdit || isSaving}
          onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
        />
      </div>

      <div className={cn("grid gap-3", showEnabledField ? "sm:grid-cols-[minmax(0,1fr)_220px]" : "sm:grid-cols-1")}>
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-model`}>项目内启用模型</Label>
          <Select
            value={form.selectedModel}
            disabled={!canEdit || isSaving || modelOptions.length === 0}
            onValueChange={(value) => setForm((current) => ({ ...current, selectedModel: value }))}
          >
            <SelectTrigger id={`${idPrefix}-model`}>
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

        {showEnabledField ? (
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-enabled`}>启用状态</Label>
            <div className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3">
              <span className="text-sm text-muted-foreground">
                {form.enabled ? "当前 Agent 已启用" : "当前 Agent 已停用"}
              </span>
              <Switch
                id={`${idPrefix}-enabled`}
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
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-workflow`}>绑定工作流</Label>
        {workflowsLoading ? (
          <div className="rounded-md border border-border bg-secondary/20 px-3 py-2 text-sm text-muted-foreground">
            正在加载工作流...
          </div>
        ) : workflowsError ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            工作流加载失败：{workflowsError.message}
          </div>
        ) : workflowOptions.length === 0 ? (
          <div className="rounded-md border border-border bg-secondary/20 px-3 py-2 text-sm text-muted-foreground">
            当前没有可绑定的工作流
          </div>
        ) : (
          <Select
            value={form.selectedWorkflowId}
            disabled={!canEdit || isSaving}
            onValueChange={(value) => setForm((current) => ({ ...current, selectedWorkflowId: value }))}
          >
            <SelectTrigger id={`${idPrefix}-workflow`}>
              <SelectValue placeholder="选择工作流" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={UNBOUND_WORKFLOW_VALUE}>不绑定工作流</SelectItem>
              {workflowOptions.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <p className="text-xs text-muted-foreground">
          当前 Agent 的执行主链会按这里绑定的工作流进入轮转。
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-description`}>介绍</Label>
        <Textarea
          id={`${idPrefix}-description`}
          rows={3}
          value={form.description}
          disabled={!canEdit || isSaving}
          onChange={(event) =>
            setForm((current) => ({ ...current, description: event.target.value }))
          }
        />
      </div>

      <div className="space-y-2">
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
              const tags = skill.tags ?? []

              return (
                <label
                  key={skill.id}
                  htmlFor={`${idPrefix}-skill-${skill.id}`}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-lg border border-transparent px-3 py-2 transition-colors",
                    checked ? "bg-card shadow-sm ring-1 ring-border" : "hover:bg-card/70",
                    (!canEdit || isSaving) && "cursor-not-allowed opacity-70",
                  )}
                >
                  <Checkbox
                    id={`${idPrefix}-skill-${skill.id}`}
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
                    {tags.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {tags.slice(0, 4).map((tag) => (
                          <Badge key={`${skill.id}-${tag}`} variant="secondary" className="text-[11px]">
                            {tag}
                          </Badge>
                        ))}
                        {tags.length > 4 ? (
                          <Badge variant="secondary" className="text-[11px] text-muted-foreground">
                            +{tags.length - 4}
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

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>MCP 绑定</Label>
          <span className="text-xs text-muted-foreground">已选 {form.selectedToolIds.length}</span>
        </div>

        {mcpToolsLoading ? (
          <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
            正在加载 MCP 工具目录...
          </div>
        ) : mcpToolsError ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            MCP 工具加载失败：{mcpToolsError.message}
          </div>
        ) : mcpTools.length === 0 ? (
          <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
            当前没有可绑定的 MCP 工具
          </div>
        ) : (
          <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-border bg-secondary/10 p-3">
            {mcpTools.map((tool) => {
              const checked = selectedToolIds.has(tool.id)
              const meta = [tool.source, tool.type.toUpperCase()].filter(Boolean).join(" · ")

              return (
                <label
                  key={tool.id}
                  htmlFor={`${idPrefix}-tool-${tool.id}`}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-lg border border-transparent px-3 py-2 transition-colors",
                    checked ? "bg-card shadow-sm ring-1 ring-border" : "hover:bg-card/70",
                    (!canEdit || isSaving) && "cursor-not-allowed opacity-70",
                  )}
                >
                  <Checkbox
                    id={`${idPrefix}-tool-${tool.id}`}
                    checked={checked}
                    disabled={!canEdit || isSaving}
                    onCheckedChange={(nextChecked) =>
                      setForm((current) => ({
                        ...current,
                        selectedToolIds:
                          nextChecked === true
                            ? [...new Set([...current.selectedToolIds, tool.id])]
                            : current.selectedToolIds.filter((item) => item !== tool.id),
                      }))
                    }
                  />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="truncate text-sm font-medium text-foreground">{tool.name}</div>
                    {meta ? (
                      <div className="truncate text-xs text-muted-foreground">{meta}</div>
                    ) : null}
                    {tool.description ? (
                      <div className="text-xs text-muted-foreground">{tool.description}</div>
                    ) : null}
                  </div>
                </label>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function AgentConfigDialog({
  open,
  agent,
  modelOptions,
  workflowOptions,
  workflowsLoading,
  workflowsError,
  brainSkills,
  brainSkillsLoading,
  brainSkillsError,
  mcpTools,
  mcpToolsLoading,
  mcpToolsError,
  canEdit,
  isSaving,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  agent: Agent | null
  modelOptions: ModelOption[]
  workflowOptions: WorkflowOption[]
  workflowsLoading: boolean
  workflowsError: Error | null
  brainSkills: BrainSkillItem[]
  brainSkillsLoading: boolean
  brainSkillsError: Error | null
  mcpTools: AgentBindableTool[]
  mcpToolsLoading: boolean
  mcpToolsError: Error | null
  canEdit: boolean
  isSaving: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: AgentConfigRequest) => Promise<void>
}) {
  const [form, setForm] = useState<AgentFormState>(() => defaultFormState(agent, modelOptions))

  useEffect(() => {
    if (!open) return
    setForm(defaultFormState(agent, modelOptions))
  }, [agent, modelOptions, open])

  const handleSubmit = async () => {
    const result = buildAgentConfigPayload(form, agent)
    if (result.error) {
      toast(result.error)
      return
    }
    await onSubmit(result.payload)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{agent ? `${agent.name} 配置` : "新增 Agent 配置"}</DialogTitle>
        </DialogHeader>

        <div className="min-h-0 overflow-y-auto py-2 pr-1">
          <AgentConfigFields
            form={form}
            setForm={setForm}
            modelOptions={modelOptions}
            workflowOptions={workflowOptions}
            workflowsLoading={workflowsLoading}
            workflowsError={workflowsError}
            brainSkills={brainSkills}
            brainSkillsLoading={brainSkillsLoading}
            brainSkillsError={brainSkillsError}
            mcpTools={mcpTools}
            mcpToolsLoading={mcpToolsLoading}
            mcpToolsError={mcpToolsError}
            canEdit={canEdit}
            isSaving={isSaving}
            idPrefix="agent-dialog"
          />
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

function resolveAgentWorkflowId(agent: Agent | null) {
  return agent?.agentWorkflowId ?? agent?.agent_workflow_id ?? null
}

function resolveBoundWorkflowName(agent: Agent | null, workflowMap: Map<string, Workflow>) {
  const workflowId = resolveAgentWorkflowId(agent)
  if (!workflowId) return null
  return workflowMap.get(workflowId)?.name ?? workflowId
}

function AgentListItem({
  agent,
  isActive,
  workflowName,
  onSelect,
}: {
  agent: Agent
  isActive: boolean
  workflowName: string | null
  onSelect: (agentId: string) => void
}) {
  const runtimeStatus = agent.runtimeStatus ?? "unknown"
  const showPrimaryStatus = agent.status !== "waiting"
  const showRuntimeStatus = runtimeStatus !== "unknown"

  return (
    <button
      type="button"
      onClick={() => onSelect(agent.id)}
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left transition-colors",
        isActive ? "border-primary shadow-sm ring-1 ring-primary/20" : "border-border hover:bg-secondary/20",
        !agent.enabled && "opacity-70",
      )}
    >
      <div className="flex items-start gap-2.5">
        <AgentAvatar name={agent.name} type={agent.type} status={agent.status} size="lg" />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-start justify-between gap-3">
            <div className="truncate text-sm font-semibold text-foreground">{agent.name}</div>
            {showPrimaryStatus ? (
              <Badge variant="secondary" className={cn("shrink-0 text-xs", statusColors[agent.status])}>
                {statusLabels[agent.status]}
              </Badge>
            ) : null}
          </div>

          {showRuntimeStatus ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary" className={cn("text-xs", runtimeColors[runtimeStatus])}>
                {runtimeLabels[runtimeStatus]}
              </Badge>
            </div>
          ) : null}

          <div className="space-y-0.5 text-xs text-muted-foreground">
            <div className="truncate">模型：{agent.modelBinding?.model ?? "未配置"}</div>
            <div className="truncate">工作流：{workflowName ?? "未绑定"}</div>
          </div>
        </div>
      </div>
    </button>
  )
}

function AgentDetailPanel({
  agent,
  modelOptions,
  workflowOptions,
  workflowsLoading,
  workflowsError,
  brainSkills,
  brainSkillsLoading,
  brainSkillsError,
  mcpTools,
  mcpToolsLoading,
  mcpToolsError,
  canEdit,
  isSaving,
  isTogglingEnabled,
  isDeleting,
  onDelete,
  onToggleEnabled,
  onReload,
  onSave,
}: {
  agent: Agent
  modelOptions: ModelOption[]
  workflowOptions: WorkflowOption[]
  workflowsLoading: boolean
  workflowsError: Error | null
  brainSkills: BrainSkillItem[]
  brainSkillsLoading: boolean
  brainSkillsError: Error | null
  mcpTools: AgentBindableTool[]
  mcpToolsLoading: boolean
  mcpToolsError: Error | null
  canEdit: boolean
  isSaving: boolean
  isTogglingEnabled: boolean
  isDeleting: boolean
  onDelete: (agent: Agent) => Promise<void>
  onToggleEnabled: (agent: Agent, enabled: boolean) => Promise<boolean>
  onReload: (agentId: string) => Promise<void>
  onSave: (agentId: string, payload: AgentConfigRequest) => Promise<void>
}) {
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [form, setForm] = useState<AgentFormState>(() => defaultFormState(agent, modelOptions))
  const runtimeStatus = agent.runtimeStatus ?? "unknown"
  const showPrimaryStatus = agent.status !== "waiting"
  const showRuntimeStatus = runtimeStatus !== "unknown"
  const syncKey = buildAgentConfigSyncKey(agent)

  useEffect(() => {
    setForm(defaultFormState(agent, modelOptions))
  }, [modelOptions, syncKey])

  const handleEnabledChange = async (checked: boolean) => {
    const previous = form.enabled
    setForm((current) => ({ ...current, enabled: checked }))
    const success = await onToggleEnabled(agent, checked)
    if (!success) {
      setForm((current) => ({ ...current, enabled: previous }))
    }
  }

  const handleSave = async () => {
    const result = buildAgentConfigPayload(form, agent)
    if (result.error) {
      toast(result.error)
      return
    }
    try {
      await onSave(agent.id, result.payload)
    } catch {
      return
    }
  }

  return (
    <Card className={cn("flex h-full flex-col bg-card", !form.enabled && "opacity-75")}>
      <CardHeader className="border-b border-border/60 pb-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="flex items-start gap-3">
            <AgentAvatar name={agent.name} type={agent.type} status={agent.status} size="lg" />
            <div className="space-y-2">
              <CardTitle className="text-xl">{agent.name}</CardTitle>
              <div className="flex flex-wrap gap-2">
                {showPrimaryStatus ? (
                  <Badge variant="secondary" className={cn("text-xs", statusColors[agent.status])}>
                    {statusLabels[agent.status]}
                  </Badge>
                ) : null}
                {showRuntimeStatus ? (
                  <Badge variant="secondary" className={cn("text-xs", runtimeColors[runtimeStatus])}>
                    {runtimeLabels[runtimeStatus]}
                  </Badge>
                ) : null}
                <Badge variant="secondary" className="text-xs">
                  成功率 {agent.successRate}%
                </Badge>
              </div>
            </div>
          </div>

          <div className="flex flex-col items-end gap-2 xl:min-w-[260px]">
            <div className="flex items-center justify-end gap-3">
              <div className="flex items-center gap-2">
                <Switch
                  checked={form.enabled}
                  disabled={!canEdit || isTogglingEnabled || isSaving}
                  onCheckedChange={(checked) => {
                    void handleEnabledChange(checked)
                  }}
                />
                <span className="text-sm text-muted-foreground">{form.enabled ? "已启用" : "已停用"}</span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
                disabled={isDeleting || isSaving}
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="mr-1 size-4" />
                {isDeleting ? "删除中..." : "删除"}
              </Button>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="min-h-0 flex-1 overflow-y-auto pt-4">
        <AgentConfigFields
          form={form}
          setForm={setForm}
          modelOptions={modelOptions}
          workflowOptions={workflowOptions}
          workflowsLoading={workflowsLoading}
          workflowsError={workflowsError}
          brainSkills={brainSkills}
          brainSkillsLoading={brainSkillsLoading}
          brainSkillsError={brainSkillsError}
          mcpTools={mcpTools}
          mcpToolsLoading={mcpToolsLoading}
          mcpToolsError={mcpToolsError}
          canEdit={canEdit}
          isSaving={isSaving}
          idPrefix={`agent-detail-${agent.id}`}
          showEnabledField={false}
        />
      </CardContent>

      <div className="flex items-center justify-end gap-2 border-t border-border/60 px-5 py-3">
        <Button
          variant="outline"
          disabled={isSaving}
          onClick={() => void onReload(agent.id)}
        >
          热重载
        </Button>
        <Button disabled={!canEdit || isSaving || modelOptions.length === 0} onClick={() => void handleSave()}>
          {isSaving ? "保存中..." : "保存配置"}
        </Button>
      </div>

      <AlertDialog open={deleteOpen} onOpenChange={(open) => !isDeleting && setDeleteOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除 Agent</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除“{agent.name}”吗？删除后将从当前项目的 Agent 列表中移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={isDeleting}
              onClick={() => {
                void onDelete(agent).finally(() => setDeleteOpen(false))
              }}
            >
              {isDeleting ? "删除中..." : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

export default function AgentsPage() {
  const { hasPermission } = useAuth()
  const [searchQuery, setSearchQuery] = useState("")
  const [activeFilter, setActiveFilter] = useState<AgentFilterMode>("all")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null)
  const [togglingAgentId, setTogglingAgentId] = useState<string | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const { data, isLoading, error } = useAgents()
  const {
    data: workflowsData,
    isLoading: workflowsLoading,
    error: workflowsQueryError,
  } = useWorkflows()
  const {
    data: brainSkillsData,
    isLoading: brainSkillsLoading,
    error: brainSkillsQueryError,
  } = useBrainSkills()
  const {
    data: mcpToolsData,
    isLoading: mcpToolsLoading,
    error: mcpToolsQueryError,
  } = useAgentMcpTools()
  const { data: agentApiSettings } = useAgentApiSettings()
  const reloadAgentMutation = useReloadAgent()
  const createAgentMutation = useCreateAgent()
  const deleteAgentMutation = useDeleteAgent()
  const setAgentEnabledMutation = useSetAgentEnabled()
  const updateAgentConfigMutation = useUpdateAgentConfig()
  const agents = data?.items ?? []
  const workflows = workflowsData?.items ?? []
  const brainSkills = brainSkillsData?.items ?? []
  const mcpTools = mcpToolsData?.items ?? []
  const workflowsError = workflowsQueryError instanceof Error ? workflowsQueryError : null
  const brainSkillsError = brainSkillsQueryError instanceof Error ? brainSkillsQueryError : null
  const mcpToolsError = mcpToolsQueryError instanceof Error ? mcpToolsQueryError : null
  const canEditConfiguration = hasPermission("agents:reload")
  const brainSkillMap = useMemo(
    () => new Map(brainSkills.map((skill) => [skill.id, skill])),
    [brainSkills],
  )
  const mcpToolMap = useMemo(() => new Map(mcpTools.map((tool) => [tool.id, tool])), [mcpTools])
  const workflowMap = useMemo(() => new Map(workflows.map((workflow) => [workflow.id, workflow])), [workflows])

  const workflowOptions = useMemo<WorkflowOption[]>(() => {
    const optionMap = new Map<string, WorkflowOption>()

    for (const workflow of workflows) {
      const workflowId = String(workflow.id ?? "").trim()
      if (!workflowId) continue
      optionMap.set(workflowId, {
        value: workflowId,
        label: workflow.name,
        description: workflow.description ?? "",
      })
    }

    for (const agent of agents) {
      const workflowId = resolveAgentWorkflowId(agent)
      if (!workflowId || optionMap.has(workflowId)) continue
      optionMap.set(workflowId, {
        value: workflowId,
        label: workflowId,
        description: "",
      })
    }

    return Array.from(optionMap.values()).sort((left, right) => left.label.localeCompare(right.label, "zh-CN"))
  }, [agents, workflows])

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

  const filteredAgents = useMemo(() => {
    const keyword = searchQuery.trim().toLowerCase()

    return agents
      .filter((agent) => {
        if (activeFilter === "active" && !agent.enabled) return false
        if (activeFilter === "inactive" && agent.enabled) return false
        if (!keyword) return true

        return (
          agent.name.toLowerCase().includes(keyword) ||
          agent.description.toLowerCase().includes(keyword) ||
          String(agent.modelBinding?.model ?? "").toLowerCase().includes(keyword) ||
          String(resolveBoundWorkflowName(agent, workflowMap) ?? "").toLowerCase().includes(keyword) ||
          resolveAgentBoundSkills(agent, brainSkillMap).some((skill) =>
            skill.name.toLowerCase().includes(keyword),
          ) ||
          resolveAgentBoundTools(agent, mcpToolMap).some((tool) =>
            tool.name.toLowerCase().includes(keyword),
          )
        )
      })
      .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"))
  }, [activeFilter, agents, brainSkillMap, mcpToolMap, searchQuery, workflowMap])

  const activeCount = agents.filter((item) => item.enabled).length
  const runningCount = agents.filter((item) => item.status === "running").length
  const onlineCount = agents.filter((item) => (item.runtimeStatus ?? "unknown") === "online").length

  useEffect(() => {
    if (filteredAgents.length === 0) {
      if (selectedAgentId !== null) {
        setSelectedAgentId(null)
      }
      return
    }

    if (!selectedAgentId || !filteredAgents.some((agent) => agent.id === selectedAgentId)) {
      setSelectedAgentId(filteredAgents[0].id)
    }
  }, [filteredAgents, selectedAgentId])

  const selectedAgent = useMemo(
    () => filteredAgents.find((agent) => agent.id === selectedAgentId) ?? null,
    [filteredAgents, selectedAgentId],
  )

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

  const handleDelete = async (agent: Agent) => {
    try {
      setDeletingAgentId(agent.id)
      await deleteAgentMutation.mutateAsync(agent.id)
      if (selectedAgentId === agent.id) {
        setSelectedAgentId(null)
      }
      toast({
        title: "Agent 已删除",
        description: `${agent.name} 已从当前项目移除。`,
      })
    } catch (deleteError) {
      toast({
        title: "删除失败",
        description: deleteError instanceof Error ? deleteError.message : "未知错误",
      })
    } finally {
      setDeletingAgentId(null)
    }
  }

  const handleToggleEnabled = async (agent: Agent, enabled: boolean) => {
    try {
      setTogglingAgentId(agent.id)
      const result = await setAgentEnabledMutation.mutateAsync({
        agentId: agent.id,
        enabled,
      })
      toast({
        title: enabled ? "Agent 已启用" : "Agent 已停用",
        description: `${result.agent.name} 当前为${enabled ? "启用" : "停用"}状态。`,
      })
      return true
    } catch (toggleError) {
      toast({
        title: "切换启用状态失败",
        description: toggleError instanceof Error ? toggleError.message : "未知错误",
      })
      return false
    } finally {
      setTogglingAgentId(null)
    }
  }

  const handleCreateAgent = async (payload: AgentConfigRequest) => {
    try {
      const result = await createAgentMutation.mutateAsync(payload)
      setSelectedAgentId(result.agent.id)
      toast({
        title: "Agent 已创建",
        description: `${result.agent.name} 已加入当前项目。`,
      })
      setDialogOpen(false)
    } catch (saveError) {
      toast({
        title: "保存失败",
        description: saveError instanceof Error ? saveError.message : "未知错误",
      })
    }
  }

  const handleUpdateAgent = async (agentId: string, payload: AgentConfigRequest) => {
    try {
      const result = await updateAgentConfigMutation.mutateAsync({
        agentId,
        payload,
      })
      setSelectedAgentId(result.agent.id)
      toast({
        title: "Agent 配置已更新",
        description: `${result.agent.name} 已绑定 ${result.agent.modelBinding?.model ?? "--"}`,
      })
    } catch (saveError) {
      toast({
        title: "保存失败",
        description: saveError instanceof Error ? saveError.message : "未知错误",
      })
      throw saveError
    }
  }

  return (
    <div className="flex h-full flex-col p-5">
      {modelOptions.length === 0 ? (
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-foreground">
          当前没有可选的启用模型，请先到“模型接入”页面启用模型。
        </div>
      ) : null}

      {error ? (
        <div className="mb-4 text-sm text-destructive">
          Agent 数据加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      <Tabs
        value={activeFilter}
        onValueChange={(value) => setActiveFilter(value as AgentFilterMode)}
        className="min-h-0 flex-1"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <TabsList className="bg-secondary">
            <TabsTrigger value="all">全部 ({agents.length})</TabsTrigger>
            <TabsTrigger value="active">活跃 ({agents.filter((a) => a.enabled).length})</TabsTrigger>
            <TabsTrigger value="inactive">停用 ({agents.filter((a) => !a.enabled).length})</TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-3">
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
                setDialogOpen(true)
              }}
            >
              <Plus className="mr-2 size-4" />
              新增 Agent 配置
            </Button>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="flex min-h-0 flex-col bg-card">
            <CardHeader className="border-b border-border/60 pb-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="搜索 Agent..."
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  className="bg-secondary pl-10"
                />
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 p-2.5">
              {isLoading && agents.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  正在加载 Agent 数据...
                </div>
              ) : filteredAgents.length === 0 ? (
                <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-border/60 text-sm text-muted-foreground">
                  当前筛选下没有 Agent
                </div>
              ) : (
                <div className="flex h-full flex-col gap-2.5 overflow-y-auto pr-1">
                  {filteredAgents.map((agent) => (
                    <AgentListItem
                      key={agent.id}
                      agent={agent}
                      isActive={agent.id === selectedAgent?.id}
                      workflowName={resolveBoundWorkflowName(agent, workflowMap)}
                      onSelect={setSelectedAgentId}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="min-h-0">
            {selectedAgent ? (
              <AgentDetailPanel
                agent={selectedAgent}
                modelOptions={modelOptions}
                workflowOptions={workflowOptions}
                workflowsLoading={workflowsLoading}
                workflowsError={workflowsError}
                brainSkills={brainSkills}
                brainSkillsLoading={brainSkillsLoading}
                brainSkillsError={brainSkillsError}
                mcpTools={mcpTools}
                mcpToolsLoading={mcpToolsLoading}
                mcpToolsError={mcpToolsError}
                canEdit={canEditConfiguration}
                isSaving={updateAgentConfigMutation.isPending}
                isTogglingEnabled={
                  togglingAgentId === selectedAgent.id && setAgentEnabledMutation.isPending
                }
                isDeleting={deletingAgentId === selectedAgent.id && deleteAgentMutation.isPending}
                onDelete={handleDelete}
                onToggleEnabled={handleToggleEnabled}
                onReload={handleReload}
                onSave={handleUpdateAgent}
              />
            ) : (
              <Card className="flex h-full min-h-[420px] items-center justify-center bg-card">
                <CardContent className="text-center text-sm text-muted-foreground">
                  请选择左侧 Agent 查看详情
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </Tabs>

      <AgentConfigDialog
        open={dialogOpen}
        agent={null}
        modelOptions={modelOptions}
        workflowOptions={workflowOptions}
        workflowsLoading={workflowsLoading}
        workflowsError={workflowsError}
        brainSkills={brainSkills}
        brainSkillsLoading={brainSkillsLoading}
        brainSkillsError={brainSkillsError}
        mcpTools={mcpTools}
        mcpToolsLoading={mcpToolsLoading}
        mcpToolsError={mcpToolsError}
        canEdit={canEditConfiguration}
        isSaving={createAgentMutation.isPending}
        onOpenChange={setDialogOpen}
        onSubmit={handleCreateAgent}
      />
    </div>
  )
}
