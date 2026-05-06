"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/shared/ui/breadcrumb"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/shared/ui/empty"
import { Progress } from "@/shared/ui/progress"
import { Separator } from "@/shared/ui/separator"
import { Skeleton } from "@/shared/ui/skeleton"
import { useCancelTask, useRetryTask, useTaskDetail, useTaskSteps } from "@/modules/dispatch/hooks/use-tasks"
import { buildAuthenticatedWebSocketUrl } from "@/platform/api/auth-storage"
import { WS_BASE_URL } from "@/platform/api/config"
import { toast } from "@/shared/hooks/use-toast"
import type {
  BrainDispatchSummary,
  ManagerPacket,
  Task as TaskPayload,
  TaskAgentGroup as TaskAgentGroupPayload,
  TaskAgentGroupMember as TaskAgentGroupMemberPayload,
  TaskAgentGroupTimelineEntry as TaskAgentGroupTimelineEntryPayload,
  TaskExecutionTraceEntry,
  TaskPriority,
  TaskRealtimeResponse,
  TaskRouteDecision,
  TaskStatus,
  TaskStep,
  TaskStepsResponse,
} from "@/shared/types"
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Clock3,
  FileSearch,
  FileText,
  Link2,
  PlayCircle,
  Sparkles,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react"
import { cn } from "@/shared/utils"

const statusConfig: Record<TaskStatus, { label: string; color: string }> = {
  pending: { label: "待处理", color: "bg-muted-foreground/20 text-muted-foreground" },
  running: { label: "运行中", color: "bg-primary/20 text-primary" },
  completed: { label: "已完成", color: "bg-success/20 text-success" },
  failed: { label: "失败", color: "bg-destructive/20 text-destructive" },
  cancelled: { label: "已取消", color: "bg-warning/20 text-warning-foreground" },
}

const priorityConfig: Record<TaskPriority, { label: string; color: string }> = {
  low: { label: "低", color: "bg-muted-foreground/20 text-muted-foreground" },
  medium: { label: "中", color: "bg-primary/20 text-primary" },
  high: { label: "高", color: "bg-destructive/20 text-destructive" },
}

const stepStatusConfig: Record<string, { label: string; color: string }> = {
  pending: { label: "待处理", color: "bg-muted-foreground/20 text-muted-foreground" },
  running: { label: "运行中", color: "bg-primary/20 text-primary" },
  completed: { label: "已完成", color: "bg-success/20 text-success" },
  failed: { label: "失败", color: "bg-destructive/20 text-destructive" },
  cancelled: { label: "已取消", color: "bg-warning/20 text-warning-foreground" },
}

const resultKindConfig: Record<string, { label: string; color: string }> = {
  search_report: { label: "检索结果", color: "bg-primary/15 text-primary" },
  draft_message: { label: "写作草稿", color: "bg-success/15 text-success" },
  help_note: { label: "帮助说明", color: "bg-warning/20 text-warning-foreground" },
}

const failureStageConfig: Record<string, string> = {
  route: "路由失败",
  dispatch: "调度失败",
  execution: "执行失败",
  outbound: "回传失败",
}

const deliveryStatusConfig: Record<string, string> = {
  sent: "已回传",
  failed: "回传失败",
  skipped: "未自动回传",
}

type LiveConnectionState = "connecting" | "connected" | "disconnected" | "error"

function liveConnectionMeta(state: LiveConnectionState) {
  if (state === "connected") {
    return {
      label: "实时同步已连接",
      tone: "bg-success/10 text-success",
      icon: <Wifi className="size-3.5" />,
    }
  }
  if (state === "connecting") {
    return {
      label: "实时同步连接中",
      tone: "bg-warning/10 text-warning-foreground",
      icon: <Wifi className="size-3.5" />,
    }
  }
  if (state === "error") {
    return {
      label: "实时同步异常",
      tone: "bg-destructive/10 text-destructive",
      icon: <WifiOff className="size-3.5" />,
    }
  }
  return {
    label: "实时同步未连接",
    tone: "bg-muted text-muted-foreground",
    icon: <WifiOff className="size-3.5" />,
  }
}

function getProgress(steps: TaskStep[], taskStatus?: TaskStatus) {
  if (steps.length === 0) {
    return taskStatus === "completed" ? 100 : taskStatus === "running" ? 60 : 0
  }

  const total = steps.reduce((acc, step) => {
    if (step.status === "completed") return acc + 1
    if (step.status === "running") return acc + 0.65
    if (step.status === "failed") return acc + 0.4
    return acc
  }, 0)

  return Math.round((total / steps.length) * 100)
}

function getRouteStrategyLabel(routeDecision?: TaskRouteDecision) {
  if (!routeDecision) {
    return null
  }
  return routeDecision.selectedByMessageTrigger ? "消息触发命中" : "意图兜底"
}

function getExecutionTraceStageLabel(stage: string, fallbackTitle: string) {
  const stageLabels: Record<string, string> = {
    request_analysis: "请求解析",
    knowledge_retrieval: "知识检索",
    context_memory_injection: "上下文与记忆注入",
    result_rendering: "结果渲染",
    execution_profile: "执行画像",
  }
  return stageLabels[stage] ?? fallbackTitle
}

function formatTraceMetadataLabel(key: string) {
  return key.replace(/_/g, " ")
}

function managerPacketEntries(managerPacket?: ManagerPacket | null) {
  if (!managerPacket) {
    return []
  }

  const labels: Array<[keyof ManagerPacket, string]> = [
    ["managerRole", "经理角色"],
    ["managerAction", "经理动作"],
    ["nextOwner", "下一归属"],
    ["interactionMode", "交互模式"],
    ["receptionMode", "接待模式"],
    ["taskShape", "任务形态"],
    ["decompositionHint", "拆解提示"],
    ["deliveryMode", "交付模式"],
    ["responseContract", "回复契约"],
  ]

  return labels
    .map(([key, label]) => ({ label, value: managerPacket[key] }))
    .filter((item) => item.value !== null && item.value !== undefined && `${item.value}`.trim() !== "")
}

function brainDispatchEntries(summary?: BrainDispatchSummary | null) {
  if (!summary) {
    return []
  }

  const labels: Array<[keyof BrainDispatchSummary, string]> = [
    ["dispatchType", "派发形态"],
    ["interactionMode", "交互模式"],
    ["receptionMode", "接待模式"],
    ["executionAgent", "执行代理"],
    ["managerAction", "经理动作"],
    ["nextOwner", "下一归属"],
    ["deliveryMode", "交付模式"],
    ["responseContract", "回复契约"],
    ["executionScope", "执行范围"],
  ]

  return labels
    .map(([key, label]) => ({ label, value: summary[key] }))
    .filter((item) => item.value !== null && item.value !== undefined && `${item.value}`.trim() !== "")
}

