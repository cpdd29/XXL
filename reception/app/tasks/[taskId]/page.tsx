"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { useCancelTask, useRetryTask, useTaskDetail, useTaskSteps } from "@/hooks/use-tasks"
import { toast } from "@/hooks/use-toast"
import type {
  BrainDispatchSummary,
  ManagerPacket,
  TaskExecutionTraceEntry,
  TaskPriority,
  TaskRouteDecision,
  TaskStatus,
  TaskStep,
} from "@/types"
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
  XCircle,
} from "lucide-react"
import { cn } from "@/lib/utils"

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
  const { data: task, isLoading, error } = useTaskDetail(taskId)
  const { data: stepsData, isLoading: stepsLoading } = useTaskSteps(taskId)
  const cancelTaskMutation = useCancelTask()
  const retryTaskMutation = useRetryTask()
  const steps = stepsData?.items ?? []
  const brainDispatchEntriesList = brainDispatchEntries(task?.brainDispatchSummary)

  if (isLoading) {
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
                  {stepsLoading ? "同步中..." : `${steps.length} steps`}
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
