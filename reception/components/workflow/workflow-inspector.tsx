"use client"

import Link from "next/link"
import { Activity, Play, RefreshCcw } from "lucide-react"

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
import { cn } from "@/lib/utils"
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
  if (prefix === "internal") return "工作流触发"
  if (prefix === "schedule") return "定时触发"
  if (prefix === "webhook") return "Webhook 触发"
  if (prefix === "manual") return "手动触发"
  return normalized ? "消息触发" : "未知触发"
}

function getRunStatusLabel(status?: string | null) {
  return runStatusLabels[status ?? ""] ?? status ?? "未知状态"
}

export function WorkflowInspector({
  workflowId,
  workflowMeta,
  runs,
  isRunsLoading,
  isRunsFetching,
  monitor,
  tickingRunId,
  canEditConfiguration,
  canTickRun,
  onWorkflowMetaChange,
  onRefreshRuns,
  onTickRun,
}: WorkflowInspectorProps) {
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
                  还没有运行记录。点击右上角“运行”后会在这里出现。
                </div>
              ) : (
                <div className="space-y-3">
                  {runs.map((run) => {
                    const issueNodes = run.nodes.filter((node) => (node.errorCount ?? 0) > 0)
                    const managerPacket = run.dispatchContext?.managerPacket
                    const brainDispatchSummary = run.dispatchContext?.brainDispatchSummary
                    const managerEntries = visibleManagerPacket(managerPacket)

                    return (
                      <div key={run.id} className="rounded-xl border border-border bg-secondary/20 p-3">
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