function visibleStepMetadata(metadata?: Record<string, string | number | boolean | null>) {
  if (!metadata) {
    return []
  }

  return Object.entries(metadata).filter(([, value]) => value !== null && `${value}`.trim() !== "")
}

function readableExecutionTrace(traceItems?: TaskExecutionTraceEntry[]) {
  return traceItems ?? []
}

function getFailureStageLabel(value?: string) {
  if (!value) return "--"
  return failureStageConfig[value] ?? value
}

function getDeliveryStatusLabel(value?: string) {
  if (!value) return "--"
  return deliveryStatusConfig[value] ?? value
}

function isActiveTaskStatus(value?: TaskStatus) {
  return value === "pending" || value === "running"
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

type TaskAgentMemberView = {
  id: string
  name: string
  role: string
  branchId: string
  type: string
  status: string
  enabled: boolean | null
  providerKey: string
  providerLabel: string
  model: string
  boundSkillIds: string[]
  boundToolIds: string[]
  requestedSkillIds: string[]
  requestedToolIds: string[]
  natsSubject: string
  soul: string
  runtimeStatus: string
  currentStepId: string
  currentStepTitle: string
  currentStepMessage: string
  currentStepStartedAt: string
  currentStepFinishedAt: string
  selectedForDelivery: boolean | null
}

type TaskAgentGroupView = {
  source: "projection" | "fallback"
  groupId: string
  groupName: string
  status: string
  topology: string
  coordinationMode: string
  dispatcherAgentId: string
  members: TaskAgentMemberView[]
  acceptanceAgent: TaskAgentMemberView | null
  requestedSkillIds: string[]
  requestedToolIds: string[]
  appliedSkillIds: string[]
  appliedToolIds: string[]
  natsSubjects: Array<{ key: string; value: string }>
  timeline: TaskAgentTimelineView[]
  warnings: string[]
}

type TaskAgentTimelineView = {
  id: string
  kind: string
  title: string
  detail: string
  timestamp: string
  actorAgentId: string
  actorAgentName: string
  metadata: Array<{ key: string; value: string }>
}

function normalizeIdentifierList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  return Array.from(
    new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean)),
  )
}

function textValue(value: unknown) {
  return String(value ?? "").trim()
}

function stringifyValue(value: unknown) {
  if (value === null || value === undefined) {
    return ""
  }
  if (typeof value === "string") {
    return value.trim()
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return ""
  }
}

function previewSoul(value: string, limit = 220) {
  if (value.length <= limit) {
    return value
  }
  return `${value.slice(0, limit).trimEnd()}...`
}

function roleLabel(value: string) {
  const labels: Record<string, string> = {
    frontend: "前端",
    backend: "后端",
    fullstack: "全栈",
    integration: "联调",
    acceptance: "验收",
    development: "开发",
  }
  return labels[value] || value || "未标注角色"
}

function agentStatusLabel(value: string) {
  const labels: Record<string, string> = {
    idle: "空闲",
    running: "运行中",
    disabled: "停用",
    failed: "异常",
    provisioned: "已编组",
    draft: "草稿",
  }
  return labels[value] || value || "状态未知"
}

function memberRuntimeStatusLabel(value: string) {
  const labels: Record<string, string> = {
    pending: "待启动",
    running: "执行中",
    completed: "已完成",
    failed: "执行失败",
    cancelled: "已取消",
    queued: "排队中",
  }
  return labels[value] || value || "运行状态未知"
}

function acceptanceOutcome(taskStatus: TaskStatus, deliveryStatus?: string, runtimeStatus?: string) {
  if (runtimeStatus === "failed") {
    return "未通过"
  }
  if (runtimeStatus === "completed" && deliveryStatus === "sent") {
    return "通过并已回传"
  }
  if (runtimeStatus === "completed" && deliveryStatus === "failed") {
    return "通过但回传失败"
  }
  if (runtimeStatus === "completed" && taskStatus === "completed") {
    return "已通过"
  }
  if (runtimeStatus === "running") {
    return "验收中"
  }
  if (runtimeStatus === "pending") {
    return "待验收"
  }
  if (taskStatus === "failed") {
    return "待人工确认"
  }
  return "待验收"
}

function natsSubjectEntries(value: Record<string, unknown> | null | undefined) {
  if (!isRecord(value)) {
    return []
  }

  return Object.entries(value)
    .map(([key, item]) => ({
      key,
      value: stringifyValue(item),
    }))
    .filter((item) => item.value !== "")
}

function timelineMetadataEntries(value: Record<string, unknown> | null | undefined) {
  if (!isRecord(value)) {
    return []
  }

  return Object.entries(value)
    .map(([key, item]) => ({
      key,
      value: stringifyValue(item),
    }))
    .filter((item) => item.value !== "")
}

function normalizeTaskAgentTimelineEntry(
  entry?: TaskAgentGroupTimelineEntryPayload | null,
  fallback?: Partial<TaskAgentTimelineView>,
): TaskAgentTimelineView | null {
  const normalized: TaskAgentTimelineView = {
    id: textValue(entry?.id ?? fallback?.id),
    kind: textValue(entry?.kind ?? fallback?.kind),
    title: textValue(entry?.title ?? fallback?.title),
    detail: textValue(entry?.detail ?? fallback?.detail),
    timestamp: textValue(entry?.timestamp ?? fallback?.timestamp),
    actorAgentId: textValue(entry?.actorAgentId ?? fallback?.actorAgentId),
    actorAgentName: textValue(entry?.actorAgentName ?? fallback?.actorAgentName),
    metadata:
      entry?.metadata && isRecord(entry.metadata)
        ? timelineMetadataEntries(entry.metadata)
        : fallback?.metadata ?? [],
  }

  if (!normalized.title && !normalized.detail && !normalized.timestamp) {
    return null
  }

  return normalized
}

