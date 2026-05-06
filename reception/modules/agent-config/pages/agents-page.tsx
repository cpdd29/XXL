"use client"

import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react"
import { AgentAvatar } from "@/shared/components/agent-avatar"
import { Checkbox } from "@/shared/ui/checkbox"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/ui/alert-dialog"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select"
import { Switch } from "@/shared/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import { Textarea } from "@/shared/ui/textarea"
import { useBrainSkills } from "@/modules/capability/hooks/use-brain-skills"
import { useAuth } from "@/modules/auth/hooks/use-auth"
import {
  useAgents,
  useAgentMcpTools,
  useCreateAgent,
  useDeleteAgent,
  useRegisterExternalAgent,
  useReloadAgent,
  useSetAgentEnabled,
  useUpdateAgentConfig,
} from "@/modules/agent-config/hooks/use-agents"
import { useExecutors } from "@/modules/executor-config/hooks/use-executor-config"
import { useAgentApiSettings } from "@/modules/settings/hooks/use-settings"
import { toast } from "@/shared/hooks/use-toast"
import { cn } from "@/shared/utils"
import type {
  Agent,
  AgentBindableTool,
  AgentBoundSkill,
  AgentBoundTool,
  AgentConfigRequest,
  ExternalAgentCreateRequest,
  BrainSkillItem,
  Executor,
} from "@/shared/types"
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
  soul: string
  tag: SystemTagOption | ""
  selectedModel: string
  executorId: string
  selectedSkillIds: string[]
  selectedToolIds: string[]
  multiMembers: MultiMemberDraft[]
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
type AgentCreateSource = "local" | "external"
type LocalAgentRunMode = "single" | "multi"
type SystemTagOption =
  | "本地 · 单智能体"
  | "本地 · 多智能体"
  | "外部 · 单智能体"
  | "外部 · 多智能体"
type MultiMemberRole = "dispatcher" | "worker"
type MultiMemberDraft = {
  id: string
  fixed: boolean
  role: MultiMemberRole
  agentId: string
}
type ResolvedMultiMember = {
  role: MultiMemberRole
  agentId: string
  order: number
}
const SYSTEM_TAG_OPTIONS: SystemTagOption[] = [
  "本地 · 单智能体",
  "本地 · 多智能体",
  "外部 · 单智能体",
  "外部 · 多智能体",
]
const LOCAL_SINGLE_TAG: SystemTagOption = "本地 · 单智能体"
const LOCAL_MULTI_TAG: SystemTagOption = "本地 · 多智能体"
const EXTERNAL_SINGLE_TAG: SystemTagOption = "外部 · 单智能体"
const EXTERNAL_MULTI_TAG: SystemTagOption = "外部 · 多智能体"
const LOCAL_SYSTEM_TAG_OPTIONS: SystemTagOption[] = [LOCAL_SINGLE_TAG, LOCAL_MULTI_TAG]
const EXTERNAL_SYSTEM_TAG_OPTIONS: SystemTagOption[] = [EXTERNAL_SINGLE_TAG, EXTERNAL_MULTI_TAG]
const EXTERNAL_RECEPTION_FAMILY = "hermes-reception"
const EXTERNAL_RECEPTION_REMOTE_MODEL = "hermes-agent"

type LocalAgentCreateDraft = {
  name: string
  description: string
  soul: string
  tag: SystemTagOption | ""
  runMode: LocalAgentRunMode
  selectedModel: string
  executorId: string
  selectedSkillIds: string[]
  selectedToolIds: string[]
  multiMembers: MultiMemberDraft[]
}

type ExternalAgentCreateDraft = {
  id: string
  name: string
  description: string
  tag: SystemTagOption | ""
  version: string
  protocol: string
  baseUrl: string
  invokePath: string
  healthPath: string
  method: string
  releaseChannel: string
  heartbeatIntervalSeconds: string
  heartbeatTimeoutSeconds: string
  capabilitiesInput: string
  compatibilityInput: string
}

type ExternalAgentResolvedDetails = {
  source: string
  version: string
  protocol: string
  method: string
  baseUrl: string
  invokePath: string
  healthPath: string
  releaseChannel: string
  heartbeatIntervalSeconds: string
  heartbeatTimeoutSeconds: string
  capabilities: string[]
  compatibility: string[]
  lastHeartbeatAt: string
  runtimeReason: string
}

const EXTERNAL_AGENT_METHOD_OPTIONS = [
  { value: "POST", label: "POST" },
] as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function normalizeIdentifierList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))]
}

function parseCommaSeparatedInput(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))]
}

function parseOptionalIntegerInput(value: string): number | undefined {
  const normalized = value.trim()
  if (!normalized) return undefined
  const parsed = Number.parseInt(normalized, 10)
  if (!Number.isFinite(parsed) || parsed <= 0) return undefined
  return parsed
}

function isSystemTagOption(value: string): value is SystemTagOption {
  return SYSTEM_TAG_OPTIONS.includes(value as SystemTagOption)
}

function defaultLocalTagByRunMode(runMode: LocalAgentRunMode): SystemTagOption {
  return runMode === "multi" ? LOCAL_MULTI_TAG : LOCAL_SINGLE_TAG
}

function inferSystemTag(agent: Agent | null): SystemTagOption | "" {
  if (!agent) return ""

  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const snapshotMetadata = snapshot && isRecord(snapshot.metadata) ? snapshot.metadata : null
  const agentMetadata = isRecord(agent.metadata) ? agent.metadata : null
  const metadata = snapshotMetadata ?? agentMetadata
  const tags = Array.isArray(metadata?.tags)
    ? metadata.tags.map((item) => String(item ?? "").trim()).filter(Boolean)
    : []
  const matched = tags.find((item) => isSystemTagOption(item))
  if (matched && isSystemTagOption(matched)) {
    return matched
  }

  const runMode = resolveAgentRunMode(agent)
  if (isExternalAgentView(agent)) {
    return runMode === "multi" ? EXTERNAL_MULTI_TAG : EXTERNAL_SINGLE_TAG
  }
  return defaultLocalTagByRunMode(runMode)
}

function resolveAgentSoul(agent: Agent | null): string {
  if (!agent) return ""
  if (typeof agent.soul === "string") return agent.soul
  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  return typeof snapshot?.soul === "string" ? snapshot.soul : ""
}

function resolveAgentMetadata(agent: Agent | null): Record<string, unknown> | null {
  if (!agent) return null
  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const snapshotMetadata = snapshot && isRecord(snapshot.metadata) ? snapshot.metadata : null
  const directMetadata = isRecord(agent.metadata) ? agent.metadata : null
  return snapshotMetadata ?? directMetadata
}

function isTaskChildAgent(agent: Agent | null): boolean {
  const metadata = resolveAgentMetadata(agent)
  if (!metadata) return false
  const source = String(metadata.source ?? "").trim().toLowerCase()
  if (source === "requirement_dispatch_agent") return true
  const hasTaskBinding = Boolean(
    String(metadata.task_id ?? metadata.taskId ?? "").trim() &&
      String(metadata.group_id ?? metadata.groupId ?? "").trim(),
  )
  return hasTaskBinding
}

function resolveTaskChildBinding(agent: Agent | null): {
  taskId: string
  taskTitle: string
  groupId: string
  groupName: string
  role: string
} | null {
  const metadata = resolveAgentMetadata(agent)
  if (!metadata) return null
  const taskId = String(metadata.task_id ?? metadata.taskId ?? "").trim()
  const groupId = String(metadata.group_id ?? metadata.groupId ?? "").trim()
  if (!taskId || !groupId) return null
  return {
    taskId,
    taskTitle: String(metadata.task_title ?? metadata.taskTitle ?? "").trim(),
    groupId,
    groupName: String(metadata.group_name ?? metadata.groupName ?? "").trim(),
    role: String(metadata.group_role ?? metadata.groupRole ?? "").trim(),
  }
}

function buildEndpointFieldValue(baseUrl: string, invokePath: string): string {
  const normalizedBaseUrl = baseUrl.trim()
  const normalizedInvokePath = invokePath.trim()
  if (!normalizedBaseUrl) return normalizedInvokePath
  if (!normalizedInvokePath) return normalizedBaseUrl
  return `${normalizedBaseUrl.replace(/\/+$/, "")}/${normalizedInvokePath.replace(/^\/+/, "")}`
}

function splitEndpointFieldValue(value: string): { baseUrl: string; invokePath: string } {
  const normalized = value.trim()
  if (!normalized) {
    return { baseUrl: "", invokePath: "" }
  }

  try {
    const url = new URL(normalized)
    const pathname = url.pathname === "/" ? "" : url.pathname
    const search = url.search || ""
    const hash = url.hash || ""
    return {
      baseUrl: `${url.protocol}//${url.host}`,
      invokePath: `${pathname}${search}${hash}` || "/",
    }
  } catch {
    return {
      baseUrl: normalized,
      invokePath: "",
    }
  }
}

function buildExternalAgentId(name: string): string {
  const normalized = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "")

  return normalized || `external-agent-${Date.now()}`
}

function resolveAgentRunMode(agent: Agent | null): LocalAgentRunMode {
  if (!agent) return "single"
  if (agent.type === "task_dispatcher") return "multi"

  const inputContract = isRecord(agent.inputContract)
    ? agent.inputContract
    : isRecord(agent.input_contract)
      ? agent.input_contract
      : null
  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const runtime = snapshot && isRecord(snapshot.runtime) ? snapshot.runtime : null
  const metadata = snapshot && isRecord(snapshot.metadata) ? snapshot.metadata : null

  const runModeCandidates = [
    inputContract && isRecord(inputContract.orchestration) ? inputContract.orchestration.runMode : null,
    inputContract && isRecord(inputContract.orchestration) ? inputContract.orchestration.run_mode : null,
    runtime && isRecord(runtime.orchestration) ? runtime.orchestration.runMode : null,
    runtime && isRecord(runtime.orchestration) ? runtime.orchestration.run_mode : null,
    metadata?.runMode,
    metadata?.run_mode,
  ]
  for (const candidate of runModeCandidates) {
    const normalized = String(candidate ?? "").trim().toLowerCase()
    if (normalized === "multi") return "multi"
  }

  if (resolveMultiAgentMembers(agent).length > 0) return "multi"
  return "single"
}

