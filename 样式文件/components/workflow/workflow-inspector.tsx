"use client"

import Link from "next/link"
import { RefreshCcw, Play, Activity } from "lucide-react"

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
  Agent,
  WorkflowMonitorResponse,
  WorkflowRun,
  WorkflowTrigger,
  WorkflowTriggerType,
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
  agentId?: string | null
}

interface WorkflowInspectorProps {
  workflowId?: string
  workflowMeta: WorkflowEditorMeta
  selectedNode?: EditableWorkflowNode
  agents: Agent[]
  runs: WorkflowRun[]
  isRunsLoading: boolean
  isRunsFetching: boolean
  monitor?: WorkflowMonitorResponse
  isMonitorLoading: boolean
  isMonitorFetching: boolean
  tickingRunId?: string | null
  onWorkflowMetaChange: (patch: Partial<WorkflowEditorMeta>) => void
  onTriggerChange: (trigger: WorkflowTrigger) => void
  onNodeLabelChange: (label: string) => void
  onNodeAgentChange: (agentId?: string) => void
  onRefreshRuns: () => void
  onTickRun: (runId: string) => void
}

const triggerTypeOptions: Array<{ value: WorkflowTriggerType; label: string; hint: string }> = [
  { value: "message", label: "消息触发", hint: "按关键词或消息事件进入流程" },
  { value: "schedule", label: "定时触发", hint: "按 Cron 周期自动执行" },
  { value: "webhook", label: "Webhook 触发", hint: "由外部系统回调进入流程" },
  { value: "internal", label: "内部触发", hint: "由 Agent 或系统内部事件发起" },
  { value: "manual", label: "手动触发", hint: "由控制台手动启动或推进流程" },
]

const workflowStatusOptions = [
  { value: "draft", label: "草稿" },
  { value: "active", label: "启用中" },
  { value: "running", label: "运行中" },
  { value: "paused", label: "已暂停" },
]

const triggerLanguageOptions = [
  { value: "auto", label: "自动检测" },
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
] as const

const runStatusConfig = {
  pending: "bg-warning/20 text-warning-foreground",
  running: "bg-primary/15 text-primary",
  completed: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
} as const

const monitorStateConfig = {
  queued: "bg-muted text-muted-foreground",
  scheduled: "bg-warning/20 text-warning-foreground",
  claimed: "bg-primary/15 text-primary",
  claimed_stale: "bg-warning/20 text-warning-foreground",
  running: "bg-primary/15 text-primary",
  retry_waiting: "bg-warning/20 text-warning-foreground",
  overdue: "bg-destructive/15 text-destructive",
  execution_timeout: "bg-destructive/15 text-destructive",
  completed: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
} as const

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function issueSeverityClass(severity?: string | null) {
  return severity === "warning"
    ? "bg-warning/20 text-warning-foreground"
    : "bg-destructive/15 text-destructive"
}

function getSelectedNodeLatestIssue(runs: WorkflowRun[], nodeId?: string) {
  if (!nodeId) return null

  for (const run of runs) {
    const node = run.nodes.find((item) => item.id === nodeId && item.errorHistory.length > 0)
    if (node) {
      return {
        run,
        issue: node.errorHistory[0],
        errorCount: node.errorCount ?? node.errorHistory.length,
      }
    }
  }

  return null
}

function getTriggerValue(trigger: WorkflowTrigger) {
  switch (trigger.type) {
    case "message":
      return trigger.keyword ?? ""
    case "schedule":
      return trigger.cron ?? ""
    case "webhook":
      return trigger.webhookPath ?? ""
    case "internal":
      return trigger.internalEvent ?? ""
    case "manual":
      return trigger.description ?? ""
  }

  return ""
}

