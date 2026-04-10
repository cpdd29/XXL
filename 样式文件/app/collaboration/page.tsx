"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
  MarkerType,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import {
  useCollaborationOverview,
  type CollaborationRealtimeStatus,
} from "@/hooks/use-collaboration"
import type {
  CollaborationLog,
  CollaborationNode,
  CollaborationOverviewResponse,
  CollaborationTaskOption,
} from "@/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AggregateNode,
  AgentNode,
  ConditionNode,
  MergeNode,
  OutputNode,
  ParallelNode,
  ToolNode,
  TransformNode,
  TriggerNode,
} from "@/components/workflow/nodes"
import { cn } from "@/lib/utils"
import {
  Activity,
  Bot,
  GitBranch,
  RefreshCcw,
  Sparkles,
  TimerReset,
} from "lucide-react"

const nodeTypes: NodeTypes = {
  trigger: TriggerNode,
  agent: AgentNode,
  condition: ConditionNode,
  parallel: ParallelNode,
  merge: MergeNode,
  tool: ToolNode,
  transform: TransformNode,
  output: OutputNode,
  aggregate: AggregateNode,
}

const taskStatusConfig = {
  pending: { label: "排队中", className: "bg-warning/20 text-warning-foreground" },
  running: { label: "执行中", className: "bg-primary/20 text-primary" },
  completed: { label: "已完成", className: "bg-success/20 text-success" },
  failed: { label: "失败", className: "bg-destructive/20 text-destructive" },
  cancelled: { label: "已取消", className: "bg-muted text-muted-foreground" },
} as const

const priorityConfig = {
  high: { label: "高优先级", className: "bg-destructive/15 text-destructive" },
  medium: { label: "中优先级", className: "bg-warning/20 text-warning-foreground" },
  low: { label: "低优先级", className: "bg-muted text-muted-foreground" },
} as const

const logTypeConfig = {
  info: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/20 text-warning-foreground",
  error: "bg-destructive/15 text-destructive",
} as const

const realtimeStatusConfig: Record<
  CollaborationRealtimeStatus,
  { label: string; className: string }
> = {
  idle: { label: "等待连接", className: "bg-muted text-muted-foreground" },
  connecting: {
    label: "实时连接中",
    className: "bg-warning/20 text-warning-foreground",
  },
  connected: { label: "WebSocket 实时", className: "bg-success/15 text-success" },
  disconnected: { label: "轮询兜底", className: "bg-muted text-muted-foreground" },
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

function getAgentType(node: CollaborationNode) {
  if (node.agentType) return node.agentType
  if (node.type === "output") return "output"
  if (node.label.includes("安全")) return "security"
  if (node.label.includes("意图")) return "intent"
  if (node.label.includes("搜索")) return "search"
  if (node.label.includes("写作")) return "write"
  return "default"
}

function getNodeStateMap(data: CollaborationOverviewResponse) {
  return new Map(data.nodes.map((node) => [node.id, node] as const))
}

function buildFlowNodes(data: CollaborationOverviewResponse): Node[] {
  const nodeStateMap = getNodeStateMap(data)

  return data.workflow.nodes.map((node) => {
    const runtime = nodeStateMap.get(node.id)

    return {
      id: node.id,
      type: node.type,
      position: { x: node.x, y: node.y },
      data: {
        label: node.label,
        agentType: runtime ? getAgentType(runtime) : undefined,
        status: runtime?.status,
        tokens: runtime?.tokens,
      },
    }
  })
}

function buildFlowEdges(data: CollaborationOverviewResponse): Edge[] {
  return data.workflow.edges.map((edge) => {
    const isActive = data.activeEdges.includes(edge.id)
    const color = isActive
      ? edge.sourceHandle === "false"
        ? "oklch(0.68 0.21 30)"
        : "oklch(0.63 0.19 160)"
      : "oklch(0.32 0.02 260)"

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? undefined,
      animated: isActive,
      style: { stroke: color, strokeWidth: isActive ? 2.4 : 1.4 },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    }
  })
}

function formatDetailTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function MetricCard({
  title,
  value,
  description,
  icon,
}: {
  title: string
  value: string
  description: string
  icon: React.ReactNode
}) {
  return (
    <Card className="bg-card">
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div>
          <div className="text-xs text-muted-foreground">{title}</div>
          <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
          <div className="mt-1 text-xs text-muted-foreground">{description}</div>
        </div>
        <div className="rounded-xl bg-primary/10 p-2 text-primary">{icon}</div>
      </CardContent>
    </Card>
  )
}

function TaskOptionLabel({ task }: { task: CollaborationTaskOption }) {
  const statusLabel =
    taskStatusConfig[task.status as keyof typeof taskStatusConfig]?.label ?? task.status

  return (
    <span className="flex flex-col">
      <span className="font-medium">{task.title}</span>
      <span className="text-xs text-muted-foreground">
        {statusLabel} · {task.agent}
      </span>
    </span>
  )
}

function LogItem({ log }: { log: CollaborationLog }) {
  return (
    <div className="rounded-xl border border-border bg-secondary/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className={cn("text-[11px]", logTypeConfig[log.type])}>
            {log.type}
          </Badge>
          <span className="text-sm font-medium text-foreground">{log.agent}</span>
        </div>
        <span className="text-xs text-muted-foreground">{log.timestamp}</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{log.message}</p>
    </div>
  )
}