function resolveMultiAgentMembers(agent: Agent): ResolvedMultiMember[] {
  const inputContract = isRecord(agent.inputContract)
    ? agent.inputContract
    : isRecord(agent.input_contract)
      ? agent.input_contract
      : null
  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const runtime = snapshot && isRecord(snapshot.runtime) ? snapshot.runtime : null
  const metadata = snapshot && isRecord(snapshot.metadata) ? snapshot.metadata : null
  const metadataMultiAgent = metadata && isRecord(metadata.multiAgent) ? metadata.multiAgent : null

  const candidates: unknown[] = [
    inputContract && isRecord(inputContract.orchestration) ? inputContract.orchestration : null,
    runtime && isRecord(runtime.orchestration) ? runtime.orchestration : null,
    metadataMultiAgent,
  ]

  for (const candidate of candidates) {
    if (!isRecord(candidate)) continue
    const team = isRecord(candidate.team) ? candidate.team : candidate
    const members = Array.isArray(team.members) ? team.members : []
    if (members.length === 0) continue

    const resolved = members
      .map((item, index) => {
        if (!isRecord(item)) return null
        const rawRole = String(item.role ?? "").trim().toLowerCase()
        const role: MultiMemberRole = rawRole === "dispatcher" ? "dispatcher" : "worker"
        const agentId = String(item.agentId ?? item.agent_id ?? "").trim()
        if (!agentId) return null
        const orderValue = Number(item.order ?? index + 1)
        const order = Number.isFinite(orderValue) ? orderValue : index + 1
        return {
          role,
          agentId,
          order,
        } satisfies ResolvedMultiMember
      })
      .filter((item): item is ResolvedMultiMember => Boolean(item))
      .sort((a, b) => a.order - b.order)

    if (resolved.length > 0) return resolved
  }

  return []
}

function defaultMultiMembers(): MultiMemberDraft[] {
  return [
    { id: "dispatcher-1", fixed: true, role: "dispatcher", agentId: "" },
    { id: "worker-1", fixed: true, role: "worker", agentId: "" },
    { id: "worker-2", fixed: true, role: "worker", agentId: "" },
  ]
}