function getTriggerFieldMeta(type: WorkflowTriggerType) {
  switch (type) {
    case "message":
      return {
        label: "关键词",
        placeholder: "例如：搜索, 写作, 帮助",
      }
    case "schedule":
      return {
        label: "Cron 表达式",
        placeholder: "例如：0 * * * *",
      }
    case "webhook":
      return {
        label: "Webhook 路径",
        placeholder: "例如：/webhooks/customer-service",
      }
    case "internal":
      return {
        label: "内部事件",
        placeholder: "例如：agent.completed",
      }
  }

  return {
    label: "触发参数",
    placeholder: "请输入触发参数",
  }
}

function getTriggerTypeLabel(type?: string | null) {
  return triggerTypeOptions.find((option) => option.value === type)?.label ?? type ?? "未知触发"
}

function getTriggerMonitorSummary(monitor?: WorkflowMonitorResponse, fallback?: WorkflowTrigger) {
  const trigger = monitor?.workflow?.trigger ?? fallback
  if (!trigger || typeof trigger === "string") {
    return {
      label: "未配置",
      detail: "当前还没有持久化触发配置",
    }
  }

  if (trigger.type === "message") {
    return {
      label: getTriggerTypeLabel(trigger.type),
      detail: trigger.keyword?.trim() ? `关键词：${trigger.keyword}` : "按消息路由命中工作流",
    }
  }
  if (trigger.type === "schedule") {
    return {
      label: getTriggerTypeLabel(trigger.type),
      detail: trigger.cron?.trim() ? `Cron：${trigger.cron}` : "尚未配置 Cron 表达式",
    }
  }
  if (trigger.type === "webhook") {
    return {
      label: getTriggerTypeLabel(trigger.type),
      detail: trigger.webhookPath?.trim() ? `路径：${trigger.webhookPath}` : "尚未配置 Webhook 路径",
    }
  }
  if (trigger.type === "internal") {
    return {
      label: getTriggerTypeLabel(trigger.type),
      detail: trigger.internalEvent?.trim() ? `事件：${trigger.internalEvent}` : "尚未配置内部事件名",
    }
  }

  return {
    label: getTriggerTypeLabel(trigger.type),
    detail: trigger.description?.trim() || "由控制台手动触发工作流运行",
  }
}

function patchTriggerValue(trigger: WorkflowTrigger, value: string): WorkflowTrigger {
  if (trigger.type === "message") {
    return { ...trigger, keyword: value }
  }
  if (trigger.type === "schedule") {
    return { ...trigger, cron: value }
  }
  if (trigger.type === "webhook") {
    return { ...trigger, webhookPath: value }
  }
  if (trigger.type === "internal") {
    return { ...trigger, internalEvent: value }
  }
  return { ...trigger, description: value }
}

function triggerChannelsValue(trigger: WorkflowTrigger) {
  return (trigger.channels ?? []).join(", ")
}

function patchTriggerChannels(trigger: WorkflowTrigger, value: string): WorkflowTrigger {
  const channels = value
    .replaceAll("，", ",")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)

  return {
    ...trigger,
    channels: Array.from(new Set(channels)),
  }
}

function nextTriggerByType(type: WorkflowTriggerType, current: WorkflowTrigger): WorkflowTrigger {
  return {
    type,
    keyword: type === "message" ? current.keyword ?? "" : null,
    cron: type === "schedule" ? current.cron ?? "" : null,
    webhookPath: type === "webhook" ? current.webhookPath ?? "" : null,
    internalEvent: type === "internal" ? current.internalEvent ?? "" : null,
    description:
      type === "internal" || type === "manual"
        ? current.description ?? "由控制台或内部流程驱动工作流运行"
        : current.description ?? "",
    priority: current.priority ?? 100,
    channels: current.channels ?? [],
    preferredLanguage: current.preferredLanguage ?? null,
    stepDelaySeconds: current.stepDelaySeconds ?? 0.6,
    maxDispatchRetry: current.maxDispatchRetry ?? 6,
    dispatchRetryBackoffSeconds: current.dispatchRetryBackoffSeconds ?? 2,
    executionTimeoutSeconds: current.executionTimeoutSeconds ?? 45,
  }
}

