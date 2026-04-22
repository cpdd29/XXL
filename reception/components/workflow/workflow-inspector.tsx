"use client"

import { useMemo } from "react"
import Link from "next/link"
import { useQueries } from "@tanstack/react-query"
import { Activity, GitBranch, Play, RefreshCcw } from "lucide-react"

import { apiRequest } from "@/lib/api/client"
import { queryKeys } from "@/lib/api/query-keys"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type {
  ManagerPacket,
  WorkflowMonitorResponse,
  WorkflowRun,
  WorkflowTrigger,
} from "@/types"

export interface WorkflowEditorMeta {
  name: string
  description: string
  version: string
  status: string
  trigger: WorkflowTrigger
}

export interface EditableWorkflowNode {
  id: string
  type: string
  label: string
  description?: string | null
  config?: Record<string, unknown> | null
  agentId?: string | null
  toolId?: string | null
  workflowId?: string | null
}

interface WorkflowInspectorProps {
  workflowId?: string
  workflowMeta: WorkflowEditorMeta
  selectedNode?: EditableWorkflowNode
  runs: WorkflowRun[]
  isRunsLoading: boolean
  isRunsFetching: boolean
  monitor?: WorkflowMonitorResponse
  isMonitorLoading: boolean
  isMonitorFetching: boolean
  tickingRunId?: string | null
  canEditConfiguration: boolean
  canTickRun: boolean
  onWorkflowMetaChange: (patch: Partial<WorkflowEditorMeta>) => void
  onRefreshRuns: () => void
  onTickRun: (runId: string) => void
}