function createWorkerMemberId(): string {
  return `worker-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function defaultLocalAgentCreateDraft(modelOptions: ModelOption[], executors: Executor[]): LocalAgentCreateDraft {
  const defaultModel = modelOptions[0]?.value ?? ""
  const defaultExecutor = executors.find((item) => item.enabled)?.id ?? executors[0]?.id ?? ""
  return {
    name: "",
    description: "",
    soul: "",
    tag: LOCAL_SINGLE_TAG,
    runMode: "single",
    selectedModel: defaultModel,
    executorId: defaultExecutor,
    selectedSkillIds: [],
    selectedToolIds: [],
    multiMembers: defaultMultiMembers(),
  }
}

function defaultExternalAgentCreateDraft(): ExternalAgentCreateDraft {
  return {
    id: "",
    name: "",
    description: "",
    tag: EXTERNAL_SINGLE_TAG,
    version: "1.0.0",
    protocol: "http",
    baseUrl: "",
    invokePath: "/v1/chat/completions",
    healthPath: "/health",
    method: "POST",
    releaseChannel: "stable",
    heartbeatIntervalSeconds: "",
    heartbeatTimeoutSeconds: "",
    capabilitiesInput: "",
    compatibilityInput: "",
  }
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

function resolveAgentExecutorId(agent: Agent | null): string {
  if (!agent) return ""
  const snapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const runtime = snapshot && isRecord(snapshot.runtime) ? snapshot.runtime : null
  const metadata = snapshot && isRecord(snapshot.metadata) ? snapshot.metadata : null

  const candidates = [
    metadata?.executorId,
    metadata?.executor_id,
    runtime?.executorId,
    runtime?.executor_id,
    snapshot?.executorId,
    snapshot?.executor_id,
  ]
  for (const candidate of candidates) {
    const normalized = String(candidate ?? "").trim()
    if (normalized) return normalized
  }
  return ""
}

function isExternalAgentView(agent: Agent | null): boolean {
  if (!agent) return false

  const configSummary = isRecord(agent.configSummary) ? agent.configSummary : null
  const configSnapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const metadata = configSnapshot && isRecord(configSnapshot.metadata) ? configSnapshot.metadata : null

  const sourceCandidates = [
    configSummary?.source,
    metadata?.source,
    agent.runtimeMetrics?.source,
  ]

  for (const candidate of sourceCandidates) {
    const normalized = String(candidate ?? "").trim().toLowerCase()
    if (normalized === "external_agent_registry" || normalized === "control_plane") {
      return true
    }
  }

  return String(configSnapshot?.status ?? "").trim().toLowerCase() === "external_registered"
}

function resolveExternalAgentDetails(agent: Agent): ExternalAgentResolvedDetails {
  const configSummary = isRecord(agent.configSummary) ? agent.configSummary : null
  const configSnapshot = isRecord(agent.configSnapshot) ? agent.configSnapshot : null
  const snapshotMetadata = configSnapshot && isRecord(configSnapshot.metadata) ? configSnapshot.metadata : null
  const agentMetadata = isRecord(agent.metadata) ? agent.metadata : null
  const metadata = snapshotMetadata ?? agentMetadata
  const invocation = configSummary && isRecord(configSummary.invocation) ? configSummary.invocation : null
  const snapshotAgent = configSnapshot && isRecord(configSnapshot.agent) ? configSnapshot.agent : null
  const snapshotRuntime = configSnapshot && isRecord(configSnapshot.runtime) ? configSnapshot.runtime : null
  const runtimeInvocation = snapshotRuntime && isRecord(snapshotRuntime.invocation) ? snapshotRuntime.invocation : null
  const metadataInvocation = metadata && isRecord(metadata.invocation) ? metadata.invocation : null
  const runtimeMetrics = isRecord(agent.runtimeMetrics) ? agent.runtimeMetrics : null

  const normalizeText = (value: unknown) => {
    const normalized = String(value ?? "").trim()
    return normalized || "未配置"
  }

  const normalizeList = (value: unknown) => {
    if (!Array.isArray(value)) return []
    return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))]
  }

  return {
    source: normalizeText(configSummary?.source ?? metadata?.source ?? agent.runtimeMetrics?.source),
    version: normalizeText(configSummary?.version ?? snapshotAgent?.version ?? metadata?.version ?? "1.0.0"),
    protocol: normalizeText(
      invocation?.protocol
      ?? runtimeInvocation?.protocol
      ?? metadataInvocation?.protocol
      ?? "http",
    ),
    method: normalizeText(
      invocation?.method
      ?? runtimeInvocation?.method
      ?? metadataInvocation?.method
      ?? "POST",
    ),
    baseUrl: normalizeText(
      invocation?.base_url
      ?? invocation?.baseUrl
      ?? runtimeInvocation?.base_url
      ?? runtimeInvocation?.baseUrl
      ?? metadataInvocation?.base_url
      ?? metadataInvocation?.baseUrl
      ?? null,
    ),
    invokePath: normalizeText(
      invocation?.invoke_path
      ?? invocation?.invokePath
      ?? runtimeInvocation?.invoke_path
      ?? runtimeInvocation?.invokePath
      ?? metadataInvocation?.invoke_path
      ?? metadataInvocation?.invokePath
      ?? "/v1/chat/completions",
    ),
    healthPath: normalizeText(
      invocation?.health_path
      ?? invocation?.healthPath
      ?? runtimeInvocation?.health_path
      ?? runtimeInvocation?.healthPath
      ?? metadataInvocation?.health_path
      ?? metadataInvocation?.healthPath
      ?? "/health",
    ),
    releaseChannel: normalizeText(configSummary?.release_channel ?? configSummary?.releaseChannel ?? metadata?.release_channel ?? metadata?.releaseChannel ?? "stable"),
    heartbeatIntervalSeconds: normalizeText(
      agent.heartbeatIntervalSeconds ?? snapshotRuntime?.heartbeat_interval_seconds ?? snapshotRuntime?.heartbeatIntervalSeconds,
    ),
    heartbeatTimeoutSeconds: normalizeText(
      agent.heartbeatTimeoutSeconds ?? snapshotRuntime?.heartbeat_timeout_seconds ?? snapshotRuntime?.heartbeatTimeoutSeconds,
    ),
    capabilities: normalizeList(configSummary?.capabilities ?? runtimeMetrics?.capabilities),
    compatibility: normalizeList(configSummary?.compatibility ?? metadata?.compatibility ?? snapshotAgent?.compatibility),
    lastHeartbeatAt: normalizeText(agent.lastHeartbeatAt),
    runtimeReason: normalizeText(agent.runtimeStatusReason),
  }
}

function defaultExternalAgentDetailDraft(agent: Agent): ExternalAgentCreateDraft {
  const details = resolveExternalAgentDetails(agent)
  return {
    id: agent.id,
    name: agent.name,
    description: agent.description ?? "",
    tag: inferSystemTag(agent) || EXTERNAL_SINGLE_TAG,
    version: details.version === "未配置" ? "1.0.0" : details.version,
    protocol: details.protocol === "未配置" ? "http" : details.protocol,
    baseUrl: details.baseUrl === "未配置" ? "" : details.baseUrl,
    invokePath: details.invokePath === "未配置" ? "/v1/chat/completions" : details.invokePath,
    healthPath: details.healthPath === "未配置" ? "/health" : details.healthPath,
    method: details.method === "未配置" ? "POST" : details.method,
    releaseChannel: details.releaseChannel === "未配置" ? "stable" : details.releaseChannel,
    heartbeatIntervalSeconds: details.heartbeatIntervalSeconds === "未配置" ? "" : details.heartbeatIntervalSeconds,
    heartbeatTimeoutSeconds: details.heartbeatTimeoutSeconds === "未配置" ? "" : details.heartbeatTimeoutSeconds,
    capabilitiesInput: details.capabilities.join(", "),
    compatibilityInput: details.compatibility.join(", "),
  }
}

function toMultiMemberDrafts(members: ResolvedMultiMember[]): MultiMemberDraft[] {
  if (members.length === 0) return []
  let dispatcherSeen = false
  let fixedWorkers = 0
  return members.map((member, index) => {
    let fixed = false
    if (member.role === "dispatcher" && !dispatcherSeen) {
      fixed = true
      dispatcherSeen = true
    } else if (member.role === "worker" && fixedWorkers < 2) {
      fixed = true
      fixedWorkers += 1
    }
    return {
      id: `${member.role}-${index + 1}-${member.agentId}`,
      fixed,
      role: member.role,
      agentId: member.agentId,
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
  const runMode = resolveAgentRunMode(agent)
  const resolvedMembers = agent ? resolveMultiAgentMembers(agent) : []
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
    soul: resolveAgentSoul(agent),
    type: runMode === "multi" ? "task_dispatcher" : (agent?.type ?? "default"),
    enabled: agent?.enabled ?? true,
    tag: inferSystemTag(agent) || defaultLocalTagByRunMode(runMode),
    selectedModel,
    executorId: resolveAgentExecutorId(agent),
    selectedSkillIds: resolveAgentBoundSkillIds(agent),
    selectedToolIds: resolveAgentBoundToolIds(agent),
    multiMembers: runMode === "multi" ? toMultiMemberDrafts(resolvedMembers) : [],
  }
}

function providerLabel(providerKey: string) {
  if (providerKey === "openapi") return "OpenAPI Compatible"
  if (providerKey === "openai") return "OpenAI"
  if (providerKey === "deepseek") return "DeepSeek"
  if (providerKey === "minimax") return "MiniMax"
  return providerKey.toUpperCase()
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

  const { providerKey, model } = parseModelValue(form.selectedModel)

  const isMultiAgent = form.type === "task_dispatcher"
  const expectedTag = defaultLocalTagByRunMode(isMultiAgent ? "multi" : "single")
  if (!form.tag) {
    return {
      error: {
        title: "请选择系统标签",
        description: "请先选择智能体系统标签。",
      },
    }
  }
  if (form.tag !== expectedTag) {
    return {
      error: {
        title: "系统标签不匹配",
        description: `当前运行模式应使用标签“${expectedTag}”。`,
      },
    }
  }
  if (!isMultiAgent && !form.executorId.trim()) {
    return {
      error: {
        title: "执行器未配置",
        description: "请选择一个执行器。",
      },
    }
  }

  const normalizedMembers = form.multiMembers.map((member, index) => ({
    role: member.role,
    agentId: member.agentId.trim(),
    order: index + 1,
  }))

  if (isMultiAgent) {
    if (normalizedMembers.length < 3) {
      return {
        error: {
          title: "成员配置不足",
          description: "多智能体团队至少需要 3 个成员。",
        },
      }
    }
    const dispatcherCount = normalizedMembers.filter((member) => member.role === "dispatcher").length
    if (dispatcherCount !== 1) {
      return {
        error: {
          title: "角色配置不完整",
          description: "必须且仅能有 1 个需求分发角色。",
        },
      }
    }
    const workerCount = normalizedMembers.filter((member) => member.role === "worker").length
    if (workerCount < 2) {
      return {
        error: {
          title: "角色配置不完整",
          description: "执行角色至少需要 2 个。",
        },
      }
    }
    if (normalizedMembers.some((member) => !member.agentId)) {
      return {
        error: {
          title: "成员未绑定",
          description: "请为每个角色选择绑定的 Agent。",
        },
      }
    }
    const uniqueIds = new Set(normalizedMembers.map((member) => member.agentId))
    if (uniqueIds.size !== normalizedMembers.length) {
      return {
        error: {
          title: "成员绑定冲突",
          description: "同一个 Agent 不能重复绑定多个角色。",
        },
      }
    }
  }

  const payload: AgentConfigRequest = {
    name,
    description: form.description.trim(),
    type: form.type,
    enabled: form.enabled,
    soul: form.soul.trim() || null,
    providerKey,
    model,
    skillIds: isMultiAgent ? [] : form.selectedSkillIds,
    toolIds: isMultiAgent ? [] : form.selectedToolIds,
  }

  if (isMultiAgent) {
    payload.inputContract = {
      orchestration: {
        runMode: "multi",
        team: {
          members: normalizedMembers,
        },
      },
    }
    payload.outputContract = {}
    payload.contractVersion = "agent-contract-v2"
    payload.metadata = {
      source: "agent_detail_edit",
      runMode: "multi",
      tags: [form.tag],
      multiAgent: {
        runMode: "multi",
        teamSize: normalizedMembers.length,
        dispatcherAgentId: normalizedMembers.find((member) => member.role === "dispatcher")?.agentId ?? null,
        workerAgentIds: normalizedMembers.filter((member) => member.role === "worker").map((member) => member.agentId),
      },
      executorId: null,
    }
  } else {
    payload.metadata = {
      source: "agent_detail_edit",
      runMode: "single",
      tags: [form.tag],
      executorId: form.executorId.trim(),
    }
  }

  return {
    payload,
  }
}

function AgentConfigFields({
  form,
  setForm,
  modelOptions,
  executors,
  executorsLoading,
  executorsError,
  onRetryExecutors,
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
  executors: Executor[]
  executorsLoading: boolean
  executorsError: Error | null
  onRetryExecutors: () => void
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
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-name`}>
            Agent 名称 <span className="text-destructive">*</span>
          </Label>
          <Input
            id={`${idPrefix}-name`}
            value={form.name}
            disabled={!canEdit || isSaving}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-tag`}>
            系统标签 <span className="text-destructive">*</span>
          </Label>
          <Select value={form.tag} disabled={!canEdit || isSaving} onValueChange={(value) => setForm((current) => ({ ...current, tag: value as SystemTagOption }))}>
            <SelectTrigger id={`${idPrefix}-tag`}>
              <SelectValue placeholder="选择系统标签" />
            </SelectTrigger>
            <SelectContent>
              {LOCAL_SYSTEM_TAG_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-model`}>
          项目内启用模型 <span className="text-destructive">*</span>
        </Label>
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

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-executor`}>
          执行器 <span className="text-destructive">*</span>
        </Label>
        <Select
          value={form.executorId}
          disabled={!canEdit || isSaving || executorsLoading || executors.length === 0}
          onValueChange={(value) => setForm((current) => ({ ...current, executorId: value }))}
        >
          <SelectTrigger id={`${idPrefix}-executor`}>
            <SelectValue placeholder="选择执行器" />
          </SelectTrigger>
          <SelectContent>
            {executors.map((executor) => (
              <SelectItem key={executor.id} value={executor.id}>
                {executor.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {executorsError ? (
          <div className="flex items-center justify-between rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <span>{executorsError.message.includes("timeout") ? "执行器加载超时" : `执行器加载失败：${executorsError.message}`}</span>
            <Button type="button" variant="outline" size="sm" className="h-7" disabled={isSaving} onClick={onRetryExecutors}>
              重试
            </Button>
          </div>
        ) : null}
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
        <Label htmlFor={`${idPrefix}-soul`}>soul.md 配置</Label>
        <Textarea
          id={`${idPrefix}-soul`}
          rows={10}
          value={form.soul}
          disabled={!canEdit || isSaving}
          placeholder={"# Soul\n\n你是谁、负责什么、回答时要遵守什么约束。"}
          onChange={(event) =>
            setForm((current) => ({ ...current, soul: event.target.value }))
          }
        />
        <div className="text-xs text-muted-foreground">
          保存后会写入当前 Agent 的运行配置快照，用作等价 `soul.md` 内容。
        </div>
      </div>
    </div>
  )
}

function MultiAgentConfigFields({
  form,
  setForm,
  canEdit,
  isSaving,
  agents,
  idPrefix,
}: {
  form: AgentFormState
  setForm: Dispatch<SetStateAction<AgentFormState>>
  canEdit: boolean
  isSaving: boolean
  agents: Agent[]
  idPrefix: string
}) {
  const handleAddMember = () => {
    setForm((current) => ({
      ...current,
      multiMembers: [
        ...current.multiMembers,
        { id: createWorkerMemberId(), fixed: false, role: "worker", agentId: "" },
      ],
    }))
  }

  const handleRemoveMember = (memberId: string) => {
    setForm((current) => {
      const target = current.multiMembers.find((item) => item.id === memberId)
      if (!target || target.fixed || target.role === "dispatcher") return current
      return {
        ...current,
        multiMembers: current.multiMembers.filter((item) => item.id !== memberId),
      }
    })
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-name`}>
            Agent 名称 <span className="text-destructive">*</span>
          </Label>
          <Input
            id={`${idPrefix}-name`}
            value={form.name}
            disabled={!canEdit || isSaving}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-tag`}>
            系统标签 <span className="text-destructive">*</span>
          </Label>
          <Select value={form.tag} disabled={!canEdit || isSaving} onValueChange={(value) => setForm((current) => ({ ...current, tag: value as SystemTagOption }))}>
            <SelectTrigger id={`${idPrefix}-tag`}>
              <SelectValue placeholder="选择系统标签" />
            </SelectTrigger>
            <SelectContent>
              {LOCAL_SYSTEM_TAG_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label>
          团队成员 <span className="text-destructive">*</span>
        </Label>
        <div className="flex items-center justify-between">
          <div />
          <Button type="button" variant="outline" size="sm" disabled={!canEdit || isSaving} onClick={handleAddMember}>
            添加成员
          </Button>
        </div>
        <div className="space-y-2 rounded-lg border border-border bg-secondary/10 p-3">
          {form.multiMembers.map((member, index) => (
            <div
              key={member.id}
              className="grid gap-2 rounded-md border border-border/80 bg-background/70 p-3 sm:grid-cols-[140px_minmax(0,1fr)_80px]"
            >
              <div className="space-y-1">
                <Label>角色</Label>
                <Input value={member.role === "dispatcher" ? "需求分发" : "执行"} readOnly disabled />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`${idPrefix}-multi-agent-${member.id}`}>
                  绑定 Agent <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={member.agentId}
                  disabled={!canEdit || isSaving || agents.length === 0}
                  onValueChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      multiMembers: current.multiMembers.map((item) => (item.id === member.id ? { ...item, agentId: value } : item)),
                    }))
                  }
                >
                  <SelectTrigger id={`${idPrefix}-multi-agent-${member.id}`}>
                    <SelectValue placeholder="选择 Agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>操作</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full"
                  disabled={!canEdit || isSaving || member.fixed || member.role === "dispatcher"}
                  onClick={() => handleRemoveMember(member.id)}
                >
                  删除
                </Button>
              </div>
              {member.fixed ? (
                <div className="sm:col-span-3 text-xs text-muted-foreground">
                  {index === 0 ? "默认分发角色（固定）" : "默认执行角色（固定）"}
                </div>
              ) : null}
            </div>
          ))}
          {agents.length === 0 ? (
            <div className="text-sm text-destructive">暂无可绑定 Agent，请先在列表中创建或接入 Agent。</div>
          ) : null}
          <div className="text-xs text-muted-foreground">至少 1 个需求分发角色 + 2 个执行角色，可继续添加执行角色。</div>
        </div>
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
        <Label htmlFor={`${idPrefix}-soul`}>soul.md 配置</Label>
        <Textarea
          id={`${idPrefix}-soul`}
          rows={10}
          value={form.soul}
          disabled={!canEdit || isSaving}
          placeholder={"# Dispatcher Soul\n\n说明这个智能体如何拆解任务、如何协调成员、如何验收。"}
          onChange={(event) =>
            setForm((current) => ({ ...current, soul: event.target.value }))
          }
        />
      </div>
    </div>
  )
}

function DetailField({
  label,
  value,
  className,
}: {
  label: string
  value: string
  className?: string
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label>{label}</Label>
      <div className="rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground">
        {value}
      </div>
    </div>
  )
}

function ExternalAgentConfigFields({
  agent,
  form,
  setForm,
  canEdit,
  isSaving,
  idPrefix,
}: {
  agent: Agent
  form: ExternalAgentCreateDraft
  setForm: Dispatch<SetStateAction<ExternalAgentCreateDraft>>
  canEdit: boolean
  isSaving: boolean
  idPrefix: string
}) {
  const details = resolveExternalAgentDetails(agent)

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-external-name`}>
            名称 <span className="text-destructive">*</span>
          </Label>
          <Input
            id={`${idPrefix}-external-name`}
            value={form.name}
            disabled={!canEdit || isSaving}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-external-tag`}>
            系统标签 <span className="text-destructive">*</span>
          </Label>
          <Select value={form.tag} disabled={!canEdit || isSaving} onValueChange={(value) => setForm((current) => ({ ...current, tag: value as SystemTagOption }))}>
            <SelectTrigger id={`${idPrefix}-external-tag`}>
              <SelectValue placeholder="选择系统标签" />
            </SelectTrigger>
            <SelectContent>
              {EXTERNAL_SYSTEM_TAG_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor={`${idPrefix}-external-endpoint`}>
            接入地址 <span className="text-destructive">*</span>
          </Label>
          <Input
            id={`${idPrefix}-external-endpoint`}
            value={buildEndpointFieldValue(form.baseUrl, form.invokePath)}
            disabled={!canEdit || isSaving}
            onChange={(event) => {
              const nextValue = splitEndpointFieldValue(event.target.value)
              setForm((current) => ({
                ...current,
                baseUrl: nextValue.baseUrl,
                invokePath: nextValue.invokePath,
              }))
            }}
            placeholder="http://host.docker.internal:8642/v1/chat/completions"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-external-method`}>
            请求方式 <span className="text-destructive">*</span>
          </Label>
          <Select
            value={form.method}
            disabled={!canEdit || isSaving}
            onValueChange={(value) => setForm((current) => ({ ...current, method: value }))}
          >
            <SelectTrigger id={`${idPrefix}-external-method`}>
              <SelectValue placeholder="选择请求方式" />
            </SelectTrigger>
            <SelectContent>
              {EXTERNAL_AGENT_METHOD_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <DetailField label="最近心跳" value={details.lastHeartbeatAt} />
      </div>

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-external-description`}>描述</Label>
        <Textarea
          id={`${idPrefix}-external-description`}
          value={form.description}
          disabled={!canEdit || isSaving}
          onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
          rows={4}
        />
      </div>
    </div>
  )
}

function AgentConfigDialog({
  open,
  agents,
  executors,
  executorsLoading,
  executorsError,
  onRetryBrainSkills,
  onRetryMcpTools,
  onRetryExecutors,
  modelOptions,
  brainSkills,
  brainSkillsLoading,
  brainSkillsError,
  mcpTools,
  mcpToolsLoading,
  mcpToolsError,
  canEdit,
  isSavingLocal,
  isSavingExternal,
  onOpenChange,
  onSubmitLocal,
  onSubmitExternal,
}: {
  open: boolean
  agents: Agent[]
  executors: Executor[]
  executorsLoading: boolean
  executorsError: Error | null
  onRetryBrainSkills: () => void
  onRetryMcpTools: () => void
  onRetryExecutors: () => void
  modelOptions: ModelOption[]
  brainSkills: BrainSkillItem[]
  brainSkillsLoading: boolean
  brainSkillsError: Error | null
  mcpTools: AgentBindableTool[]
  mcpToolsLoading: boolean
  mcpToolsError: Error | null
  canEdit: boolean
  isSavingLocal: boolean
  isSavingExternal: boolean
  onOpenChange: (open: boolean) => void
  onSubmitLocal: (payload: AgentConfigRequest) => Promise<void>
  onSubmitExternal: (payload: ExternalAgentCreateRequest) => Promise<void>
}) {
  const [source, setSource] = useState<AgentCreateSource>("local")
  const [localDraft, setLocalDraft] = useState<LocalAgentCreateDraft>(() =>
    defaultLocalAgentCreateDraft(modelOptions, executors),
  )
  const [externalDraft, setExternalDraft] = useState<ExternalAgentCreateDraft>(() =>
    defaultExternalAgentCreateDraft(),
  )
  const [skillPickerOpen, setSkillPickerOpen] = useState(false)
  const [toolPickerOpen, setToolPickerOpen] = useState(false)
  const [skillPickerDraftIds, setSkillPickerDraftIds] = useState<string[]>([])
  const [toolPickerDraftIds, setToolPickerDraftIds] = useState<string[]>([])
  const isSaving = isSavingLocal || isSavingExternal
  const skillPickerSelectedIds = useMemo(() => new Set(skillPickerDraftIds), [skillPickerDraftIds])
  const toolPickerSelectedIds = useMemo(() => new Set(toolPickerDraftIds), [toolPickerDraftIds])
  const selectedSkillNames = useMemo(() => {
    if (localDraft.selectedSkillIds.length === 0) return []
    const skillNameMap = new Map(brainSkills.map((skill) => [skill.id, skill.name]))
    return localDraft.selectedSkillIds.map((skillId) => skillNameMap.get(skillId)).filter(Boolean) as string[]
  }, [brainSkills, localDraft.selectedSkillIds])
  const selectedToolNames = useMemo(() => {
    if (localDraft.selectedToolIds.length === 0) return []
    const toolNameMap = new Map(mcpTools.map((tool) => [tool.id, tool.name]))
    return localDraft.selectedToolIds.map((toolId) => toolNameMap.get(toolId)).filter(Boolean) as string[]
  }, [localDraft.selectedToolIds, mcpTools])

  useEffect(() => {
    if (!open) return
    setSource("local")
    setLocalDraft(defaultLocalAgentCreateDraft(modelOptions, executors))
    setExternalDraft(defaultExternalAgentCreateDraft())
    setSkillPickerOpen(false)
    setToolPickerOpen(false)
    setSkillPickerDraftIds([])
    setToolPickerDraftIds([])
  }, [executors, modelOptions, open])

  const handleSubmitLocal = async () => {
    const name = localDraft.name.trim()
    if (!name) {
      toast({
        title: "名称不能为空",
        description: "请先填写智能体名称。",
      })
      return
    }

    if (!localDraft.selectedModel.trim()) {
      toast({
        title: "模型未配置",
        description: "请选择项目内启用模型。",
      })
      return
    }

    const { providerKey, model } = parseModelValue(localDraft.selectedModel)
    if (!providerKey || !model) {
      toast({
        title: "模型配置无效",
        description: "请重新选择项目内启用模型。",
      })
      return
    }

    if (localDraft.runMode === "single" && !localDraft.executorId.trim()) {
      toast({
        title: "执行器未配置",
        description: "请选择一个执行器。",
      })
      return
    }

    if (!localDraft.tag) {
      toast({
        title: "标签未配置",
        description: "请选择系统标签。",
      })
      return
    }
    const expectedTag = defaultLocalTagByRunMode(localDraft.runMode)
    if (localDraft.tag !== expectedTag) {
      toast({
        title: "系统标签不匹配",
        description: `当前运行模式应使用标签“${expectedTag}”。`,
      })
      return
    }

    const tags = [localDraft.tag]
    const metadata: Record<string, unknown> = {
      source: "local_agent_create",
      tags,
      runMode: localDraft.runMode,
      executorId: localDraft.runMode === "single" ? localDraft.executorId.trim() : null,
    }
    let inputContract: Record<string, unknown> = {}
    let outputContract: Record<string, unknown> = {}

    if (localDraft.runMode === "multi") {
      const normalizedMembers = localDraft.multiMembers.map((member) => ({
        ...member,
        agentId: member.agentId.trim(),
      }))
      if (normalizedMembers.length < 3) {
        toast({
          title: "成员配置不足",
          description: "多智能体团队至少需要 3 个成员。",
        })
        return
      }
      const dispatcherMembers = normalizedMembers.filter((member) => member.role === "dispatcher")
      const workerMembers = normalizedMembers.filter((member) => member.role === "worker")
      if (dispatcherMembers.length !== 1) {
        toast({
          title: "角色配置不完整",
          description: "必须且仅能有 1 个需求分发角色。",
        })
        return
      }
      if (workerMembers.length < 2) {
        toast({
          title: "角色配置不完整",
          description: "执行角色至少需要 2 个。",
        })
        return
      }
      const unboundMember = normalizedMembers.find((member) => !member.agentId)
      if (unboundMember) {
        toast({
          title: "成员未绑定",
          description: "请为每个角色选择绑定的 Agent。",
        })
        return
      }
      const selectedAgentIds = normalizedMembers.map((member) => member.agentId)
      if (new Set(selectedAgentIds).size !== selectedAgentIds.length) {
        toast({
          title: "成员绑定冲突",
          description: "同一个 Agent 不能重复绑定多个角色。",
        })
        return
      }

      inputContract = {
        orchestration: {
          runMode: "multi",
          team: {
            members: normalizedMembers.map((member, index) => ({
              role: member.role,
              agentId: member.agentId,
              order: index + 1,
            })),
          },
        },
      }
      metadata.multiAgent = {
        runMode: "multi",
        teamSize: normalizedMembers.length,
        dispatcherAgentId: dispatcherMembers[0]?.agentId ?? null,
        workerAgentIds: workerMembers.map((member) => member.agentId),
      }
    } else {
      metadata.singleAgent = {
        runMode: "single",
        skillCount: localDraft.selectedSkillIds.length,
        toolCount: localDraft.selectedToolIds.length,
      }
    }

    await onSubmitLocal({
      name,
      description: localDraft.description.trim(),
      type: localDraft.runMode === "multi" ? "task_dispatcher" : "default",
      enabled: true,
      soul: localDraft.soul.trim() || null,
      providerKey,
      model,
      skillIds: localDraft.runMode === "single" ? localDraft.selectedSkillIds : [],
      toolIds: localDraft.runMode === "single" ? localDraft.selectedToolIds : [],
      inputContract,
      outputContract,
      contractVersion: localDraft.runMode === "multi" ? "agent-contract-v2" : null,
      metadata,
    })
  }

  const handleSubmitExternal = async () => {
    const name = externalDraft.name.trim()
    const baseUrl = externalDraft.baseUrl.trim()
    const invokePath = externalDraft.invokePath.trim()
    const healthPath = externalDraft.healthPath.trim()
    if (!name) {
      toast({
        title: "名称不能为空",
        description: "请填写智能体名称。",
      })
      return
    }
    if (!baseUrl) {
      toast({
        title: "接入地址不能为空",
        description: "请填写完整的外部智能体接入地址。",
      })
      return
    }
    if (!invokePath) {
      toast({
        title: "接入地址不完整",
        description: "请填写包含调用路径的完整接入地址。",
      })
      return
    }
    if (!externalDraft.tag) {
      toast({
        title: "系统标签未配置",
        description: "请选择系统标签。",
      })
      return
    }
    if (!externalDraft.tag.startsWith("外部")) {
      toast({
        title: "系统标签不匹配",
        description: "外部智能体只能使用“外部 · …”系统标签。",
      })
      return
    }

    const id = externalDraft.id.trim() || buildExternalAgentId(name)

    await onSubmitExternal({
      id,
      name,
      description: externalDraft.description.trim(),
      type: "write",
      agentFamily: EXTERNAL_RECEPTION_FAMILY,
      version: externalDraft.version.trim() || "1.0.0",
      protocol: externalDraft.protocol.trim() || "http",
      baseUrl,
      invokePath,
      healthPath: healthPath || "/health",
      method: externalDraft.method.trim() || "POST",
      releaseChannel: externalDraft.releaseChannel.trim() || "stable",
      remoteModel: EXTERNAL_RECEPTION_REMOTE_MODEL,
      heartbeatIntervalSeconds: parseOptionalIntegerInput(externalDraft.heartbeatIntervalSeconds),
      heartbeatTimeoutSeconds: parseOptionalIntegerInput(externalDraft.heartbeatTimeoutSeconds),
      enabled: true,
      capabilities: parseCommaSeparatedInput(externalDraft.capabilitiesInput),
      compatibility: parseCommaSeparatedInput(externalDraft.compatibilityInput),
      tags: [externalDraft.tag],
    })
  }

  const handleOpenSkillPicker = () => {
    setSkillPickerDraftIds(localDraft.selectedSkillIds)
    setSkillPickerOpen(true)
  }

  const handleOpenToolPicker = () => {
    setToolPickerDraftIds(localDraft.selectedToolIds)
    setToolPickerOpen(true)
  }

  const handleAddMultiMember = () => {
    setLocalDraft((draft) => ({
      ...draft,
      multiMembers: [...draft.multiMembers, { id: createWorkerMemberId(), fixed: false, role: "worker", agentId: "" }],
    }))
  }

  const handleRemoveMultiMember = (memberId: string) => {
    setLocalDraft((current) => {
      const target = current.multiMembers.find((item) => item.id === memberId)
      if (!target || target.fixed || target.role === "dispatcher") return current
      return {
        ...current,
        multiMembers: current.multiMembers.filter((item) => item.id !== memberId),
      }
    })
  }

  const handleConfirmSkillPicker = () => {
    setLocalDraft((current) => ({
      ...current,
      selectedSkillIds: [...new Set(skillPickerDraftIds)],
    }))
    setSkillPickerOpen(false)
  }

  const handleConfirmToolPicker = () => {
    setLocalDraft((current) => ({
      ...current,
      selectedToolIds: [...new Set(toolPickerDraftIds)],
    }))
    setToolPickerOpen(false)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88vh] max-h-[88vh] flex-col overflow-hidden sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>新增 Agent</DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto py-2 pr-1">
          <Tabs value={source} onValueChange={(value) => setSource(value as AgentCreateSource)}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="local">本地智能体</TabsTrigger>
              <TabsTrigger value="external">外部智能体接入</TabsTrigger>
            </TabsList>
          </Tabs>

          {source === "local" ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="create-local-name">
                    名称 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="create-local-name"
                    value={localDraft.name}
                    disabled={!canEdit || isSaving}
                    onChange={(event) => setLocalDraft((current) => ({ ...current, name: event.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-local-tag">
                    系统标签 <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={localDraft.tag}
                    disabled={!canEdit || isSaving}
                    onValueChange={(value) =>
                      setLocalDraft((current) => ({ ...current, tag: value as SystemTagOption }))
                    }
                  >
                    <SelectTrigger id="create-local-tag">
                      <SelectValue placeholder="请选择系统标签" />
                    </SelectTrigger>
                    <SelectContent>
                      {LOCAL_SYSTEM_TAG_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label>
                  运行模式 <span className="text-destructive">*</span>
                </Label>
                <Tabs
                  value={localDraft.runMode}
                  onValueChange={(value) =>
                    setLocalDraft((current) => {
                      const nextRunMode = value as LocalAgentRunMode
                      const nextDefaultTag = defaultLocalTagByRunMode(nextRunMode)
                      const nextTag =
                        current.tag === LOCAL_SINGLE_TAG || current.tag === LOCAL_MULTI_TAG
                          ? nextDefaultTag
                          : current.tag
                      return {
                        ...current,
                        runMode: nextRunMode,
                        tag: nextTag,
                      }
                    })
                  }
                >
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="single">单智能体</TabsTrigger>
                    <TabsTrigger value="multi">多智能体</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {localDraft.runMode === "single" ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="create-local-model">
                      模型 <span className="text-destructive">*</span>
                    </Label>
                    <Select
                      value={localDraft.selectedModel}
                      disabled={!canEdit || isSaving || modelOptions.length === 0}
                      onValueChange={(value) =>
                        setLocalDraft((current) => ({ ...current, selectedModel: value }))
                      }
                    >
                      <SelectTrigger id="create-local-model">
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
                    {modelOptions.length === 0 ? (
                      <div className="text-xs text-destructive">未检测到已启用模型，请先到模型接入页启用。</div>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="create-local-executor">
                      执行器 <span className="text-destructive">*</span>
                    </Label>
                    <Select
                      value={localDraft.executorId}
                      disabled={!canEdit || isSaving || executorsLoading || executors.length === 0}
                      onValueChange={(value) => setLocalDraft((current) => ({ ...current, executorId: value }))}
                    >
                      <SelectTrigger id="create-local-executor">
                        <SelectValue placeholder="选择执行器" />
                      </SelectTrigger>
                      <SelectContent>
                        {executors.map((executor) => (
                          <SelectItem key={executor.id} value={executor.id}>
                            {executor.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {executorsError ? (
                      <div className="flex items-center justify-between rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                        <span>
                          {executorsError.message.includes("timeout") ? "执行器加载超时" : `执行器加载失败：${executorsError.message}`}
                        </span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7"
                          disabled={isSaving}
                          onClick={() => onRetryExecutors()}
                        >
                          重试
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {localDraft.runMode === "single" ? (
                <>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Skill 绑定（可选）</Label>
                      <span className="text-xs text-muted-foreground">已选 {localDraft.selectedSkillIds.length}</span>
                    </div>
                    <div className="space-y-2 rounded-lg border border-border bg-secondary/10 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm text-muted-foreground">
                          {localDraft.selectedSkillIds.length > 0
                            ? `已选择 ${localDraft.selectedSkillIds.length} 个 Skill`
                            : "暂未选择 Skill"}
                        </span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={!canEdit || isSaving || brainSkillsLoading}
                          onClick={handleOpenSkillPicker}
                        >
                          选择 Skill
                        </Button>
                      </div>
                      {brainSkillsLoading ? (
                        <div className="text-sm text-muted-foreground">正在加载本地 Skill...</div>
                      ) : brainSkillsError ? (
                        <div className="flex items-center justify-between rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                          <span>
                            {brainSkillsError.message.includes("timeout")
                              ? "本地 Skill 加载超时"
                              : `本地 Skill 加载失败：${brainSkillsError.message}`}
                          </span>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7"
                            disabled={isSaving}
                            onClick={() => onRetryBrainSkills()}
                          >
                            重试
                          </Button>
                        </div>
                      ) : brainSkills.length === 0 ? null : selectedSkillNames.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {selectedSkillNames.slice(0, 4).map((name, index) => (
                            <Badge key={`${name}-${index}`} variant="secondary" className="text-[11px]">
                              {name}
                            </Badge>
                          ))}
                          {selectedSkillNames.length > 4 ? (
                            <Badge variant="secondary" className="text-[11px] text-muted-foreground">
                              +{selectedSkillNames.length - 4}
                            </Badge>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>MCP 绑定（可选）</Label>
                      <span className="text-xs text-muted-foreground">已选 {localDraft.selectedToolIds.length}</span>
                    </div>
                    <div className="space-y-2 rounded-lg border border-border bg-secondary/10 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm text-muted-foreground">
                          {localDraft.selectedToolIds.length > 0
                            ? `已选择 ${localDraft.selectedToolIds.length} 个 MCP`
                            : "暂未选择 MCP"}
                        </span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={!canEdit || isSaving || mcpToolsLoading}
                          onClick={handleOpenToolPicker}
                        >
                          选择 MCP
                        </Button>
                      </div>
                      {mcpToolsLoading ? (
                        <div className="text-sm text-muted-foreground">正在加载 MCP 工具目录...</div>
                      ) : mcpToolsError ? (
                        <div className="flex items-center justify-between rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                          <span>
                            {mcpToolsError.message.includes("timeout")
                              ? "MCP 工具加载超时"
                              : `MCP 工具加载失败：${mcpToolsError.message}`}
                          </span>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7"
                            disabled={isSaving}
                            onClick={() => onRetryMcpTools()}
                          >
                            重试
                          </Button>
                        </div>
                      ) : mcpTools.length === 0 ? null : selectedToolNames.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {selectedToolNames.slice(0, 4).map((name, index) => (
                            <Badge key={`${name}-${index}`} variant="secondary" className="text-[11px]">
                              {name}
                            </Badge>
                          ))}
                          {selectedToolNames.length > 4 ? (
                            <Badge variant="secondary" className="text-[11px] text-muted-foreground">
                              +{selectedToolNames.length - 4}
                            </Badge>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label>
                      成员列表 <span className="text-destructive">*</span>
                    </Label>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!canEdit || isSaving}
                      onClick={handleAddMultiMember}
                    >
                      添加成员
                    </Button>
                  </div>
                  <div className="space-y-2 rounded-lg border border-border bg-secondary/10 p-3">
                    {localDraft.multiMembers.map((member, index) => (
                      <div
                        key={member.id}
                        className="grid gap-2 rounded-md border border-border/80 bg-background/70 p-3 sm:grid-cols-[140px_minmax(0,1fr)_80px]"
                      >
                        <div className="space-y-1">
                          <Label>角色</Label>
                          <Input
                            value={member.role === "dispatcher" ? "需求分发" : "执行"}
                            readOnly
                            disabled
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`create-multi-agent-${member.id}`}>
                            绑定 Agent <span className="text-destructive">*</span>
                          </Label>
                          <Select
                            value={member.agentId}
                            disabled={!canEdit || isSaving || agents.length === 0}
                            onValueChange={(value) =>
                              setLocalDraft((current) => ({
                                ...current,
                                multiMembers: current.multiMembers.map((item) =>
                                  item.id === member.id ? { ...item, agentId: value } : item,
                                ),
                              }))
                            }
                          >
                            <SelectTrigger id={`create-multi-agent-${member.id}`}>
                              <SelectValue placeholder="选择 Agent" />
                            </SelectTrigger>
                            <SelectContent>
                              {agents.map((agent) => (
                                <SelectItem key={agent.id} value={agent.id}>
                                  {agent.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1">
                          <Label>操作</Label>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="w-full"
                            disabled={!canEdit || isSaving || member.fixed || member.role === "dispatcher"}
                            onClick={() => handleRemoveMultiMember(member.id)}
                          >
                            删除
                          </Button>
                        </div>
                        {member.fixed ? (
                          <div className="sm:col-span-3 text-xs text-muted-foreground">
                            {index === 0 ? "默认分发角色（固定）" : "默认执行角色（固定）"}
                          </div>
                        ) : null}
                      </div>
                    ))}
                    {agents.length === 0 ? (
                      <div className="text-sm text-destructive">暂无可绑定 Agent，请先在列表中创建或接入 Agent。</div>
                    ) : null}
                    <div className="text-xs text-muted-foreground">至少 1 个需求分发角色 + 2 个执行角色，可继续添加执行角色。</div>
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="create-local-description">描述（可选）</Label>
                <Textarea
                  id="create-local-description"
                  rows={2}
                  value={localDraft.description}
                  disabled={!canEdit || isSaving}
                  onChange={(event) => setLocalDraft((current) => ({ ...current, description: event.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="create-local-soul">soul.md 配置</Label>
                <Textarea
                  id="create-local-soul"
                  rows={10}
                  value={localDraft.soul}
                  disabled={!canEdit || isSaving}
                  placeholder={"# Soul\n\n你是谁、负责什么、与用户或其他智能体协作时有哪些规则。"}
                  onChange={(event) => setLocalDraft((current) => ({ ...current, soul: event.target.value }))}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="create-external-name">
                    名称 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="create-external-name"
                    value={externalDraft.name}
                    disabled={!canEdit || isSaving}
                    onChange={(event) =>
                      setExternalDraft((current) => ({ ...current, name: event.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-external-tag">
                    系统标签 <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={externalDraft.tag}
                    disabled={!canEdit || isSaving}
                    onValueChange={(value) =>
                      setExternalDraft((current) => ({ ...current, tag: value as SystemTagOption }))
                    }
                  >
                    <SelectTrigger id="create-external-tag">
                      <SelectValue placeholder="请选择系统标签" />
                    </SelectTrigger>
                    <SelectContent>
                      {EXTERNAL_SYSTEM_TAG_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="create-external-endpoint">
                    接入地址 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="create-external-endpoint"
                    value={buildEndpointFieldValue(externalDraft.baseUrl, externalDraft.invokePath)}
                    disabled={!canEdit || isSaving}
                    placeholder="http://host.docker.internal:8642/v1/chat/completions"
                    onChange={(event) => {
                      const nextValue = splitEndpointFieldValue(event.target.value)
                      setExternalDraft((current) => ({
                        ...current,
                        baseUrl: nextValue.baseUrl,
                        invokePath: nextValue.invokePath,
                      }))
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-external-method">
                    请求方式 <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={externalDraft.method}
                    disabled={!canEdit || isSaving}
                    onValueChange={(value) =>
                      setExternalDraft((current) => ({ ...current, method: value }))
                    }
                  >
                    <SelectTrigger id="create-external-method">
                      <SelectValue placeholder="请选择请求方式" />
                    </SelectTrigger>
                    <SelectContent>
                      {EXTERNAL_AGENT_METHOD_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                    </Select>
                  </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="create-external-description">描述</Label>
                <Textarea
                  id="create-external-description"
                  rows={3}
                  value={externalDraft.description}
                  disabled={!canEdit || isSaving}
                  onChange={(event) =>
                    setExternalDraft((current) => ({ ...current, description: event.target.value }))
                  }
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={isSaving} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={
              !canEdit ||
              isSaving ||
              (source === "local" && modelOptions.length === 0)
            }
            onClick={() => void (source === "local" ? handleSubmitLocal() : handleSubmitExternal())}
          >
            {isSaving ? "保存中..." : source === "local" ? "创建本地智能体" : "接入外部智能体"}
          </Button>
        </DialogFooter>
      </DialogContent>
      </Dialog>

      <Dialog
        open={skillPickerOpen}
        onOpenChange={(nextOpen) => {
          if (nextOpen) {
            setSkillPickerDraftIds(localDraft.selectedSkillIds)
          }
          setSkillPickerOpen(nextOpen)
        }}
      >
        <DialogContent className="flex h-[72vh] max-h-[72vh] flex-col overflow-hidden sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>选择 Skill</DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {brainSkillsLoading ? (
              <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
                正在加载本地 Skill...
              </div>
            ) : brainSkillsError ? (
              <div className="flex items-center justify-between rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                <span>
                  {brainSkillsError.message.includes("timeout")
                    ? "本地 Skill 加载超时"
                    : `本地 Skill 加载失败：${brainSkillsError.message}`}
                </span>
                <Button type="button" variant="outline" size="sm" className="h-7" disabled={isSaving} onClick={onRetryBrainSkills}>
                  重试
                </Button>
              </div>
            ) : brainSkills.length === 0 ? null : (
              <div className="space-y-2">
                {brainSkills.map((skill) => {
                  const checked = skillPickerSelectedIds.has(skill.id)
                  const meta = [skill.fileName, skill.format].filter(Boolean).join(" · ")
                  const tags = skill.tags ?? []
                  return (
                    <label
                      key={skill.id}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-lg border border-transparent px-3 py-2 transition-colors",
                        checked ? "bg-card shadow-sm ring-1 ring-border" : "hover:bg-card/70",
                        (!canEdit || isSaving) && "cursor-not-allowed opacity-70",
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        disabled={!canEdit || isSaving}
                        onCheckedChange={(nextChecked) =>
                          setSkillPickerDraftIds((current) =>
                            nextChecked === true
                              ? [...new Set([...current, skill.id])]
                              : current.filter((item) => item !== skill.id),
                          )
                        }
                      />
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-foreground">{skill.name}</div>
                          {meta ? <div className="truncate text-xs text-muted-foreground">{meta}</div> : null}
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
          <DialogFooter>
            <Button variant="outline" disabled={isSaving} onClick={() => setSkillPickerOpen(false)}>
              取消
            </Button>
            <Button
              disabled={!canEdit || isSaving || brainSkillsLoading || Boolean(brainSkillsError)}
              onClick={handleConfirmSkillPicker}
            >
              确认
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={toolPickerOpen}
        onOpenChange={(nextOpen) => {
          if (nextOpen) {
            setToolPickerDraftIds(localDraft.selectedToolIds)
          }
          setToolPickerOpen(nextOpen)
        }}
      >
        <DialogContent className="flex h-[72vh] max-h-[72vh] flex-col overflow-hidden sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>选择 MCP</DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {mcpToolsLoading ? (
              <div className="rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
                正在加载 MCP 工具目录...
              </div>
            ) : mcpToolsError ? (
              <div className="flex items-center justify-between rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                <span>
                  {mcpToolsError.message.includes("timeout")
                    ? "MCP 工具加载超时"
                    : `MCP 工具加载失败：${mcpToolsError.message}`}
                </span>
                <Button type="button" variant="outline" size="sm" className="h-7" disabled={isSaving} onClick={onRetryMcpTools}>
                  重试
                </Button>
              </div>
            ) : mcpTools.length === 0 ? null : (
              <div className="space-y-2">
                {mcpTools.map((tool) => {
                  const checked = toolPickerSelectedIds.has(tool.id)
                  const meta = [tool.source, tool.type.toUpperCase()].filter(Boolean).join(" · ")
                  return (
                    <label
                      key={tool.id}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-lg border border-transparent px-3 py-2 transition-colors",
                        checked ? "bg-card shadow-sm ring-1 ring-border" : "hover:bg-card/70",
                        (!canEdit || isSaving) && "cursor-not-allowed opacity-70",
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        disabled={!canEdit || isSaving}
                        onCheckedChange={(nextChecked) =>
                          setToolPickerDraftIds((current) =>
                            nextChecked === true
                              ? [...new Set([...current, tool.id])]
                              : current.filter((item) => item !== tool.id),
                          )
                        }
                      />
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="truncate text-sm font-medium text-foreground">{tool.name}</div>
                        {meta ? <div className="truncate text-xs text-muted-foreground">{meta}</div> : null}
                        {tool.description ? <div className="text-xs text-muted-foreground">{tool.description}</div> : null}
                      </div>
                    </label>
                  )
                })}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={isSaving} onClick={() => setToolPickerOpen(false)}>
              取消
            </Button>
            <Button
              disabled={!canEdit || isSaving || mcpToolsLoading || Boolean(mcpToolsError)}
              onClick={handleConfirmToolPicker}
            >
              确认
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function AgentListItem({
  agent,
  isActive,
  onSelect,
}: {
  agent: Agent
  isActive: boolean
  onSelect: (agentId: string) => void
}) {
  const runtimeStatus = agent.runtimeStatus ?? "unknown"
  const showPrimaryStatus = agent.status !== "waiting"
  const showRuntimeStatus = runtimeStatus !== "unknown"
  const systemTag = inferSystemTag(agent)
  const taskChildBinding = resolveTaskChildBinding(agent)
  const externalDetails = isExternalAgentView(agent) ? resolveExternalAgentDetails(agent) : null
  const externalEndpoint = externalDetails
    ? buildEndpointFieldValue(
        externalDetails.baseUrl === "未配置" ? "" : externalDetails.baseUrl,
        externalDetails.invokePath === "未配置" ? "" : externalDetails.invokePath,
      ) || "未配置"
    : null

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
              {systemTag ? (
                <Badge variant="outline" className="text-xs">
                  {systemTag}
                </Badge>
              ) : null}
              {taskChildBinding ? (
                <Badge variant="outline" className="text-xs">
                  任务子智能体
                </Badge>
              ) : null}
            </div>
          ) : systemTag ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="text-xs">
                {systemTag}
              </Badge>
              {taskChildBinding ? (
                <Badge variant="outline" className="text-xs">
                  任务子智能体
                </Badge>
              ) : null}
            </div>
          ) : taskChildBinding ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="text-xs">
                任务子智能体
              </Badge>
            </div>
          ) : null}

          <div className="space-y-0.5 text-xs text-muted-foreground">
            <div className="truncate">{externalEndpoint ? `接入：${externalEndpoint}` : `模型：${agent.modelBinding?.model ?? "未配置"}`}</div>
            <div className="truncate">
              {taskChildBinding
                ? `归属任务：${taskChildBinding.taskId}${taskChildBinding.role ? ` · ${taskChildBinding.role}` : ""}`
                : `Skill：${resolveAgentBoundSkillIds(agent).length}`}
            </div>
          </div>
        </div>
      </div>
    </button>
  )
}

function AgentDetailPanel({
  agent,
  agents,
  modelOptions,
  executors,
  executorsLoading,
  executorsError,
  onRetryExecutors,
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
  onSaveExternal,
}: {
  agent: Agent
  agents: Agent[]
  modelOptions: ModelOption[]
  executors: Executor[]
  executorsLoading: boolean
  executorsError: Error | null
  onRetryExecutors: () => void
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
  onSaveExternal: (payload: ExternalAgentCreateRequest) => Promise<void>
}) {
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [form, setForm] = useState<AgentFormState>(() => defaultFormState(agent, modelOptions))
  const [externalForm, setExternalForm] = useState<ExternalAgentCreateDraft>(() => defaultExternalAgentDetailDraft(agent))
  const runtimeStatus = agent.runtimeStatus ?? "unknown"
  const showPrimaryStatus = agent.status !== "waiting"
  const showRuntimeStatus = runtimeStatus !== "unknown"
  const isExternalView = isExternalAgentView(agent)
  const isMultiAgentView = !isExternalView && resolveAgentRunMode(agent) === "multi"
  const systemTag = inferSystemTag(agent)
  const taskChildBinding = resolveTaskChildBinding(agent)
  const isTaskChildView = Boolean(taskChildBinding)
  const canManageAgent = canEdit && !isTaskChildView

  useEffect(() => {
    setForm(defaultFormState(agent, modelOptions))
    setExternalForm(defaultExternalAgentDetailDraft(agent))
  }, [agent, modelOptions])

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

  const handleSaveExternal = async () => {
    const name = externalForm.name.trim()
    const baseUrl = externalForm.baseUrl.trim()
    const invokePath = externalForm.invokePath.trim()
    const healthPath = externalForm.healthPath.trim()
    if (!name) {
      toast({
        title: "名称不能为空",
        description: "请填写智能体名称。",
      })
      return
    }

    const id = externalForm.id.trim() || buildExternalAgentId(name)
    if (!baseUrl) {
      toast({
        title: "接入地址不能为空",
        description: "请填写完整的外部智能体接入地址。",
      })
      return
    }
    if (!invokePath) {
      toast({
        title: "接入地址不完整",
        description: "请填写包含调用路径的完整接入地址。",
      })
      return
    }
    if (!externalForm.tag) {
      toast({
        title: "系统标签未配置",
        description: "请选择系统标签。",
      })
      return
    }
    if (!externalForm.tag.startsWith("外部")) {
      toast({
        title: "系统标签不匹配",
        description: "外部智能体只能使用“外部 · …”系统标签。",
      })
      return
    }

    try {
      await onSaveExternal({
        id,
        name,
        description: externalForm.description.trim(),
        type: "write",
        agentFamily: EXTERNAL_RECEPTION_FAMILY,
        version: externalForm.version.trim() || "1.0.0",
        protocol: externalForm.protocol.trim() || "http",
        baseUrl,
        invokePath,
        healthPath: healthPath || "/health",
        method: externalForm.method.trim() || "POST",
        releaseChannel: externalForm.releaseChannel.trim() || "stable",
        remoteModel: EXTERNAL_RECEPTION_REMOTE_MODEL,
        heartbeatIntervalSeconds: parseOptionalIntegerInput(externalForm.heartbeatIntervalSeconds),
        heartbeatTimeoutSeconds: parseOptionalIntegerInput(externalForm.heartbeatTimeoutSeconds),
        enabled: form.enabled,
        capabilities: parseCommaSeparatedInput(externalForm.capabilitiesInput),
        compatibility: parseCommaSeparatedInput(externalForm.compatibilityInput),
        tags: [externalForm.tag],
      })
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
                {systemTag ? (
                  <Badge variant="outline" className="text-xs">
                    {systemTag}
                  </Badge>
                ) : null}
              </div>
            </div>
          </div>

          <div className="flex flex-col items-end gap-2 xl:min-w-[260px]">
            <div className="flex items-center justify-end gap-3">
              <div className="flex items-center gap-2">
                <Switch
                  checked={form.enabled}
                  disabled={!canManageAgent || isTogglingEnabled || isSaving}
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
                disabled={!canManageAgent || isDeleting || isSaving}
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
        {taskChildBinding ? (
          <div className="mb-4 rounded-lg border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
            该智能体由需求下发流程为任务 {taskChildBinding.taskId} 自动生成，默认归属任务域管理。
            {taskChildBinding.groupName ? ` 当前编组：${taskChildBinding.groupName}。` : ""}
            Agent 管理页仅保留查看，不建议在这里直接修改。
          </div>
        ) : null}
        {isExternalView ? (
          <ExternalAgentConfigFields
            agent={agent}
            form={externalForm}
            setForm={setExternalForm}
            canEdit={canManageAgent}
            isSaving={isSaving}
            idPrefix={`agent-detail-${agent.id}`}
          />
        ) : isMultiAgentView ? (
          <MultiAgentConfigFields
            form={form}
            setForm={setForm}
            canEdit={canManageAgent}
            isSaving={isSaving}
            agents={agents}
            idPrefix={`agent-detail-${agent.id}`}
          />
        ) : (
          <AgentConfigFields
            form={form}
            setForm={setForm}
            modelOptions={modelOptions}
            executors={executors}
            executorsLoading={executorsLoading}
            executorsError={executorsError}
            onRetryExecutors={onRetryExecutors}
            brainSkills={brainSkills}
            brainSkillsLoading={brainSkillsLoading}
            brainSkillsError={brainSkillsError}
            mcpTools={mcpTools}
            mcpToolsLoading={mcpToolsLoading}
            mcpToolsError={mcpToolsError}
            canEdit={canManageAgent}
            isSaving={isSaving}
            idPrefix={`agent-detail-${agent.id}`}
            showEnabledField={false}
          />
        )}
      </CardContent>

      <div className="flex items-center justify-end gap-2 border-t border-border/60 px-5 py-3">
        {isExternalView ? (
          <Button disabled={!canManageAgent || isSaving} onClick={() => void handleSaveExternal()}>
            {isSaving ? "保存中..." : "保存配置"}
          </Button>
        ) : (
          <>
            <Button
              variant="outline"
              disabled={!canManageAgent || isSaving}
              onClick={() => void onReload(agent.id)}
            >
              热重载
            </Button>
            <Button disabled={!canManageAgent || isSaving || modelOptions.length === 0} onClick={() => void handleSave()}>
              {isSaving ? "保存中..." : "保存配置"}
            </Button>
          </>
        )}
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
  const { data, isLoading, error, refetch: refetchAgents } = useAgents()
  const {
    data: brainSkillsData,
    isLoading: brainSkillsLoading,
    isFetching: brainSkillsFetching,
    error: brainSkillsQueryError,
    refetch: refetchBrainSkills,
  } = useBrainSkills()
  const {
    data: mcpToolsData,
    isLoading: mcpToolsLoading,
    isFetching: mcpToolsFetching,
    error: mcpToolsQueryError,
    refetch: refetchMcpTools,
  } = useAgentMcpTools()
  const {
    data: executorsData,
    isLoading: executorsLoading,
    isFetching: executorsFetching,
    error: executorsQueryError,
    refetch: refetchExecutors,
  } = useExecutors()
  const { data: agentApiSettings } = useAgentApiSettings()
  const reloadAgentMutation = useReloadAgent()
  const createAgentMutation = useCreateAgent()
  const registerExternalAgentMutation = useRegisterExternalAgent()
  const deleteAgentMutation = useDeleteAgent()
  const setAgentEnabledMutation = useSetAgentEnabled()
  const updateAgentConfigMutation = useUpdateAgentConfig()
  const agents = useMemo(() => data?.items ?? [], [data?.items])
  const visibleAgents = useMemo(
    () => agents.filter((agent) => !isTaskChildAgent(agent)),
    [agents],
  )
  const brainSkills = useMemo(() => brainSkillsData?.items ?? [], [brainSkillsData?.items])
  const mcpTools = useMemo(() => mcpToolsData?.items ?? [], [mcpToolsData?.items])
  const executors = useMemo(() => executorsData?.items ?? [], [executorsData?.items])
  const brainSkillsError = !brainSkillsFetching && brainSkillsQueryError instanceof Error ? brainSkillsQueryError : null
  const mcpToolsError = !mcpToolsFetching && mcpToolsQueryError instanceof Error ? mcpToolsQueryError : null
  const executorsError = !executorsFetching && executorsQueryError instanceof Error ? executorsQueryError : null
  const canEditConfiguration = hasPermission("agents:reload")
  const brainSkillMap = useMemo(
    () => new Map(brainSkills.map((skill) => [skill.id, skill])),
    [brainSkills],
  )
  const mcpToolMap = useMemo(() => new Map(mcpTools.map((tool) => [tool.id, tool])), [mcpTools])

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

    return visibleAgents
      .filter((agent) => {
        if (activeFilter === "active" && !agent.enabled) return false
        if (activeFilter === "inactive" && agent.enabled) return false
        if (!keyword) return true

        return (
          agent.name.toLowerCase().includes(keyword) ||
          agent.description.toLowerCase().includes(keyword) ||
          String(agent.modelBinding?.model ?? "").toLowerCase().includes(keyword) ||
          resolveAgentBoundSkills(agent, brainSkillMap).some((skill) =>
            skill.name.toLowerCase().includes(keyword),
          ) ||
          resolveAgentBoundTools(agent, mcpToolMap).some((tool) =>
            tool.name.toLowerCase().includes(keyword),
          )
        )
      })
      .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"))
  }, [activeFilter, brainSkillMap, mcpToolMap, searchQuery, visibleAgents])

  const activeCount = visibleAgents.filter((item) => item.enabled).length
  const runningCount = visibleAgents.filter((item) => item.status === "running").length
  const onlineCount = visibleAgents.filter((item) => (item.runtimeStatus ?? "unknown") === "online").length

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

  useEffect(() => {
    if (!dialogOpen) return
    void refetchBrainSkills()
    void refetchMcpTools()
    void refetchExecutors()
  }, [dialogOpen, refetchBrainSkills, refetchExecutors, refetchMcpTools])

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

  const handleCreateExternalAgent = async (payload: ExternalAgentCreateRequest) => {
    try {
      const result = await registerExternalAgentMutation.mutateAsync(payload)
      await refetchAgents()
      const createdId = String(result.agent?.id ?? "").trim()
      const createdName = String(result.agent?.name ?? payload.name).trim()
      if (createdId) {
        setSelectedAgentId(createdId)
      }
      toast({
        title: "外部智能体已接入",
        description: createdName || payload.name,
      })
      setDialogOpen(false)
    } catch (saveError) {
      toast({
        title: "接入失败",
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

  const handleUpdateExternalAgent = async (payload: ExternalAgentCreateRequest) => {
    try {
      const result = await registerExternalAgentMutation.mutateAsync(payload)
      await refetchAgents()
      const updatedId = String(result.agent?.id ?? payload.id).trim()
      const updatedName = String(result.agent?.name ?? payload.name).trim()
      if (updatedId) {
        setSelectedAgentId(updatedId)
      }
      toast({
        title: "外部智能体配置已更新",
        description: updatedName || payload.name,
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
            <TabsTrigger value="all">全部 ({visibleAgents.length})</TabsTrigger>
            <TabsTrigger value="active">活跃 ({visibleAgents.filter((a) => a.enabled).length})</TabsTrigger>
            <TabsTrigger value="inactive">停用 ({visibleAgents.filter((a) => !a.enabled).length})</TabsTrigger>
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
              disabled={!canEditConfiguration}
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
                agents={visibleAgents.filter((item) => !isTaskChildAgent(item))}
                modelOptions={modelOptions}
                executors={executors}
                executorsLoading={executorsLoading || executorsFetching}
                executorsError={executorsError}
                onRetryExecutors={() => {
                  void refetchExecutors()
                }}
                brainSkills={brainSkills}
                brainSkillsLoading={brainSkillsLoading}
                brainSkillsError={brainSkillsError}
                mcpTools={mcpTools}
                mcpToolsLoading={mcpToolsLoading}
                mcpToolsError={mcpToolsError}
                canEdit={canEditConfiguration}
                isSaving={updateAgentConfigMutation.isPending || registerExternalAgentMutation.isPending}
                isTogglingEnabled={
                  togglingAgentId === selectedAgent.id && setAgentEnabledMutation.isPending
                }
                isDeleting={deletingAgentId === selectedAgent.id && deleteAgentMutation.isPending}
                onDelete={handleDelete}
                onToggleEnabled={handleToggleEnabled}
                onReload={handleReload}
                onSave={handleUpdateAgent}
                onSaveExternal={handleUpdateExternalAgent}
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
        agents={visibleAgents.filter((item) => !isTaskChildAgent(item))}
        executors={executors}
        executorsLoading={executorsLoading || executorsFetching}
        executorsError={executorsError}
        onRetryBrainSkills={() => {
          void refetchBrainSkills()
        }}
        onRetryMcpTools={() => {
          void refetchMcpTools()
        }}
        onRetryExecutors={() => {
          void refetchExecutors()
        }}
        modelOptions={modelOptions}
        brainSkills={brainSkills}
        brainSkillsLoading={brainSkillsLoading || brainSkillsFetching}
        brainSkillsError={brainSkillsError}
        mcpTools={mcpTools}
        mcpToolsLoading={mcpToolsLoading || mcpToolsFetching}
        mcpToolsError={mcpToolsError}
        canEdit={canEditConfiguration}
        isSavingLocal={createAgentMutation.isPending}
        isSavingExternal={registerExternalAgentMutation.isPending}
        onOpenChange={setDialogOpen}
        onSubmitLocal={handleCreateAgent}
        onSubmitExternal={handleCreateExternalAgent}
      />
    </div>
  )
}