export function WorkflowInspector({
  workflowId,
  workflowMeta,
  selectedNode,
  agents,
  runs,
  isRunsLoading,
  isRunsFetching,
  monitor,
  isMonitorLoading,
  isMonitorFetching,
  tickingRunId,
  onWorkflowMetaChange,
  onTriggerChange,
  onNodeLabelChange,
  onNodeAgentChange,
  onRefreshRuns,
  onTickRun,
}: WorkflowInspectorProps) {
  const triggerFieldMeta = getTriggerFieldMeta(workflowMeta.trigger.type)
  const triggerTypeHint =
    triggerTypeOptions.find((option) => option.value === workflowMeta.trigger.type)?.hint ??
    "配置工作流的入口方式"
  const selectedNodeLatestIssue = getSelectedNodeLatestIssue(runs, selectedNode?.id)
  const triggerMonitorSummary = getTriggerMonitorSummary(monitor, workflowMeta.trigger)
  const monitorStats = monitor?.stats
  const latestRunCreatedAt = monitor?.items?.[0]?.createdAt
  const monitorMetricItems = monitorStats
    ? [
        { label: "总运行", value: monitorStats.total },
        { label: "运行中", value: monitorStats.running },
        { label: "已完成", value: monitorStats.completed },
        { label: "异常态", value: monitorStats.unhealthy },
        { label: "待调度", value: monitorStats.scheduled + monitorStats.queued },
        { label: "已认领", value: monitorStats.claimed },
      ]
    : []

  return (
    <div className="h-full w-[360px] shrink-0 border-l border-border bg-card">
      <ScrollArea className="h-full">
        <div className="space-y-4 p-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">流程配置</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">工作流名称</div>
                <Input
                  value={workflowMeta.name}
                  onChange={(event) => onWorkflowMetaChange({ name: event.target.value })}
                />
              </div>

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">描述</div>
                <Textarea
                  value={workflowMeta.description}
                  onChange={(event) => onWorkflowMetaChange({ description: event.target.value })}
                  rows={3}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">版本</div>
                  <Input
                    value={workflowMeta.version}
                    onChange={(event) => onWorkflowMetaChange({ version: event.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">状态</div>
                  <Select
                    value={workflowMeta.status}
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

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">触发方式</div>
                <Select
                  value={workflowMeta.trigger.type}
                  onValueChange={(value) =>
                    onTriggerChange(nextTriggerByType(value as WorkflowTriggerType, workflowMeta.trigger))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {triggerTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs leading-5 text-muted-foreground">
                  {triggerTypeHint}
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">{triggerFieldMeta.label}</div>
                <Input
                  value={getTriggerValue(workflowMeta.trigger)}
                  placeholder={triggerFieldMeta.placeholder}
                  onChange={(event) =>
                    onTriggerChange(patchTriggerValue(workflowMeta.trigger, event.target.value))
                  }
                />
              </div>

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">触发说明</div>
                <Textarea
                  rows={3}
                  value={workflowMeta.trigger.description ?? ""}
                  onChange={(event) =>
                    onTriggerChange({ ...workflowMeta.trigger, description: event.target.value })
                  }
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">路由优先级</div>
                  <Input
                    type="number"
                    min={0}
                    value={workflowMeta.trigger.priority ?? 100}
                    onChange={(event) =>
                      onTriggerChange({
                        ...workflowMeta.trigger,
                        priority: Number(event.target.value || 100),
                      })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">偏好语言</div>
                  <Select
                    value={workflowMeta.trigger.preferredLanguage ?? "auto"}
                    onValueChange={(value) =>
                      onTriggerChange({
                        ...workflowMeta.trigger,
                        preferredLanguage: value === "auto" ? null : (value as "zh" | "en"),
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {triggerLanguageOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">渠道限制</div>
                <Input
                  value={triggerChannelsValue(workflowMeta.trigger)}
                  placeholder="例如：telegram, wecom"
                  onChange={(event) =>
                    onTriggerChange(patchTriggerChannels(workflowMeta.trigger, event.target.value))
                  }
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  留空表示所有渠道都可命中。消息触发时，这些字段会和关键词一起参与后端路由。
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">调度策略</div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <div className="text-[11px] text-muted-foreground">步进间隔（秒）</div>
                    <Input
                      type="number"
                      min={0}
                      step="0.1"
                      value={workflowMeta.trigger.stepDelaySeconds ?? 0.6}
                      onChange={(event) =>
                        onTriggerChange({
                          ...workflowMeta.trigger,
                          stepDelaySeconds: Number(event.target.value || 0),
                        })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="text-[11px] text-muted-foreground">最大重试次数</div>
                    <Input
                      type="number"
                      min={0}
                      step="1"
                      value={workflowMeta.trigger.maxDispatchRetry ?? 6}
                      onChange={(event) =>
                        onTriggerChange({
                          ...workflowMeta.trigger,
                          maxDispatchRetry: Number(event.target.value || 0),
                        })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="text-[11px] text-muted-foreground">重试退避（秒）</div>
                    <Input
                      type="number"
                      min={0}
                      step="0.1"
                      value={workflowMeta.trigger.dispatchRetryBackoffSeconds ?? 2}
                      onChange={(event) =>
                        onTriggerChange({
                          ...workflowMeta.trigger,
                          dispatchRetryBackoffSeconds: Number(event.target.value || 0),
                        })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="text-[11px] text-muted-foreground">执行超时（秒）</div>
                    <Input
                      type="number"
                      min={0}
                      step="1"
                      value={workflowMeta.trigger.executionTimeoutSeconds ?? 45}
                      onChange={(event) =>
                        onTriggerChange({
                          ...workflowMeta.trigger,
                          executionTimeoutSeconds: Number(event.target.value || 0),
                        })
                      }
                    />
                  </div>
                </div>
                <p className="text-xs leading-5 text-muted-foreground">
                  这些字段会随工作流触发配置一起保存，便于后续把调度治理参数下沉到 workflow 级策略。
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">节点配置</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedNode ? (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">{selectedNode.label}</div>
                      <div className="text-xs text-muted-foreground">节点 ID：{selectedNode.id}</div>
                    </div>
                    <Badge variant="secondary">{selectedNode.type}</Badge>
                  </div>

                  <div className="space-y-2">
                    <div className="text-xs text-muted-foreground">显示名称</div>
                    <Input
                      value={selectedNode.label}
                      onChange={(event) => onNodeLabelChange(event.target.value)}
                    />
                  </div>

                  {selectedNode.type === "agent" ? (
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">绑定 Agent</div>
                      <Select
                        value={selectedNode.agentId ?? "__unbound__"}
                        onValueChange={(value) =>
                          onNodeAgentChange(value === "__unbound__" ? undefined : value)
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="选择一个 Agent" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__unbound__">未绑定</SelectItem>
                          {agents.map((agent) => (
                            <SelectItem key={agent.id} value={agent.id}>
                              {agent.name} · {agent.type}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs leading-5 text-muted-foreground">
                        当前节点会把真实 `agent_id` 保存到工作流定义中，后端执行引擎会据此决定分支和运行态。
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs leading-5 text-muted-foreground">
                      {selectedNode.type === "trigger"
                        ? "触发节点的实际行为由上方“流程配置”里的触发器设置控制。"
                        : "当前节点暂时只支持编辑显示名称，后续还可以继续补条件表达式、工具参数和并行策略。"}
                    </p>
                  )}

                  {selectedNodeLatestIssue ? (
                    <div className="space-y-2 rounded-lg border border-destructive/20 bg-background/70 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-medium text-foreground">最近一次异常</div>
                        <Badge
                          variant="secondary"
                          className={cn(
                            "border-transparent",
                            issueSeverityClass(selectedNodeLatestIssue.issue.severity),
                          )}
                        >
                          {selectedNodeLatestIssue.issue.severity}
                        </Badge>
                      </div>
                      <p className="text-xs leading-5 text-foreground">
                        {selectedNodeLatestIssue.issue.message}
                      </p>
                      <div className="text-[11px] leading-5 text-muted-foreground">
                        发生于 {formatTimestamp(selectedNodeLatestIssue.issue.timestamp)}，运行 ID：
                        {selectedNodeLatestIssue.run.id}
                      </div>
                      <div className="text-[11px] leading-5 text-muted-foreground">
                        当前节点累计归档 {selectedNodeLatestIssue.errorCount} 条异常记录。
                      </div>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="text-sm leading-6 text-muted-foreground">
                  点击画布中的任意节点后，这里会显示对应的配置项。
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm">运行监控</CardTitle>
                {workflowId && isMonitorFetching ? (
                  <Badge variant="secondary" className="bg-secondary/60 text-muted-foreground">
                    刷新中
                  </Badge>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {!workflowId ? (
                <div className="text-sm leading-6 text-muted-foreground">
                  当前还没有持久化的工作流 ID。保存后，这里会展示调度与运行监控快照。
                </div>
              ) : isMonitorLoading && !monitor ? (
                <div className="text-sm leading-6 text-muted-foreground">正在加载监控快照...</div>
              ) : !monitorStats ? (
                <div className="text-sm leading-6 text-muted-foreground">
                  暂时还没有可用的监控快照，请稍后刷新。
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    {monitorMetricItems.map((item) => (
                      <div
                        key={item.label}
                        className="rounded-xl border border-border bg-secondary/20 px-3 py-2"
                      >
                        <div className="text-[11px] text-muted-foreground">{item.label}</div>
                        <div className="mt-1 text-lg font-semibold text-foreground">{item.value}</div>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-xl border border-border bg-secondary/20 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs font-medium text-foreground">持久化触发配置</div>
                      <Badge
                        variant="secondary"
                        className={cn(
                          "border-transparent",
                          monitorStateConfig[
                            (monitor?.items?.[0]?.monitor?.monitorState ??
                              "queued") as keyof typeof monitorStateConfig
                          ] ?? "bg-muted text-muted-foreground",
                        )}
                      >
                        {monitor?.items?.[0]?.monitor?.monitorState ?? "queued"}
                      </Badge>
                    </div>
                    <div className="mt-2 text-sm font-medium text-foreground">
                      {triggerMonitorSummary.label}
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {triggerMonitorSummary.detail}
                    </p>
                    <div className="mt-2 text-[11px] leading-5 text-muted-foreground">
                      最近运行 {formatTimestamp(latestRunCreatedAt)} · 最近快照 {formatTimestamp(monitor?.timestamp)}
                    </div>
                  </div>

                  {monitor.alerts.length > 0 ? (
                    <div className="space-y-2 rounded-xl border border-warning/20 bg-warning/5 p-3">
                      <div className="text-xs font-medium text-foreground">当前告警</div>
                      <div className="space-y-2">
                        {monitor.alerts.map((alert) => (
                          <div
                            key={alert}
                            className="rounded-lg border border-warning/20 bg-background/80 px-3 py-2 text-xs leading-5 text-foreground"
                          >
                            {alert}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-success/20 bg-success/5 px-3 py-2 text-xs leading-5 text-success">
                      当前没有待处理的调度告警。
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm">运行历史</CardTitle>
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
                                {run.status}
                              </Badge>
                              <span className="text-xs text-muted-foreground">{run.trigger}</span>
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
                                查看协作视图
                              </Link>
                            </Button>
                          ) : null}
                          {run.status === "pending" || run.status === "running" ? (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={tickingRunId === run.id}
                              onClick={() => onTickRun(run.id)}
                            >
                              <Play className="mr-2 size-4" />
                              {tickingRunId === run.id ? "推进中..." : "推进一轮"}
                            </Button>
                          ) : null}
                        </div>

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