function normalizeTaskAgentMember(
  member?: TaskAgentGroupMemberPayload | null,
  fallback?: Partial<TaskAgentMemberView>,
): TaskAgentMemberView | null {
  const normalized: TaskAgentMemberView = {
    id: textValue(member?.id ?? fallback?.id),
    name: textValue(member?.name ?? fallback?.name),
    role: textValue(member?.role ?? fallback?.role),
    branchId: textValue(member?.branchId ?? fallback?.branchId),
    type: textValue(member?.type ?? fallback?.type),
    status: textValue(member?.status ?? fallback?.status),
    enabled: member?.enabled ?? fallback?.enabled ?? null,
    providerKey: textValue(member?.providerKey ?? fallback?.providerKey),
    providerLabel: textValue(member?.providerLabel ?? fallback?.providerLabel),
    model: textValue(member?.model ?? fallback?.model),
    boundSkillIds: normalizeIdentifierList(member?.boundSkillIds ?? fallback?.boundSkillIds),
    boundToolIds: normalizeIdentifierList(member?.boundToolIds ?? fallback?.boundToolIds),
    requestedSkillIds: normalizeIdentifierList(
      member?.requestedSkillIds ?? fallback?.requestedSkillIds,
    ),
    requestedToolIds: normalizeIdentifierList(
      member?.requestedToolIds ?? fallback?.requestedToolIds,
    ),
    natsSubject: textValue(member?.natsSubject ?? fallback?.natsSubject),
    soul: textValue(member?.soul ?? fallback?.soul),
    runtimeStatus: textValue(member?.runtimeStatus ?? fallback?.runtimeStatus),
    currentStepId: textValue(member?.currentStepId ?? fallback?.currentStepId),
    currentStepTitle: textValue(member?.currentStepTitle ?? fallback?.currentStepTitle),
    currentStepMessage: textValue(member?.currentStepMessage ?? fallback?.currentStepMessage),
    currentStepStartedAt: textValue(member?.currentStepStartedAt ?? fallback?.currentStepStartedAt),
    currentStepFinishedAt: textValue(member?.currentStepFinishedAt ?? fallback?.currentStepFinishedAt),
    selectedForDelivery: member?.selectedForDelivery ?? fallback?.selectedForDelivery ?? null,
  }

  if (
    !normalized.id &&
    !normalized.name &&
    !normalized.role &&
    !normalized.branchId &&
    !normalized.model &&
    normalized.boundSkillIds.length === 0 &&
    normalized.boundToolIds.length === 0 &&
    normalized.requestedSkillIds.length === 0 &&
    normalized.requestedToolIds.length === 0 &&
    !normalized.natsSubject &&
    !normalized.soul &&
    !normalized.runtimeStatus &&
    !normalized.currentStepTitle &&
    !normalized.currentStepMessage
  ) {
    return null
  }

  return normalized
}

function resolveProjectedTaskAgentGroup(taskAgentGroup?: TaskAgentGroupPayload | null): TaskAgentGroupView | null {
  if (!taskAgentGroup) {
    return null
  }

  const members = (taskAgentGroup.developmentAgents ?? [])
    .map((member) => normalizeTaskAgentMember(member))
    .filter((member): member is TaskAgentMemberView => Boolean(member))

  const acceptanceAgent = normalizeTaskAgentMember(taskAgentGroup.acceptanceAgent, {
    role: "acceptance",
  })

  const projected: TaskAgentGroupView = {
    source: "projection",
    groupId: textValue(taskAgentGroup.id),
    groupName: textValue(taskAgentGroup.name),
    status: textValue(taskAgentGroup.status),
    topology: textValue(taskAgentGroup.topology),
    coordinationMode: textValue(taskAgentGroup.coordinationMode),
    dispatcherAgentId: textValue(taskAgentGroup.dispatcherAgentId),
    members,
    acceptanceAgent,
    requestedSkillIds: normalizeIdentifierList(taskAgentGroup.requestedSkillIds),
    requestedToolIds: normalizeIdentifierList(taskAgentGroup.requestedToolIds),
    appliedSkillIds: normalizeIdentifierList(taskAgentGroup.appliedSkillIds),
    appliedToolIds: normalizeIdentifierList(taskAgentGroup.appliedToolIds),
    natsSubjects: natsSubjectEntries(taskAgentGroup.natsSubjects),
    timeline: (taskAgentGroup.timeline ?? [])
      .map((entry) => normalizeTaskAgentTimelineEntry(entry))
      .filter((entry): entry is TaskAgentTimelineView => Boolean(entry)),
    warnings: normalizeIdentifierList(taskAgentGroup.warnings),
  }

  if (
    !projected.groupId &&
    !projected.groupName &&
    !projected.status &&
    !projected.topology &&
    !projected.coordinationMode &&
    !projected.dispatcherAgentId &&
    projected.members.length === 0 &&
    !projected.acceptanceAgent &&
    projected.requestedSkillIds.length === 0 &&
    projected.requestedToolIds.length === 0 &&
    projected.appliedSkillIds.length === 0 &&
    projected.appliedToolIds.length === 0 &&
    projected.natsSubjects.length === 0 &&
    projected.timeline.length === 0 &&
    projected.warnings.length === 0
  ) {
    return null
  }

  return projected
}