type DisplayWorkflowRelation = {
  relationRole: "parent" | "downstream"
  id: string
  relationType: string
  sourceNodeId?: string | null
  sourceNodeLabel?: string | null
  targetWorkflowId?: string | null
  targetWorkflowName?: string | null
  targetRunId?: string | null
  targetTaskId?: string | null
  targetStatus?: string | null
  trigger?: string | null
  handoffNote?: string | null
  payloadPreview?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

const workflowStatusOptions = [
  { value: "draft", label: "草稿" },
  { value: "active", label: "启用中" },
  { value: "running", label: "运行中" },
  { value: "paused", label: "已暂停" },
]

const runStatusConfig = {
  pending: "bg-warning/20 text-warning-foreground",
  running: "bg-primary/15 text-primary",
  completed: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
} as const

const runStatusLabels: Record<string, string> = {
  pending: "等待执行",
  running: "执行中",
  completed: "已完成",
  failed: "执行异常",
  cancelled: "已取消",
}

const workflowNodeTypeLabels: Record<string, string> = {
  workflow: "工作流节点",
  sub_workflow: "子工作流节点",
  trigger_workflow: "触发工作流节点",
}

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function visibleManagerPacket(packet?: ManagerPacket | null) {
  if (!packet) {
    return []
  }

  const labels: Array<[keyof ManagerPacket, string]> = [
    ["managerAction", "主脑动作"],
    ["nextOwner", "下一处理方"],
    ["workflowMode", "执行方式"],
    ["taskShape", "任务类型"],
    ["deliveryMode", "输出方式"],
    ["responseContract", "回复要求"],
  ]

  return labels
    .map(([key, label]) => ({ label, value: packet[key] }))
    .filter((item) => item.value !== null && item.value !== undefined && `${item.value}`.trim() !== "")
}

function issueSeverityClass(severity?: string | null) {
  return severity === "warning"
    ? "bg-warning/20 text-warning-foreground"
    : "bg-destructive/15 text-destructive"
}

function getTriggerTypeLabel(type?: string | null) {
  const normalized = String(type ?? "").trim().toLowerCase()
  const prefix = normalized.split(":")[0]
  if (prefix === "trigger_workflow") return "流程内触发"
  if (prefix === "sub_workflow") return "父子流程触发"
  if (prefix === "workflow") return "工作流触发"
  if (prefix === "internal") return "内部事件触发"
  if (prefix === "schedule") return "定时触发"
  if (prefix === "webhook") return "Webhook 触发"
  if (prefix === "manual") return "手动触发"
  return normalized ? "消息触发" : "未知触发"
}

function getRunStatusLabel(status?: string | null) {
  return runStatusLabels[status ?? ""] ?? status ?? "未知状态"
}

function getRelationStatusClass(status?: string | null) {
  const normalized = String(status ?? "").trim().toLowerCase()
  if (normalized === "completed") return "bg-success/15 text-success"
  if (normalized === "running") return "bg-primary/15 text-primary"
  if (normalized === "pending" || normalized === "waiting") {
    return "bg-warning/20 text-warning-foreground"
  }
  if (normalized === "failed" || normalized === "error" || normalized === "cancelled") {
    return "bg-destructive/15 text-destructive"
  }
  return "bg-muted text-muted-foreground"
}

function getRelationStatusLabel(status?: string | null) {
  const normalized = String(status ?? "").trim().toLowerCase()
  if (normalized === "waiting") return "等待中"
  if (normalized === "error") return "异常"
  return getRunStatusLabel(status)
}

function getWorkflowRelationTypeLabel(type?: string | null) {
  const normalized = String(type ?? "").trim().toLowerCase()
  if (normalized === "trigger_workflow") return "触发工作流"
  if (normalized === "sub_workflow" || normalized === "workflow") return "子工作流"
  return normalized || "工作流关系"
}

function getSelectedNodeConfigValue(node: EditableWorkflowNode | undefined, key: string) {
  const value = node?.config?.[key]
  if (value === null || value === undefined) return ""
  return String(value)
}

function truncateText(value?: string | null, limit = 220) {
  const normalized = String(value ?? "").trim()
  if (!normalized) return ""
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit - 1)}…`
}

function stringifyPayloadPreview(value?: Record<string, unknown> | null) {
  if (!value || Object.keys(value).length === 0) return ""
  try {
    return truncateText(JSON.stringify(value, null, 2), 240)
  } catch {
    return ""
  }
}

function buildParentRelation(run: WorkflowRun): DisplayWorkflowRelation | null {
  const dispatchContext = run.dispatchContext
  if (!dispatchContext?.parentWorkflowId && !dispatchContext?.parentRunId) {
    return null
  }

  return {
    relationRole: "parent",
    id: `${run.id}-parent-relation`,
    relationType: dispatchContext.workflowRelationType ?? "sub_workflow",
    sourceNodeId: dispatchContext.parentNodeId ?? null,
    sourceNodeLabel: dispatchContext.parentNodeLabel ?? null,
    targetWorkflowId: dispatchContext.parentWorkflowId ?? null,
    targetWorkflowName: dispatchContext.parentWorkflowName ?? null,
    targetRunId: dispatchContext.parentRunId ?? null,
    trigger: run.trigger,
    payloadPreview: stringifyPayloadPreview(dispatchContext.triggerPayload),
    createdAt: run.createdAt,
    updatedAt: run.updatedAt,
  }
}

function buildDownstreamRelations(run: WorkflowRun): DisplayWorkflowRelation[] {
  return (run.dispatchContext?.workflowRelations ?? []).map((relation) => ({
    relationRole: "downstream",
    id: relation.id,
    relationType: relation.relationType,
    sourceNodeId: relation.sourceNodeId ?? null,
    sourceNodeLabel: relation.sourceNodeLabel ?? null,
    targetWorkflowId: relation.targetWorkflowId ?? null,
    targetWorkflowName: relation.targetWorkflowName ?? null,
    targetRunId: relation.targetRunId ?? null,
    targetTaskId: relation.targetTaskId ?? null,
    targetStatus: relation.targetStatus ?? null,
    trigger: relation.trigger ?? null,
    handoffNote: relation.handoffNote ?? null,
    payloadPreview: relation.payloadPreview ?? null,
    createdAt: relation.createdAt,
    updatedAt: relation.updatedAt ?? null,
  }))
}

function buildTriggerFacts(run: WorkflowRun) {
  const triggerFacts: Array<{ label: string; value: string }> = []
  const trigger = String(run.trigger ?? "").trim()
  const dispatchContext = run.dispatchContext

  triggerFacts.push({ label: "触发方式", value: getTriggerTypeLabel(trigger) })

  if (trigger.startsWith("internal:")) {
    triggerFacts.push({ label: "内部事件", value: trigger.slice("internal:".length) || trigger })
  } else if (trigger.startsWith("trigger_workflow:")) {
    triggerFacts.push({ label: "触发链路", value: trigger })
  } else if (trigger.startsWith("workflow:")) {
    triggerFacts.push({ label: "上游触发", value: trigger })
  } else if (trigger.startsWith("webhook:")) {
    triggerFacts.push({ label: "Webhook", value: trigger.slice("webhook:".length) || trigger })
  }

  if (dispatchContext?.workflowRelationType) {
    triggerFacts.push({
      label: "链路类型",
      value: getWorkflowRelationTypeLabel(dispatchContext.workflowRelationType),
    })
  }

  if (dispatchContext?.workflowCallStack?.length) {
    triggerFacts.push({
      label: "父流程栈",
      value: dispatchContext.workflowCallStack.join(" -> "),
    })
  }

  if (dispatchContext?.internalEventId) {
    triggerFacts.push({
      label: "事件投递",
      value: dispatchContext.internalEventId,
    })
  }

  return triggerFacts
}

function collectRelatedRunIds(runs: WorkflowRun[]) {
  const relatedRunIds = new Set<string>()

  for (const run of runs) {
    const parentRunId = String(run.dispatchContext?.parentRunId ?? "").trim()
    if (parentRunId && parentRunId !== run.id) {
      relatedRunIds.add(parentRunId)
    }

    for (const relation of run.dispatchContext?.workflowRelations ?? []) {
      const relationRunId = String(relation.targetRunId ?? "").trim()
      if (relationRunId && relationRunId !== run.id) {
        relatedRunIds.add(relationRunId)
      }
    }
  }

  return Array.from(relatedRunIds)
}

function RelationCard({
  relation,
  relatedRun,
  canLocateRun,
}: {
  relation: DisplayWorkflowRelation
  relatedRun?: WorkflowRun
  canLocateRun: boolean
}) {
  const relationTypeLabel = getWorkflowRelationTypeLabel(relation.relationType)
  const relationStatus = relatedRun?.status ?? relation.targetStatus ?? null
  const relationRunId = relatedRun?.id ?? relation.targetRunId ?? null
  const relationTaskId = relatedRun?.taskId ?? relation.targetTaskId ?? null
  const relationWorkflowId = relatedRun?.workflowId ?? relation.targetWorkflowId ?? null
  const relationWorkflowName =
    relatedRun?.workflowName ??
    relation.targetWorkflowName ??
    relation.targetWorkflowId ??
    (relation.relationRole === "parent" ? "父流程" : "关联工作流")
  const relationStage = relatedRun?.currentStage ?? null
  const failureStage = relatedRun?.failureStage ?? relatedRun?.dispatchContext?.failureStage ?? null
  const failureMessage = relatedRun?.failureMessage ?? relatedRun?.dispatchContext?.failureMessage ?? null

  return (
    <div className="rounded-lg border border-border bg-secondary/20 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="bg-primary/10 text-primary">
              {relation.relationRole === "parent" ? "父流程" : relationTypeLabel}
            </Badge>
            {relationStatus ? (
              <Badge variant="secondary" className={cn("capitalize", getRelationStatusClass(relationStatus))}>
                {getRelationStatusLabel(relationStatus)}
              </Badge>
            ) : null}
          </div>
          <div className="text-sm font-medium text-foreground">
            {relationWorkflowName}
            {relationWorkflowId && relationWorkflowId !== relationWorkflowName ? ` · ${relationWorkflowId}` : ""}
          </div>
          {relation.sourceNodeLabel || relation.sourceNodeId ? (
            <div className="text-xs text-muted-foreground">
              来源节点: {relation.sourceNodeLabel ?? relation.sourceNodeId}
            </div>
          ) : null}
        </div>
        <GitBranch className="mt-1 size-4 text-muted-foreground" />
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {relationRunId ? (
          <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
            run: {relationRunId}
          </Badge>
        ) : null}
        {relationTaskId ? (
          <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
            task: {relationTaskId}
          </Badge>
        ) : null}
        {relation.trigger ? (
          <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
            trigger: {truncateText(relation.trigger, 60)}
          </Badge>
        ) : null}
      </div>

      {relationStage ? (
        <p className="mt-2 text-xs leading-5 text-muted-foreground">当前阶段: {relationStage}</p>
      ) : null}
      {relation.handoffNote ? (
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          交接说明: {relation.handoffNote}
        </p>
      ) : null}
      {relation.payloadPreview ? (
        <div className="mt-2 rounded-md border border-border bg-background/80 px-2 py-2 text-xs leading-5 text-foreground">
          触发参数: {relation.payloadPreview}
        </div>
      ) : null}
      {failureStage || failureMessage ? (
        <div className="mt-2 rounded-md border border-destructive/20 bg-destructive/5 px-2 py-2 text-xs leading-5 text-foreground">
          {failureStage ? `故障定位: ${failureStage}` : "故障定位"}
          {failureMessage ? ` · ${failureMessage}` : ""}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {relationTaskId ? (
          <Button asChild size="sm" variant="ghost">
            <Link href={`/collaboration?taskId=${encodeURIComponent(relationTaskId)}`}>
              进入 Collaboration
            </Link>
          </Button>
        ) : null}
        {canLocateRun && relationRunId ? (
          <Button asChild size="sm" variant="outline">
            <a href={`#workflow-run-${relationRunId}`}>定位记录</a>
          </Button>
        ) : null}
      </div>

      <div className="mt-2 text-[11px] text-muted-foreground">
        创建于 {formatTimestamp(relation.createdAt)}
        {relation.updatedAt ? ` · 更新于 ${formatTimestamp(relation.updatedAt)}` : ""}
      </div>
    </div>
  )
}