export default function CollaborationPage() {
  const router = useRouter()
  const [taskId, setTaskId] = useState<string | undefined>(() => {
    if (typeof window === "undefined") return undefined
    return new URLSearchParams(window.location.search).get("taskId") ?? undefined
  })
  const { data, error, isLoading, isFetching, refetch, realtimeStatus, isRealtimeActive } =
    useCollaborationOverview(taskId)

  useEffect(() => {
    if (!taskId && data?.session.taskId) {
      setTaskId(data.session.taskId)
    }
  }, [data?.session.taskId, taskId])

  const flowNodes = data ? buildFlowNodes(data) : []
  const flowEdges = data ? buildFlowEdges(data) : []
  const currentTaskValue = taskId ?? data?.session.taskId
  const taskStatus =
    data && taskStatusConfig[data.session.taskStatus as keyof typeof taskStatusConfig]
      ? taskStatusConfig[data.session.taskStatus as keyof typeof taskStatusConfig]
      : undefined
  const priority =
    data && priorityConfig[data.session.taskPriority as keyof typeof priorityConfig]
      ? priorityConfig[data.session.taskPriority as keyof typeof priorityConfig]
      : undefined
  const realtimeBadge = realtimeStatusConfig[realtimeStatus]

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="border-b border-border bg-card px-6 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Agent 协作可视化</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              按开发指南的协作编排思路，将任务流转、节点状态、Token 消耗和执行日志放在同一个实时视图里。
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={currentTaskValue}
              onValueChange={(value) => {
                setTaskId(value)
                router.replace(`/collaboration?taskId=${encodeURIComponent(value)}`)
              }}
            >
              <SelectTrigger className="w-[320px] bg-background">
                <SelectValue placeholder="选择一个任务查看协作轨迹" />
              </SelectTrigger>
              <SelectContent>
                {data?.tasks.map((task) => (
                  <SelectItem key={task.id} value={task.id}>
                    <TaskOptionLabel task={task} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetch()
              }}
              disabled={isFetching}
            >
              <RefreshCcw className={cn("mr-2 size-4", isFetching && "animate-spin")} />
              刷新
            </Button>

            <Badge variant="secondary" className={realtimeBadge.className}>
              {realtimeBadge.label}
            </Badge>
          </div>
        </div>
      </div>

      {error ? (
        <div className="px-6 py-4 text-sm text-destructive">
          协作视图加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      {isLoading && !data ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
          正在加载协作快照...
        </div>
      ) : null}

      {data ? (
        <div className="flex-1 overflow-auto p-6">
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
            <MetricCard
              title="执行进度"
              value={`${data.session.progressPercent}%`}
              description={`${data.session.completedSteps}/${data.session.totalSteps} 个节点已推进`}
              icon={<Activity className="size-5" />}
            />
            <MetricCard
              title="当前阶段"
              value={data.session.currentStage}
              description={`工作流：${data.session.workflowName}`}
              icon={<GitBranch className="size-5" />}
            />
            <MetricCard
              title="活跃 Agent"
              value={data.session.activeAgentCount.toString()}
              description="包含运行中与等待中的执行节点"
              icon={<Bot className="size-5" />}
            />
            <MetricCard
              title="Token 消耗"
              value={data.session.totalTokens.toLocaleString()}
              description={`任务开始于 ${data.session.startedAt}`}
              icon={<Sparkles className="size-5" />}
            />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <Card className="overflow-hidden bg-card">
              <CardHeader className="border-b border-border pb-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <CardTitle className="text-lg">{data.session.taskTitle}</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      关联工作流：{data.session.workflowName} · {data.session.workflowId}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {taskStatus ? (
                      <Badge variant="secondary" className={taskStatus.className}>
                        {taskStatus.label}
                      </Badge>
                    ) : null}
                    {data.session.failureStage ? (
                      <Badge variant="secondary" className="bg-destructive/15 text-destructive">
                        {failureStageConfig[data.session.failureStage] ?? data.session.failureStage}
                      </Badge>
                    ) : null}
                    {data.session.deliveryStatus ? (
                      <Badge
                        variant="secondary"
                        className={cn(
                          data.session.deliveryStatus === "failed" && "bg-destructive/15 text-destructive",
                          data.session.deliveryStatus === "sent" && "bg-success/15 text-success",
                          data.session.deliveryStatus === "skipped" && "bg-warning/20 text-warning-foreground",
                        )}
                      >
                        {deliveryStatusConfig[data.session.deliveryStatus] ?? data.session.deliveryStatus}
                      </Badge>
                    ) : null}
                    {priority ? (
                      <Badge variant="secondary" className={priority.className}>
                        {priority.label}
                      </Badge>
                    ) : null}
                    <Badge variant="outline" className="border-border text-muted-foreground">
                      {data.session.completedAt
                        ? `完成于 ${data.session.completedAt}`
                        : isRealtimeActive
                          ? "实时同步中"
                          : "快照模式"}
                    </Badge>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="h-[720px] p-0">
                <ReactFlow
                  nodes={flowNodes}
                  edges={flowEdges}
                  nodeTypes={nodeTypes}
                  fitView
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  proOptions={{ hideAttribution: true }}
                  className="bg-background"
                >
                  <Panel position="top-left" className="m-4">
                    <Card className="w-72 bg-card/90 shadow-xl backdrop-blur">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">协作快照</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <Progress value={data.session.progressPercent} className="h-2" />
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>当前阶段</span>
                          <span>{data.session.currentStage}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>激活边数</span>
                          <span>{data.activeEdges.length}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>开始时间</span>
                          <span>{data.session.startedAt}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>同步方式</span>
                          <span>{realtimeBadge.label}</span>
                        </div>
                      </CardContent>
                    </Card>
                  </Panel>

                  <Background color="oklch(0.28 0.01 260)" gap={20} />
                  <Controls className="rounded-lg border border-border bg-card [&>button]:border-border [&>button]:bg-card [&>button]:text-foreground [&>button:hover]:bg-secondary" />
                  <MiniMap
                    className="rounded-lg border border-border !bg-card"
                    nodeColor="oklch(0.65 0.2 265)"
                    maskColor="oklch(0.12 0.01 260 / 0.8)"
                  />
                </ReactFlow>
              </CardContent>
            </Card>

            <div className="space-y-4">
              <Card className="bg-card">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">运行摘要</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between rounded-xl bg-secondary/40 p-3">
                    <span className="text-sm text-muted-foreground">任务主 Agent</span>
                    <span className="text-sm font-medium text-foreground">
                      {data.tasks.find((task) => task.id === data.session.taskId)?.agent ?? "--"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-secondary/40 p-3">
                    <span className="text-sm text-muted-foreground">总节点数</span>
                    <span className="text-sm font-medium text-foreground">
                      {data.session.totalSteps}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-secondary/40 p-3">
                    <span className="text-sm text-muted-foreground">完成节点</span>
                    <span className="text-sm font-medium text-foreground">
                      {data.session.completedSteps}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-secondary/40 p-3">
                    <span className="text-sm text-muted-foreground">最后刷新</span>
                    <span className="text-sm font-medium text-foreground">
                      {isFetching ? "同步中..." : isRealtimeActive ? "实时推送" : "15s 校准"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-secondary/40 p-3">
                    <span className="text-sm text-muted-foreground">调度状态</span>
                    <span className="text-sm font-medium text-foreground">
                      {data.session.dispatchState ?? "--"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-secondary/40 p-3">
                    <span className="text-sm text-muted-foreground">回传状态</span>
                    <span className="text-sm font-medium text-foreground">
                      {data.session.deliveryStatus
                        ? deliveryStatusConfig[data.session.deliveryStatus] ?? data.session.deliveryStatus
                        : "--"}
                    </span>
                  </div>
                  {data.session.statusReason ? (
                    <div className="rounded-xl bg-secondary/40 p-3 text-xs leading-5 text-muted-foreground">
                      {data.session.statusReason}
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              <Card className="bg-card">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">节点状态</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {data.nodes.map((node) => (
                    <div
                      key={node.id}
                      className="rounded-xl border border-border bg-secondary/20 p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-foreground">{node.label}</span>
                        <Badge
                          variant="secondary"
                          className={cn(
                            "text-[11px]",
                            node.status === "completed" && "bg-success/15 text-success",
                            node.status === "running" && "bg-primary/15 text-primary",
                            node.status === "waiting" && "bg-warning/20 text-warning-foreground",
                            node.status === "error" && "bg-destructive/15 text-destructive",
                            node.status === "idle" && "bg-muted text-muted-foreground",
                          )}
                        >
                          {node.status}
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        {node.message || "暂无执行说明"}
                      </p>
                      {node.errorCount > 0 ? (
                        <div className="mt-3 space-y-2 rounded-lg border border-destructive/20 bg-background/80 p-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-medium text-foreground">
                              异常归档
                            </span>
                            <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                              {node.errorCount} 条
                            </Badge>
                          </div>
                          {node.errorHistory.slice(0, 3).map((issue) => (
                            <div
                              key={issue.id}
                              className="rounded-md border border-border/70 bg-secondary/20 p-2"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <Badge
                                  variant="secondary"
                                  className={cn(
                                    "text-[11px]",
                                    issue.severity === "warning"
                                      ? "bg-warning/20 text-warning-foreground"
                                      : "bg-destructive/15 text-destructive",
                                  )}
                                >
                                  {issue.severity}
                                </Badge>
                                <span className="text-[11px] text-muted-foreground">
                                  {formatDetailTimestamp(issue.timestamp)}
                                </span>
                              </div>
                              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                {issue.message}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="flex min-h-[360px] flex-col bg-card">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">执行日志</CardTitle>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <TimerReset className="size-3.5" />
                      {isFetching ? "同步中" : realtimeBadge.label}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="min-h-0 flex-1 p-0">
                  <ScrollArea className="h-[360px] px-4 pb-4">
                    <div className="space-y-3 pb-4">
                      {data.logs.map((log) => (
                        <LogItem key={log.id} log={log} />
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