function resolveFallbackTaskAgentGroup(routeDecision?: TaskRouteDecision): TaskAgentGroupView | null {
  if (!routeDecision || !isRecord(routeDecision.executionPlan)) {
    return null
  }

  const executionPlan = routeDecision.executionPlan
  const metadata = isRecord(executionPlan.metadata) ? executionPlan.metadata : null
  const fanIn = isRecord(executionPlan.fanIn)
    ? executionPlan.fanIn
    : isRecord(executionPlan.fan_in)
      ? executionPlan.fan_in
      : null
  const steps = Array.isArray(executionPlan.steps) ? executionPlan.steps : []
  const members = steps
    .map((step) => {
      if (!isRecord(step)) return null
      return normalizeTaskAgentMember(undefined, {
        role: textValue(step.role) || "development",
        id: textValue(step.executionAgentId ?? step.execution_agent_id),
        name:
          textValue(step.executionAgent ?? step.execution_agent) ||
          textValue(step.executionAgentId ?? step.execution_agent_id) ||
          "未命名成员",
        branchId: textValue(step.branchId ?? step.branch_id),
      })
    })
    .filter((item): item is TaskAgentMemberView => Boolean(item))

  const warnings = Array.isArray(metadata?.warnings)
    ? metadata.warnings.map((item) => String(item ?? "").trim()).filter(Boolean)
    : []

  const groupId = String(metadata?.groupId ?? metadata?.group_id ?? "").trim()
  const groupName = String(metadata?.groupName ?? metadata?.group_name ?? "").trim()
  const acceptanceAgentId = String(
    metadata?.acceptanceAgentId ?? metadata?.acceptance_agent_id ?? fanIn?.aggregatorId ?? fanIn?.aggregator_id ?? "",
  ).trim()
  const acceptanceAgentName = String(
    metadata?.acceptanceAgentName ?? metadata?.acceptance_agent_name ?? fanIn?.aggregator ?? "",
  ).trim()
  const topology = String(routeDecision.executionScope ?? executionPlan.planType ?? executionPlan.plan_type ?? "").trim()
  const coordinationMode = String(
    executionPlan.coordinationMode ?? executionPlan.coordination_mode ?? "",
  ).trim()

  if (!groupId && !groupName && members.length === 0 && !acceptanceAgentId && !acceptanceAgentName) {
    return null
  }

  const timeline: TaskAgentTimelineView[] = [
    {
      id: `${groupId || "task-group"}:fallback-created`,
      kind: "group_created",
      title: "识别到开发组",
      detail: `${groupName || groupId || "当前任务开发组"} 已出现在执行计划中。`,
      timestamp: "",
      actorAgentId: "",
      actorAgentName: "",
      metadata: [],
    },
    ...members.map((member, index) => ({
      id: `${groupId || "task-group"}:fallback-member:${member.id || index + 1}`,
      kind: "development_agent_provisioned",
      title: "识别到开发成员",
      detail: `${member.name || member.id || "开发 Agent"} 承担 ${roleLabel(member.role)} 角色。`,
      timestamp: "",
      actorAgentId: member.id,
      actorAgentName: member.name,
      metadata: member.branchId
        ? [
            {
              key: "branch",
              value: member.branchId,
            },
          ]
        : [],
    })),
  ]
  if (acceptanceAgentId || acceptanceAgentName) {
    timeline.push({
      id: `${groupId || "task-group"}:fallback-acceptance`,
      kind: "acceptance_agent_provisioned",
      title: "识别到验收成员",
      detail: `${acceptanceAgentName || acceptanceAgentId} 承担最终验收。`,
      timestamp: "",
      actorAgentId: acceptanceAgentId,
      actorAgentName: acceptanceAgentName,
      metadata: [],
    })
  }

  return {
    source: "fallback",
    groupId,
    groupName,
    status: "",
    topology,
    coordinationMode,
    dispatcherAgentId: "",
    members,
    acceptanceAgent:
      acceptanceAgentId || acceptanceAgentName
        ? {
            id: acceptanceAgentId,
            name: acceptanceAgentName || acceptanceAgentId,
            role: "acceptance",
            branchId: "",
            type: "",
            status: "",
            enabled: null,
            providerKey: "",
            providerLabel: "",
            model: "",
            boundSkillIds: [],
            boundToolIds: [],
            requestedSkillIds: [],
            requestedToolIds: [],
            natsSubject: "",
            soul: "",
            runtimeStatus: "",
            currentStepId: "",
            currentStepTitle: "",
            currentStepMessage: "",
            currentStepStartedAt: "",
            currentStepFinishedAt: "",
            selectedForDelivery: null,
          }
        : null,
    requestedSkillIds: [],
    requestedToolIds: [],
    appliedSkillIds: [],
    appliedToolIds: [],
    natsSubjects: [],
    timeline,
    warnings,
  }
}

function resolveTaskAgentGroup(
  taskAgentGroup?: TaskAgentGroupPayload | null,
  routeDecision?: TaskRouteDecision,
): TaskAgentGroupView | null {
  return resolveProjectedTaskAgentGroup(taskAgentGroup) ?? resolveFallbackTaskAgentGroup(routeDecision)
}

function CapabilityBadges({
  items,
  emptyText,
  emphasis = false,
}: {
  items: string[]
  emptyText: string
  emphasis?: boolean
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-lg bg-secondary/35 px-3 py-2 text-xs leading-5 text-muted-foreground">
        {emptyText}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <Badge
          key={item}
          variant={emphasis ? "secondary" : "outline"}
          className={emphasis ? "bg-primary/10 text-primary" : "border-border text-muted-foreground"}
        >
          {item}
        </Badge>
      ))}
    </div>
  )
}