export function WorkflowInspector({
  workflowId,
  workflowMeta,
  selectedNode,
  runs,
  isRunsLoading,
  isRunsFetching,
  monitor,
  isMonitorLoading,
  isMonitorFetching,
  tickingRunId,
  canEditConfiguration,
  canTickRun,
  onWorkflowMetaChange,
  onRefreshRuns,
  onTickRun,
}: WorkflowInspectorProps) {
  void monitor
  void isMonitorLoading
  void isMonitorFetching

  const relatedRunIds = useMemo(() => collectRelatedRunIds(runs), [runs])
  const runIdsInList = useMemo(() => new Set(runs.map((run) => run.id)), [runs])
  const selectedNodeNote = getSelectedNodeConfigValue(selectedNode, "handoffNote")
  const selectedTriggerPayload = getSelectedNodeConfigValue(selectedNode, "triggerPayload")

  const relatedRunQueries = useQueries({
    queries: relatedRunIds.map((runId) => ({
      queryKey: queryKeys.workflows.run(runId),
      queryFn: () => apiRequest<WorkflowRun>(`/api/workflows/runs/${encodeURIComponent(runId)}`),
      staleTime: 10_000,
      enabled: Boolean(runId),
    })),
  })

  const relatedRunsById = useMemo(() => {
    const byId = new Map<string, WorkflowRun>()

    for (const run of runs) {
      byId.set(run.id, run)
    }

    relatedRunIds.forEach((runId, index) => {
      const relatedRun = relatedRunQueries[index]?.data
      if (relatedRun) {
        byId.set(runId, relatedRun)
      }
    })

    return byId
  }, [relatedRunIds, relatedRunQueries, runs])

  return (
    <div className="h-full w-full min-w-0 bg-card">
      <ScrollArea className="h-full">
        <div className="flex flex-col gap-4 p-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm">工作流设置</CardTitle>
                <Badge variant="secondary" className="text-xs">
                  {canEditConfiguration ? "可编辑" : "只读"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">工作流名称</div>
                <Input
                  value={workflowMeta.name}
                  disabled={!canEditConfiguration}
                  onChange={(event) => onWorkflowMetaChange({ name: event.target.value })}
                />
              </div>

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">工作流介绍</div>
                <Textarea
                  value={workflowMeta.description}
                  disabled={!canEditConfiguration}
                  onChange={(event) => onWorkflowMetaChange({ description: event.target.value })}
                  rows={4}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">版本</div>
                  <Input
                    value={workflowMeta.version}
                    disabled={!canEditConfiguration}
                    onChange={(event) => onWorkflowMetaChange({ version: event.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">状态</div>
                  <Select
                    value={workflowMeta.status}
                    disabled={!canEditConfiguration}
                    onValueChange={(value) => onWorkflowMetaChange({ status: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {workflowStatusOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {selectedNode ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">当前选中节点</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">
                    {workflowNodeTypeLabels[selectedNode.type] ?? selectedNode.type}
                  </Badge>
                  {selectedNode.workflowId ? (
                    <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                      目标流程: {selectedNode.workflowId}
                    </Badge>
                  ) : null}
                </div>
                <div className="text-sm font-medium text-foreground">{selectedNode.label}</div>
                {selectedNode.description ? (
                  <p className="text-xs leading-5 text-muted-foreground">{selectedNode.description}</p>
                ) : null}
                {selectedNodeNote ? (
                  <div className="rounded-lg border border-border bg-background/70 px-3 py-2 text-xs leading-5 text-muted-foreground">
                    {selectedNode.type === "trigger_workflow" ? "触发说明" : "交接说明"}: {selectedNodeNote}
                  </div>
                ) : null}
                {selectedNode.type === "trigger_workflow" && selectedTriggerPayload ? (
                  <div className="rounded-lg border border-border bg-background/70 px-3 py-2 text-xs leading-5 text-foreground">
                    触发参数模板: {selectedTriggerPayload}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm">最近运行记录</CardTitle>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onRefreshRuns}
                  disabled={!workflowId || isRunsFetching}
                >
                  <RefreshCcw className={cn("mr-2 size-4", isRunsFetching && "animate-spin")} />
                  刷新
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {!workflowId ? (
                <div className="text-sm leading-6 text-muted-foreground">
                  当前还没有持久化的工作流 ID。保存后，这里会展示执行历史。
                </div>
              ) : isRunsLoading ? (
                <div className="text-sm leading-6 text-muted-foreground">正在加载运行历史...</div>
              ) : runs.length === 0 ? (
                <div className="text-sm leading-6 text-muted-foreground">
                  还没有运行记录。工作流被触发后，会在这里展示执行历史。
                </div>
              ) : (
                <div className="space-y-3">
                  {runs.map((run) => {
                    const issueNodes = run.nodes.filter((node) => (node.errorCount ?? 0) > 0)
                    const managerPacket = run.dispatchContext?.managerPacket
                    const brainDispatchSummary = run.dispatchContext?.brainDispatchSummary
                    const managerEntries = visibleManagerPacket(managerPacket)
                    const parentRelation = buildParentRelation(run)
                    const downstreamRelations = buildDownstreamRelations(run)
                    const triggerFacts = buildTriggerFacts(run)
                    const failureStage = run.failureStage ?? run.dispatchContext?.failureStage ?? null
                    const failureMessage = run.failureMessage ?? run.dispatchContext?.failureMessage ?? null
                    const failureNodeLabel = run.dispatchContext?.selectedNodeLabel ?? null
                    const failureNodeType = run.dispatchContext?.selectedNodeType ?? null
                    const triggerPayloadPreview = stringifyPayloadPreview(run.dispatchContext?.triggerPayload)

                    return (
                      <div
                        key={run.id}
                        id={`workflow-run-${run.id}`}
                        className="rounded-xl border border-border bg-secondary/20 p-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <Badge
                                variant="secondary"
                                className={cn(
                                  "capitalize",
                                  runStatusConfig[run.status as keyof typeof runStatusConfig],
                                )}
                              >
                                {getRunStatusLabel(run.status)}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {getTriggerTypeLabel(run.trigger)}
                              </span>
                              {run.dispatchContext?.workflowRelationType ? (
                                <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                                  {getWorkflowRelationTypeLabel(run.dispatchContext.workflowRelationType)}
                                </Badge>
                              ) : null}
                            </div>
                            <div className="text-sm font-medium text-foreground">{run.currentStage}</div>
                            <div className="text-xs text-muted-foreground">
                              创建于 {formatTimestamp(run.createdAt)}
                            </div>
                          </div>
                          <Activity className="mt-1 size-4 text-muted-foreground" />
                        </div>

                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {run.taskId ? (
                            <Button asChild size="sm" variant="ghost">
                              <Link href={`/collaboration?taskId=${encodeURIComponent(run.taskId)}`}>
                                查看执行过程
                              </Link>
                            </Button>
                          ) : null}
                          {run.status === "pending" || run.status === "running" ? (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={!canTickRun || tickingRunId === run.id}
                              onClick={() => onTickRun(run.id)}
                            >
                              <Play className="mr-2 size-4" />
                              {tickingRunId === run.id ? "推进中..." : "推进一轮"}
                            </Button>
                          ) : null}
                        </div>

                        {triggerFacts.length > 0 || parentRelation || downstreamRelations.length > 0 || triggerPayloadPreview ? (
                          <div className="mt-3 rounded-lg border border-border bg-background/70 p-3">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs font-medium text-foreground">运行链路</div>
                              <Badge variant="secondary" className="bg-primary/10 text-primary">
                                workflow relations
                              </Badge>
                            </div>

                            {triggerFacts.length > 0 ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {triggerFacts.map((item) => (
                                  <Badge
                                    key={`${run.id}-${item.label}-${item.value}`}
                                    variant="outline"
                                    className="border-border text-[11px] text-muted-foreground"
                                  >
                                    {item.label}: {item.value}
                                  </Badge>
                                ))}
                              </div>
                            ) : null}

                            {triggerPayloadPreview ? (
                              <div className="mt-2 rounded-md border border-border bg-background/80 px-2 py-2 text-xs leading-5 text-foreground">
                                触发载荷: {triggerPayloadPreview}
                              </div>
                            ) : null}

                            {parentRelation ? (
                              <div className="mt-3 space-y-2">
                                <div className="text-xs font-medium text-foreground">父流程关系</div>
                                <RelationCard
                                  relation={parentRelation}
                                  relatedRun={
                                    parentRelation.targetRunId
                                      ? relatedRunsById.get(parentRelation.targetRunId)
                                      : undefined
                                  }
                                  canLocateRun={Boolean(
                                    parentRelation.targetRunId && runIdsInList.has(parentRelation.targetRunId),
                                  )}
                                />
                              </div>
                            ) : null}

                            {downstreamRelations.length > 0 ? (
                              <div className="mt-3 space-y-2">
                                <div className="text-xs font-medium text-foreground">子流程 / 触发流程关系</div>
                                {downstreamRelations.map((relation) => (
                                  <RelationCard
                                    key={`${run.id}-${relation.id}`}
                                    relation={relation}
                                    relatedRun={
                                      relation.targetRunId
                                        ? relatedRunsById.get(relation.targetRunId)
                                        : undefined
                                    }
                                    canLocateRun={Boolean(
                                      relation.targetRunId && runIdsInList.has(relation.targetRunId),
                                    )}
                                  />
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ) : null}

                        {failureStage || failureMessage || failureNodeLabel ? (
                          <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="text-xs font-medium text-foreground">故障定位</div>
                              {failureStage ? (
                                <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                                  {failureStage}
                                </Badge>
                              ) : null}
                              {failureNodeLabel ? (
                                <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                                  节点: {failureNodeLabel}
                                  {failureNodeType ? ` · ${failureNodeType}` : ""}
                                </Badge>
                              ) : null}
                            </div>
                            {failureMessage ? (
                              <p className="mt-2 text-xs leading-5 text-foreground">{failureMessage}</p>
                            ) : null}
                          </div>
                        ) : null}

                        {managerPacket ? (
                          <div className="mt-3 rounded-lg border border-border bg-background/70 p-3">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs font-medium text-foreground">项目经理分发</div>
                              <Badge variant="secondary" className="bg-primary/10 text-primary">
                                {managerPacket.managerRole ?? "主脑调度"}
                              </Badge>
                            </div>
                            {managerEntries.length > 0 ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {managerEntries.map((entry) => (
                                  <Badge
                                    key={`${run.id}-${entry.label}`}
                                    variant="outline"
                                    className="border-border text-[11px] text-muted-foreground"
                                  >
                                    {entry.label}: {String(entry.value)}
                                  </Badge>
                                ))}
                              </div>
                            ) : null}
                            {managerPacket.handoffSummary ? (
                              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                {managerPacket.handoffSummary}
                              </p>
                            ) : null}
                            {managerPacket.clarifyQuestion ? (
                              <div className="mt-2 rounded-md bg-warning/10 px-2 py-2 text-xs leading-5 text-foreground">
                                澄清问题：{managerPacket.clarifyQuestion}
                              </div>
                            ) : null}
                          </div>
                        ) : null}

                        {brainDispatchSummary ? (
                          <div className="mt-3 rounded-lg border border-border bg-background/70 p-3">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs font-medium text-foreground">主脑分发摘要</div>
                              <Badge variant="secondary" className="bg-primary/10 text-primary">
                                {brainDispatchSummary.dispatchType ?? "dispatch"}
                              </Badge>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {brainDispatchSummary.workflowMode ? (
                                <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                                  执行方式: {brainDispatchSummary.workflowMode}
                                </Badge>
                              ) : null}
                              {brainDispatchSummary.executionAgent ? (
                                <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                                  执行角色: {brainDispatchSummary.executionAgent}
                                </Badge>
                              ) : null}
                              {brainDispatchSummary.nextOwner ? (
                                <Badge variant="outline" className="border-border text-[11px] text-muted-foreground">
                                  下一处理方: {brainDispatchSummary.nextOwner}
                                </Badge>
                              ) : null}
                            </div>
                            {brainDispatchSummary.summaryLine ? (
                              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                {brainDispatchSummary.summaryLine}
                              </p>
                            ) : null}
                          </div>
                        ) : null}

                        {issueNodes.length > 0 ? (
                          <div className="mt-3 space-y-2 rounded-lg border border-destructive/20 bg-background/70 p-3">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs font-medium text-foreground">节点异常归档</div>
                              <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                                {issueNodes.length} 个节点
                              </Badge>
                            </div>
                            <div className="space-y-2">
                              {issueNodes.map((node) => (
                                <div
                                  key={`${run.id}-${node.id}-issues`}
                                  className="rounded-lg border border-border bg-secondary/20 p-2"
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="text-xs font-medium text-foreground">{node.label}</div>
                                    <Badge variant="secondary" className="bg-muted text-muted-foreground">
                                      {node.errorCount} 条
                                    </Badge>
                                  </div>
                                  {node.latestError ? (
                                    <p className="mt-2 text-xs leading-5 text-foreground">{node.latestError}</p>
                                  ) : null}
                                  <div className="mt-2 space-y-1">
                                    {node.errorHistory.slice(0, 3).map((issue) => (
                                      <div
                                        key={issue.id}
                                        className="rounded-md border border-border/70 bg-background/80 p-2"
                                      >
                                        <div className="flex items-center justify-between gap-2 text-[11px]">
                                          <Badge
                                            variant="secondary"
                                            className={cn("border-transparent", issueSeverityClass(issue.severity))}
                                          >
                                            {issue.severity}
                                          </Badge>
                                          <span className="text-muted-foreground">
                                            {formatTimestamp(issue.timestamp)}
                                          </span>
                                        </div>
                                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                          {issue.message}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </div>
  )
}