function TaskAgentMemberCard({
  member,
  title,
}: {
  member: TaskAgentMemberView
  title: string
}) {
  const capabilityRows = [
    {
      label: "请求技能",
      items: member.requestedSkillIds,
      emptyText: "没有声明额外请求技能",
    },
    {
      label: "实际绑定技能",
      items: member.boundSkillIds,
      emptyText: "当前未绑定技能",
      emphasis: true,
    },
    {
      label: "请求工具",
      items: member.requestedToolIds,
      emptyText: "没有声明额外请求工具",
    },
    {
      label: "实际绑定工具",
      items: member.boundToolIds,
      emptyText: "当前未绑定工具",
      emphasis: true,
    },
  ]

  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-3">
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{title}</div>
            <div className="mt-1 font-medium text-foreground">{member.name || member.id || "未命名成员"}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className="bg-primary/10 text-primary">
              {roleLabel(member.role)}
            </Badge>
            <Badge
              variant="secondary"
              className={cn(
                "text-foreground",
                member.runtimeStatus === "completed" && "bg-success/15 text-success",
                member.runtimeStatus === "running" && "bg-primary/15 text-primary",
                member.runtimeStatus === "failed" && "bg-destructive/10 text-destructive",
                member.runtimeStatus === "cancelled" && "bg-warning/15 text-warning-foreground",
                member.runtimeStatus === "pending" && "bg-muted text-muted-foreground",
                !member.runtimeStatus && "bg-muted text-muted-foreground",
              )}
            >
              {memberRuntimeStatusLabel(member.runtimeStatus)}
            </Badge>
            {member.status ? <Badge variant="outline">资源状态: {agentStatusLabel(member.status)}</Badge> : null}
            <Badge
              variant="outline"
              className={member.enabled === false ? "border-warning/40 text-warning-foreground" : undefined}
            >
              {member.enabled === null ? "启用状态未知" : member.enabled ? "已启用" : "未启用"}
            </Badge>
            {member.selectedForDelivery ? (
              <Badge variant="secondary" className="bg-warning/15 text-warning-foreground">
                已选中汇总
              </Badge>
            ) : null}
            {member.model ? (
              <Badge variant="secondary" className="bg-success/10 text-success">
                {member.model}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {member.id ? (
            <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
              Agent ID: {member.id}
            </Badge>
          ) : null}
          {member.branchId ? (
            <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
              Branch: {member.branchId}
            </Badge>
          ) : null}
          {member.type ? (
            <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
              类型: {member.type}
            </Badge>
          ) : null}
          {member.providerLabel || member.providerKey ? (
            <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
              提供方: {member.providerLabel || member.providerKey}
            </Badge>
          ) : null}
          {member.natsSubject ? (
            <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
              NATS: {member.natsSubject}
            </Badge>
          ) : null}
        </div>

        {member.currentStepTitle || member.currentStepMessage ? (
          <div className="rounded-lg bg-background p-3">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="text-xs text-muted-foreground">当前步骤</div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {member.currentStepTitle || "执行中"}
                </div>
                {member.currentStepMessage ? (
                  <div className="mt-1 text-xs leading-5 text-muted-foreground">
                    {member.currentStepMessage}
                  </div>
                ) : null}
              </div>
              <div className="text-xs text-muted-foreground">
                {member.currentStepStartedAt ? <div>开始: {member.currentStepStartedAt}</div> : null}
                {member.currentStepFinishedAt ? <div className="mt-1">结束: {member.currentStepFinishedAt}</div> : null}
                {member.currentStepId ? <div className="mt-1">Step ID: {member.currentStepId}</div> : null}
              </div>
            </div>
          </div>
        ) : null}

        {capabilityRows.map((row) => (
          <div key={`${member.id}-${row.label}`} className="space-y-2">
            <div className="text-xs text-muted-foreground">{row.label}</div>
            <CapabilityBadges items={row.items} emptyText={row.emptyText} emphasis={row.emphasis} />
          </div>
        ))}

        {member.soul ? (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">soul 预览</div>
            <div className="rounded-lg bg-background p-3 font-mono text-[11px] leading-5 text-muted-foreground">
              <div className="whitespace-pre-wrap break-words">{previewSoul(member.soul)}</div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function TaskAgentTimelineCard({ entry }: { entry: TaskAgentTimelineView }) {
  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-3">
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="font-medium text-foreground">{entry.title}</div>
            {entry.detail ? (
              <div className="mt-1 text-xs leading-5 text-muted-foreground">{entry.detail}</div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {entry.kind ? <Badge variant="outline">{entry.kind}</Badge> : null}
            {entry.timestamp ? (
              <Badge variant="secondary" className="bg-primary/10 text-primary">
                {entry.timestamp}
              </Badge>
            ) : null}
          </div>
        </div>

        {entry.actorAgentName || entry.actorAgentId ? (
          <div className="flex flex-wrap gap-2">
            {entry.actorAgentName ? (
              <Badge variant="secondary" className="bg-success/10 text-success">
                {entry.actorAgentName}
              </Badge>
            ) : null}
            {entry.actorAgentId ? (
              <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                Agent ID: {entry.actorAgentId}
              </Badge>
            ) : null}
          </div>
        ) : null}

        {entry.metadata.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {entry.metadata.slice(0, 6).map((item) => (
              <Badge
                key={`${entry.id}-${item.key}`}
                variant="outline"
                className="border-border text-[11px] text-muted-foreground"
              >
                {formatTraceMetadataLabel(item.key)}: {item.value}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function LoadingView() {
  return (
    <div className="space-y-6 p-6">
      <Skeleton className="h-5 w-64" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-32 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Skeleton className="h-[480px] rounded-xl" />
        <Skeleton className="h-[480px] rounded-xl" />
      </div>
    </div>
  )
}

export default function TaskDetailPage() {
  const params = useParams<{ taskId: string }>()
  const taskId = params.taskId
  const [liveTask, setLiveTask] = useState<TaskPayload | null>(null)
  const [liveSteps, setLiveSteps] = useState<TaskStepsResponse | null>(null)
  const [liveState, setLiveState] = useState<LiveConnectionState>("connecting")
  const pollingFallbackEnabled = liveState !== "connected"
  const taskQuery = useTaskDetail(taskId, { live: pollingFallbackEnabled })
  const task = liveTask ?? taskQuery.data
  const stepsQuery = useTaskSteps(taskId, {
    live: pollingFallbackEnabled,
    taskStatus: task?.status,
  })
  const stepsData = liveSteps ?? stepsQuery.data
  const { isLoading, error } = taskQuery
  const { isLoading: stepsLoading } = stepsQuery
  const cancelTaskMutation = useCancelTask()
  const retryTaskMutation = useRetryTask()
  const steps = stepsData?.items ?? []
  const brainDispatchEntriesList = brainDispatchEntries(task?.brainDispatchSummary)
  const taskAgentGroup = resolveTaskAgentGroup(task?.taskAgentGroup, task?.routeDecision)
  const liveMeta = liveConnectionMeta(liveState)
  const showLiveBadge = Boolean(task) && (isActiveTaskStatus(task?.status) || liveState !== "disconnected")

  useEffect(() => {
    setLiveTask(null)
    setLiveSteps(null)
    setLiveState("connecting")
  }, [taskId])

  useEffect(() => {
    if (!taskId) {
      setLiveState("error")
      return
    }

    let cancelled = false
    let socket: WebSocket | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const wsUrl = buildAuthenticatedWebSocketUrl(
        `/api/tasks/${encodeURIComponent(taskId)}/realtime`,
        WS_BASE_URL,
      )
      if (!wsUrl) {
        setLiveState("error")
        return
      }

      setLiveState("connecting")
      socket = new WebSocket(wsUrl)

      socket.onopen = () => {
        if (!cancelled) {
          setLiveState("connected")
        }
      }

      socket.onmessage = (event) => {
        if (cancelled) return
        try {
          const payload = JSON.parse(event.data) as TaskRealtimeResponse
          if (payload.task) {
            setLiveTask(payload.task)
          }
          if (payload.steps) {
            setLiveSteps(payload.steps)
          }
          if (payload.messageType === "snapshot" || payload.messageType === "keepalive") {
            setLiveState("connected")
          }
        } catch {
          setLiveState("error")
        }
      }

      socket.onerror = () => {
        if (!cancelled) {
          setLiveState("error")
        }
      }

      socket.onclose = () => {
        if (cancelled) return
        setLiveState("disconnected")
        retryTimer = setTimeout(() => {
          connect()
        }, 3000)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimer) {
        clearTimeout(retryTimer)
      }
      if (socket) {
        socket.close()
      }
    }
  }, [taskId])

  if (isLoading && !task) {
    return <LoadingView />
  }

  if (error || !task) {
    return (
      <div className="p-6">
        <Card className="bg-card">
          <CardContent className="p-8">
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <XCircle className="size-5" />
                </EmptyMedia>
                <EmptyTitle>任务不存在或暂时不可用</EmptyTitle>
                <EmptyDescription>
                  {error instanceof Error ? error.message : "没有找到对应的任务详情。"}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button asChild>
                  <Link href="/tasks">
                    <ArrowLeft className="mr-2 size-4" />
                    返回任务列表
                  </Link>
                </Button>
              </EmptyContent>
            </Empty>
          </CardContent>
        </Card>
      </div>
    )
  }

  const status = statusConfig[task.status]
  const priority = priorityConfig[task.priority]
  const progress = getProgress(steps, task.status)
  const liveRefreshing = isActiveTaskStatus(task.status)
  const canCancel = task.status === "pending" || task.status === "running"
  const canRetry = task.status !== "running"
  const taskResult = task.result
  const executionTrace = readableExecutionTrace(taskResult?.executionTrace)
  const managerEntries = managerPacketEntries(task.managerPacket)
  const resultKind = task.result
    ? resultKindConfig[task.result.kind] ?? {
        label: task.result.kind,
        color: "bg-muted text-muted-foreground",
      }
    : null

  const handleCancel = async () => {
    try {
      const result = await cancelTaskMutation.mutateAsync(task.id)
      toast({
        title: "任务已取消",
        description: result.message,
      })
    } catch (mutationError) {
      toast({
        title: "取消任务失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleRetry = async () => {
    try {
      const result = await retryTaskMutation.mutateAsync(task.id)
      toast({
        title: "任务已重新执行",
        description: result.message,
      })
    } catch (mutationError) {
      toast({
        title: "重新执行失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="space-y-4">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link href="/tasks">任务中心</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{task.title}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold text-foreground">{task.title}</h1>
              <Badge variant="secondary" className={status.color}>
                {status.label}
              </Badge>
              {showLiveBadge ? (
                <Badge variant="secondary" className={liveMeta.tone}>
                  <span className="mr-1">{liveMeta.icon}</span>
                  {liveMeta.label}
                </Badge>
              ) : null}
              <Badge variant="secondary" className={priority.color}>
                优先级: {priority.label}
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              {task.description}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => void handleRetry()} disabled={!canRetry}>
              <PlayCircle className="mr-2 size-4" />
              重新执行
            </Button>
            <Button variant="destructive" onClick={() => void handleCancel()} disabled={!canCancel}>
              取消任务
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">执行进度</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{progress}%</div>
            <Progress value={progress} className="mt-3 h-2" />
            <div className="mt-3 text-xs text-muted-foreground">
              {steps.length > 0 ? `${steps.length} 个步骤参与执行` : "当前任务尚无步骤明细"}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">主处理 Agent</div>
            <div className="mt-2 flex items-center gap-2 text-lg font-semibold text-foreground">
              <Bot className="size-5 text-primary" />
              {task.agent}
            </div>
            <div className="mt-3 text-xs text-muted-foreground">创建于 {task.createdAt}</div>
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">Token 消耗</div>
            <div className="mt-2 flex items-center gap-2 text-2xl font-semibold text-foreground">
              <Sparkles className="size-5 text-primary" />
              {task.tokens.toLocaleString()}
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              {task.completedAt ? `完成于 ${task.completedAt}` : "任务仍在执行或排队"}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">总耗时</div>
            <div className="mt-2 flex items-center gap-2 text-2xl font-semibold text-foreground">
              <Clock3 className="size-5 text-primary" />
              {task.duration || "--"}
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              {canCancel ? "仍可取消当前任务" : "当前状态下无需取消"}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-lg">执行结果</CardTitle>
                {resultKind ? (
                  <Badge variant="secondary" className={resultKind.color}>
                    {resultKind.label}
                  </Badge>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {taskResult ? (
                <div className="space-y-4">
                  <div className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="flex items-start gap-3">
                      {taskResult.kind === "search_report" ? (
                        <FileSearch className="mt-0.5 size-5 text-primary" />
                      ) : (
                        <FileText className="mt-0.5 size-5 text-primary" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-foreground">{taskResult.title}</div>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">
                          {taskResult.summary}
                        </p>
                      </div>
                    </div>
                  </div>

                  {taskResult.bullets.length > 0 ? (
                    <div className="space-y-2">
                      {taskResult.bullets.map((bullet, index) => (
                        <div
                          key={`${taskResult.kind}-bullet-${index}`}
                          className="rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted-foreground"
                        >
                          {bullet}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  <div className="rounded-xl border border-border bg-background p-4">
                    <div className="mb-3 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                      输出正文
                    </div>
                    <div className="whitespace-pre-wrap text-sm leading-7 text-foreground">
                      {taskResult.content}
                    </div>
                  </div>

                  {executionTrace.length > 0 ? (
                    <div className="rounded-xl border border-border bg-background p-4">
                      <div className="mb-3 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                        执行轨迹
                      </div>
                      <div className="space-y-3">
                        {executionTrace.map((trace, index) => {
                          const traceStatus = stepStatusConfig[trace.status] ?? {
                            label: trace.status,
                            color: "bg-muted text-muted-foreground",
                          }
                          const metadataEntries = Object.entries(trace.metadata ?? {}).filter(
                            ([, value]) => value !== null && `${value}`.trim() !== "",
                          )
                          return (
                            <div key={`${trace.stage}-${index}`} className="rounded-lg border border-border bg-card p-3">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-sm font-medium text-foreground">
                                  {getExecutionTraceStageLabel(trace.stage, trace.title)}
                                </div>
                                <Badge variant="secondary" className={traceStatus.color}>
                                  {traceStatus.label}
                                </Badge>
                              </div>
                              {trace.detail ? (
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">{trace.detail}</p>
                              ) : null}
                              {metadataEntries.length > 0 ? (
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {metadataEntries.slice(0, 4).map(([key, value]) => (
                                    <Badge
                                      key={`${trace.stage}-${key}`}
                                      variant="outline"
                                      className="border-border text-[11px] text-muted-foreground"
                                    >
                                      {formatTraceMetadataLabel(key)}: {String(value)}
                                    </Badge>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ) : null}

                  {taskResult.references.length > 0 ? (
                    <div className="rounded-xl border border-border bg-secondary/15 p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
                        <Link2 className="size-4 text-primary" />
                        参考线索
                      </div>
                      <div className="space-y-3">
                        {taskResult.references.map((reference, index) => (
                          <div key={`${reference.title}-${index}`} className="rounded-lg bg-background p-3">
                            <div className="text-sm font-medium text-foreground">{reference.title}</div>
                            {reference.detail ? (
                              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                {reference.detail}
                              </p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <Empty className="border-border py-10">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileText className="size-5" />
                    </EmptyMedia>
                    <EmptyTitle>结果产物尚未生成</EmptyTitle>
                    <EmptyDescription>
                      {task.status === "completed"
                        ? "当前任务已经结束，但还没有沉淀出结构化输出。"
                        : "结果会在输出节点完成后显示在这里。"}
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">执行步骤</CardTitle>
                <span className="text-xs text-muted-foreground">
                  {liveState === "connected"
                    ? "实时同步中"
                    : stepsLoading
                      ? "同步中..."
                      : `${steps.length} steps`}
                </span>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {steps.length === 0 ? (
                <Empty className="border-border py-12">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <Clock3 className="size-5" />
                    </EmptyMedia>
                    <EmptyTitle>暂无步骤明细</EmptyTitle>
                    <EmptyDescription>
                      这个任务还没有产生可展示的执行步骤，通常出现在排队中的任务。
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : (
                <div className="space-y-4">
                  {steps.map((step, index) => {
                    const stepStatus = stepStatusConfig[step.status] ?? {
                      label: step.status,
                      color: "bg-muted text-muted-foreground",
                    }

                    return (
                      <div key={step.id} className="relative rounded-xl border border-border bg-secondary/20 p-4">
                        {index !== steps.length - 1 ? (
                          <div className="absolute left-7 top-14 h-[calc(100%-2rem)] w-px bg-border" />
                        ) : null}
                        <div className="flex items-start gap-3">
                          <div
                            className={cn(
                              "mt-0.5 flex size-6 items-center justify-center rounded-full border-4 border-background",
                              step.status === "completed" && "bg-success",
                              step.status === "running" && "bg-primary",
                              step.status === "failed" && "bg-destructive",
                              step.status !== "completed" &&
                                step.status !== "running" &&
                                step.status !== "failed" &&
                                "bg-muted-foreground",
                            )}
                          />
                          <div className="flex-1">
                            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                              <div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <h3 className="font-medium text-foreground">{step.title}</h3>
                                  <Badge variant="secondary" className={stepStatus.color}>
                                    {stepStatus.label}
                                  </Badge>
                                </div>
                                <p className="mt-2 text-sm text-muted-foreground">
                                  {step.message || "暂无额外说明"}
                                </p>
                              </div>
                              <div className="text-xs text-muted-foreground">
                                <div>{step.startedAt ? `开始: ${step.startedAt}` : "开始时间待定"}</div>
                                <div className="mt-1">
                                  {step.finishedAt ? `结束: ${step.finishedAt}` : "尚未结束"}
                                </div>
                              </div>
                            </div>
                            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <Badge variant="outline" className="border-border">
                                {step.agent}
                              </Badge>
                              {step.tokens ? (
                                <Badge variant="secondary" className="bg-primary/10 text-primary">
                                  {step.tokens} tokens
                                </Badge>
                              ) : null}
                              {visibleStepMetadata(step.metadata)
                                .slice(0, 4)
                                .map(([key, value]) => (
                                  <Badge
                                    key={`${step.id}-${key}`}
                                    variant="outline"
                                    className="border-border text-[11px] text-muted-foreground"
                                  >
                                    {formatTraceMetadataLabel(key)}: {String(value)}
                                  </Badge>
                                ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">任务摘要</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">任务 ID</span>
                <span className="font-medium text-foreground">{task.id}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">状态</span>
                <span className="font-medium text-foreground">{status.label}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">当前阶段</span>
                <span className="font-medium text-foreground">{task.currentStage || "--"}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">失败归因</span>
                <span className="font-medium text-foreground">
                  {getFailureStageLabel(task.failureStage)}
                </span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">回传状态</span>
                <span className="font-medium text-foreground">
                  {getDeliveryStatusLabel(task.deliveryStatus)}
                </span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">完成时间</span>
                <span className="font-medium text-foreground">{task.completedAt || "--"}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">执行步数</span>
                <span className="font-medium text-foreground">{steps.length}</span>
              </div>
              {task.failureMessage ? (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <div className="text-muted-foreground">失败说明</div>
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                      {task.failureMessage}
                    </div>
                  </div>
                </>
              ) : null}
              {task.deliveryMessage ? (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <div className="text-muted-foreground">回传说明</div>
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                      {task.deliveryMessage}
                    </div>
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>

          {task.routeDecision ? (
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">路由决策</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">命中路由</span>
                  <span className="font-medium text-foreground">
                    {task.routeDecision.executionAgent || task.routeDecision.workflowName || "--"}
                  </span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">执行代理</span>
                  <span className="font-medium text-foreground">{task.routeDecision.executionAgent}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">路由策略</span>
                  <Badge variant="secondary" className="bg-primary/10 text-primary">
                    {getRouteStrategyLabel(task.routeDecision)}
                  </Badge>
                </div>
                <Separator />
                <div className="space-y-2">
                  <div className="text-muted-foreground">路由说明</div>
                  <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                    {task.routeDecision.routeMessage}
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {task.brainDispatchSummary ? (
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">主脑分发摘要</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {brainDispatchEntriesList.map((entry) => (
                  <div key={entry.label}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">{entry.label}</span>
                      <span className="text-right font-medium text-foreground">
                        {String(entry.value)}
                      </span>
                    </div>
                    <Separator className="mt-3" />
                  </div>
                ))}
                {task.brainDispatchSummary.summaryLine ? (
                  <div className="space-y-2">
                    <div className="text-muted-foreground">闭环摘要</div>
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                      {task.brainDispatchSummary.summaryLine}
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {task.managerPacket ? (
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">项目经理判断</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {managerEntries.map((entry) => (
                  <div key={entry.label}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">{entry.label}</span>
                      <span className="text-right font-medium text-foreground">
                        {String(entry.value)}
                      </span>
                    </div>
                    <Separator className="mt-3" />
                  </div>
                ))}
                {task.managerPacket.userGoal ? (
                  <div className="space-y-2">
                    <div className="text-muted-foreground">用户目标</div>
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                      {task.managerPacket.userGoal}
                    </div>
                  </div>
                ) : null}
                {task.managerPacket.routingNote ? (
                  <div className="space-y-2">
                    <div className="text-muted-foreground">路由备注</div>
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                      {task.managerPacket.routingNote}
                    </div>
                  </div>
                ) : null}
                {task.managerPacket.handoffSummary ? (
                  <div className="space-y-2">
                    <div className="text-muted-foreground">交接摘要</div>
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                      {task.managerPacket.handoffSummary}
                    </div>
                  </div>
                ) : null}
                {task.managerPacket.clarifyQuestion ? (
                  <div className="space-y-2">
                    <div className="text-muted-foreground">澄清问题</div>
                    <div className="rounded-xl bg-warning/10 p-3 text-xs leading-5 text-foreground">
                      {task.managerPacket.clarifyQuestion}
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {taskAgentGroup ? (
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-base">任务子智能体</CardTitle>
                  <div className="flex flex-wrap justify-end gap-2">
                    {taskAgentGroup.source === "fallback" ? (
                      <Badge variant="outline" className="border-warning/40 text-warning-foreground">
                        兼容视图
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="bg-success/10 text-success">
                        正式任务域
                      </Badge>
                    )}
                    {taskAgentGroup.status ? <Badge variant="outline">{taskAgentGroup.status}</Badge> : null}
                    {taskAgentGroup.topology ? (
                      <Badge variant="secondary" className="bg-primary/10 text-primary">
                        {taskAgentGroup.topology}
                      </Badge>
                    ) : null}
                    {taskAgentGroup.coordinationMode ? (
                      <Badge variant="outline">{taskAgentGroup.coordinationMode}</Badge>
                    ) : null}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">开发组</span>
                  <span className="text-right font-medium text-foreground">
                    {taskAgentGroup.groupName || taskAgentGroup.groupId || "--"}
                  </span>
                </div>
                <Separator />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">分发责任</span>
                  <span className="text-right font-medium text-foreground">
                    {taskAgentGroup.dispatcherAgentId || "requirement dispatch agent"}
                  </span>
                </div>
                <Separator />
                <div className="space-y-2">
                  <div className="text-muted-foreground">能力编排</div>
                  <div className="grid gap-3">
                    <div className="space-y-2 rounded-xl bg-secondary/25 p-3">
                      <div className="text-xs text-muted-foreground">请求技能</div>
                      <CapabilityBadges
                        items={taskAgentGroup.requestedSkillIds}
                        emptyText="当前任务没有显式请求技能"
                      />
                    </div>
                    <div className="space-y-2 rounded-xl bg-secondary/25 p-3">
                      <div className="text-xs text-muted-foreground">实际技能</div>
                      <CapabilityBadges
                        items={taskAgentGroup.appliedSkillIds}
                        emptyText="当前还没有实际绑定技能"
                        emphasis
                      />
                    </div>
                    <div className="space-y-2 rounded-xl bg-secondary/25 p-3">
                      <div className="text-xs text-muted-foreground">请求工具</div>
                      <CapabilityBadges
                        items={taskAgentGroup.requestedToolIds}
                        emptyText="当前任务没有显式请求工具"
                      />
                    </div>
                    <div className="space-y-2 rounded-xl bg-secondary/25 p-3">
                      <div className="text-xs text-muted-foreground">实际工具</div>
                      <CapabilityBadges
                        items={taskAgentGroup.appliedToolIds}
                        emptyText="当前还没有实际绑定工具"
                        emphasis
                      />
                    </div>
                  </div>
                </div>
                <Separator />
                <div className="space-y-2">
                  <div className="text-muted-foreground">组间通信</div>
                  {taskAgentGroup.natsSubjects.length > 0 ? (
                    <div className="space-y-2">
                      {taskAgentGroup.natsSubjects.map((subject) => (
                        <div
                          key={`${subject.key}-${subject.value}`}
                          className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground"
                        >
                          <div className="font-medium">{subject.key}</div>
                          <div className="mt-1 break-all text-muted-foreground">{subject.value}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-muted-foreground">
                      当前任务还没有暴露组级 NATS subject。
                    </div>
                  )}
                </div>
                <Separator />
                <div className="space-y-2">
                  <div className="text-muted-foreground">创建痕迹</div>
                  {taskAgentGroup.timeline.length > 0 ? (
                    <div className="space-y-2">
                      {taskAgentGroup.timeline.map((entry) => (
                        <TaskAgentTimelineCard key={entry.id || `${entry.kind}-${entry.title}`} entry={entry} />
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-muted-foreground">
                      当前任务还没有沉淀出可展示的编组时间线。
                    </div>
                  )}
                </div>
                <Separator />
                <div className="space-y-2">
                  <div className="text-muted-foreground">开发成员</div>
                  {taskAgentGroup.members.length > 0 ? (
                    <div className="space-y-2">
                      {taskAgentGroup.members.map((member, index) => (
                        <TaskAgentMemberCard
                          key={`${member.role}-${member.id}-${member.branchId}-${index}`}
                          member={member}
                          title={`开发成员 ${index + 1}`}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-muted-foreground">
                      当前任务还没有展开出可见的开发成员。
                    </div>
                  )}
                </div>
                {taskAgentGroup.acceptanceAgent ? (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <div className="text-muted-foreground">验收责任</div>
                      <TaskAgentMemberCard member={taskAgentGroup.acceptanceAgent} title="验收 Agent" />
                    </div>
                  </>
                ) : null}
                {taskAgentGroup.warnings.length > 0 ? (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <div className="text-muted-foreground">编组提示</div>
                      <div className="rounded-xl bg-warning/10 p-3 text-xs leading-5 text-foreground">
                        {taskAgentGroup.warnings.join("；")}
                      </div>
                    </div>
                  </>
                ) : null}
                {taskAgentGroup.source === "fallback" ? (
                  <>
                    <Separator />
                    <div className="rounded-xl bg-warning/10 p-3 text-xs leading-5 text-foreground">
                      当前任务还在使用旧执行计划做兼容展示，建议让任务详情接口返回正式的
                      <code className="mx-1 rounded bg-background px-1 py-0.5 text-[11px]">taskAgentGroup</code>
                      投影后再观察。
                    </div>
                  </>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {taskAgentGroup?.acceptanceAgent ? (
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">验收摘要</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">验收成员</span>
                  <span className="text-right font-medium text-foreground">
                    {taskAgentGroup.acceptanceAgent.name || taskAgentGroup.acceptanceAgent.id || "--"}
                  </span>
                </div>
                <Separator />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">验收结论</span>
                  <Badge variant="secondary" className="bg-primary/10 text-primary">
                    {acceptanceOutcome(
                      task.status,
                      task.deliveryStatus,
                      taskAgentGroup.acceptanceAgent.runtimeStatus,
                    )}
                  </Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">运行状态</span>
                  <span className="font-medium text-foreground">
                    {memberRuntimeStatusLabel(taskAgentGroup.acceptanceAgent.runtimeStatus)}
                  </span>
                </div>
                <Separator />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">回传状态</span>
                  <span className="font-medium text-foreground">
                    {getDeliveryStatusLabel(task.deliveryStatus)}
                  </span>
                </div>
                {taskAgentGroup.acceptanceAgent.currentStepTitle ? (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <div className="text-muted-foreground">当前步骤</div>
                      <div className="rounded-xl bg-secondary/35 p-3 text-xs leading-5 text-foreground">
                        <div className="font-medium">
                          {taskAgentGroup.acceptanceAgent.currentStepTitle}
                        </div>
                        {taskAgentGroup.acceptanceAgent.currentStepMessage ? (
                          <div className="mt-1 text-muted-foreground">
                            {taskAgentGroup.acceptanceAgent.currentStepMessage}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">推荐动作</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button asChild variant="outline" className="w-full justify-between">
                <Link href="/tasks">
                  返回任务列表
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              {task.statusReason ? (
                <div
                  className={cn(
                    "rounded-xl p-3 text-xs leading-5",
                    task.status === "failed" || task.deliveryStatus === "failed"
                      ? "bg-destructive/10 text-destructive"
                      : "bg-secondary/40 text-muted-foreground",
                  )}
                >
                  {task.statusReason}
                </div>
              ) : null}
              <div className="rounded-xl bg-secondary/40 p-3 text-xs leading-5 text-muted-foreground">
                {task.status === "failed"
                  ? "当前任务失败，可以直接点击“重新执行”把它拉回运行态，再去执行过程观察流转。"
                  : task.status === "running"
                    ? "当前任务仍在执行中，可以切到执行过程查看节点状态与分支流向。"
                    : "当前任务已经稳定结束，如需复跑可直接点击“重新执行”生成新的运行态。"}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
