"use client"

import type { ReactNode } from "react"
import { useMemo } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDashboardStats } from "@/hooks/use-dashboard"
import { useExternalCapabilityGovernanceOverview } from "@/hooks/use-external-connections"
import { useTasks } from "@/hooks/use-tasks"
import { useWorkflowMonitor, useWorkflows } from "@/hooks/use-workflows"
import { ArrowRight, Clock3, Headphones, Shield, Wrench } from "lucide-react"

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function clipText(value?: string | null, limit = 48) {
  const normalized = String(value || "").trim()
  if (!normalized) return "--"
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit)}...`
}

function toTimestamp(value?: string | null) {
  const timestamp = Date.parse(String(value || ""))
  return Number.isFinite(timestamp) ? timestamp : 0
}

function formatExternalStatus(status?: string | null, circuitState?: string | null) {
  if (String(circuitState || "").trim().toLowerCase() === "open") return "熔断打开"
  const normalized = String(status || "").trim().toLowerCase()
  if (["healthy", "online", "idle"].includes(normalized)) return "正常"
  if (normalized === "degraded") return "降级"
  if (normalized === "offline") return "离线"
  if (normalized === "unknown") return "未知"
  return status || "--"
}

function externalRiskScore(item: {
  circuitState?: string | null
  routable?: boolean
  status?: string | null
  deprecated?: boolean
}) {
  let score = 0
  if (String(item.circuitState || "").trim().toLowerCase() === "open") score += 100
  if (!item.routable) score += 60
  const normalizedStatus = String(item.status || "").trim().toLowerCase()
  if (normalizedStatus === "offline" || normalizedStatus === "unknown") score += 50
  if (normalizedStatus === "degraded") score += 30
  if (item.deprecated) score += 5
  return score
}

const healthTone = {
  healthy: "bg-success/10 text-success",
  degraded: "bg-warning/10 text-warning-foreground",
  critical: "bg-destructive/10 text-destructive",
} as const

const healthLabel = {
  healthy: "正常",
  degraded: "关注",
  critical: "高风险",
} as const

function MetricCard({
  title,
  value,
  hint,
  toneClass,
  icon,
  href,
}: {
  title: string
  value: string | number
  hint: string
  toneClass: string
  icon: ReactNode
  href: string
}) {
  return (
    <Link href={href} className="block h-full">
      <Card className="h-full border-border bg-card transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">{title}</div>
              <div className="mt-2 truncate text-2xl font-semibold text-foreground">{value}</div>
              <div className="mt-2 text-xs leading-5 text-muted-foreground">{hint}</div>
              <div className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-primary">
                查看模块
                <ArrowRight className="size-3.5" />
              </div>
            </div>
            <div className={`rounded-xl p-2 ${toneClass}`}>{icon}</div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

function SectionEmpty({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
      {text}
    </div>
  )
}

function SignalCard({
  title,
  status,
  value,
  unit,
  summary,
}: {
  title: string
  status: keyof typeof healthTone
  value: number
  unit: string
  summary: string
}) {
  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium text-foreground">{title}</div>
        <Badge variant="secondary" className={healthTone[status]}>
          {healthLabel[status]}
        </Badge>
      </div>
      <div className="mt-2 text-xl font-semibold text-foreground">
        {value.toFixed(1)}
        {unit}
      </div>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">{summary}</div>
    </div>
  )
}

function SummaryPill({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  const compactValue = typeof value === "string" && value.length > 14
  return (
    <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={compactValue ? "mt-1 text-sm font-medium leading-6 text-foreground" : "mt-1 text-xl font-semibold text-foreground"}>
        {value}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const dashboardQuery = useDashboardStats()
  const runningTasksQuery = useTasks({ status: "running" })
  const workflowsQuery = useWorkflows()
  const externalGovernanceQuery = useExternalCapabilityGovernanceOverview(8)

  const data = dashboardQuery.data
  const managerQueue = data?.managerQueue ?? []
  const replyQueue = data?.replyQueue ?? []
  const healthSignals = data?.healthSignals ?? []
  const tentacleMetrics = data?.tentacleMetrics ?? []
  const workflowCandidates = workflowsQuery.data?.items ?? []

  const primaryWorkflow = useMemo(
    () =>
      workflowCandidates.find((item) => ["running", "active"].includes(String(item.status).toLowerCase())) ??
      workflowCandidates[0],
    [workflowCandidates],
  )

  const workflowMonitorQuery = useWorkflowMonitor(primaryWorkflow?.id)
  const workflowMonitor = workflowMonitorQuery.data
  const workflowRuns = workflowMonitor?.items ?? []

  const runningTasks = useMemo(
    () =>
      [...(runningTasksQuery.data?.items ?? [])].sort(
        (left, right) => toTimestamp(right.createdAt) - toTimestamp(left.createdAt),
      ),
    [runningTasksQuery.data?.items],
  )

  const currentTask = useMemo(() => {
    if (runningTasks.length === 0) return undefined
    if (!primaryWorkflow) return runningTasks[0]
    return (
      runningTasks.find(
        (task) =>
          task.workflowId === primaryWorkflow.id ||
          task.routeDecision?.workflowId === primaryWorkflow.id ||
          task.routeDecision?.workflowName === primaryWorkflow.name ||
          task.brainDispatchSummary?.workflowName === primaryWorkflow.name,
      ) ?? runningTasks[0]
    )
  }, [primaryWorkflow, runningTasks])

  const activeRun = useMemo(
    () =>
      workflowRuns.find((item) =>
        ["running", "pending"].includes(item.status) ||
        ["running", "claimed", "queued", "scheduled", "retry_waiting", "claimed_stale"].includes(
          item.monitor?.monitorState ?? "",
        ),
      ) ?? workflowRuns[0],
    [workflowRuns],
  )

  const currentWorkflowName =
    currentTask?.routeDecision?.workflowName ||
    currentTask?.brainDispatchSummary?.workflowName ||
    activeRun?.workflowName ||
    primaryWorkflow?.name ||
    "当前暂无命中的工作流"

  const humanActionCount = managerQueue.length + replyQueue.length
  const brainHealth = data?.slaSummary.healthStatus ?? "healthy"
  const successRate = data?.slaSummary.successRate?.toFixed(1) ?? "0.0"
  const failureRate = data?.slaSummary.failureRate?.toFixed(1) ?? "0.0"

  const externalItems = externalGovernanceQuery.data?.items ?? []
  const externalSummary = externalGovernanceQuery.data?.summary
  const externalRiskItems = useMemo(
    () =>
      [...externalItems]
        .sort((left, right) => externalRiskScore(right) - externalRiskScore(left))
        .slice(0, 4),
    [externalItems],
  )

  const externalProblemCount = useMemo(
    () => externalItems.filter((item) => externalRiskScore(item) > 0).length,
    [externalItems],
  )

  const highlightedTentacles = useMemo(
    () =>
      [...tentacleMetrics]
        .sort((left, right) => {
          if (left.successRate !== right.successRate) return left.successRate - right.successRate
          return right.calls - left.calls
        })
        .slice(0, 4),
    [tentacleMetrics],
  )

  const dashboardError = dashboardQuery.error
  const externalError = externalGovernanceQuery.error

  return (
    <div className="space-y-6 p-6">
      {dashboardError ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            主脑总控数据加载失败：{dashboardError instanceof Error ? dashboardError.message : "未知错误"}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="执行成功率"
          value={`${successRate}%`}
          hint={`失败率 ${failureRate}% · 点击查看工作流`}
          toneClass={healthTone[brainHealth]}
          icon={<Shield className="size-4" />}
          href="/workflow"
        />
        <MetricCard
          title="执行中任务"
          value={runningTasks.length}
          hint={currentTask ? `当前主线：${clipText(currentWorkflowName, 18)}` : "点击查看执行任务模块"}
          toneClass="bg-primary/10 text-primary"
          icon={<Clock3 className="size-4" />}
          href="/tasks"
        />
        <MetricCard
          title="待人工处理"
          value={humanActionCount}
          hint={`待确认 ${managerQueue.length} 项 · 待回复 ${replyQueue.length} 项`}
          toneClass="bg-warning/10 text-warning-foreground"
          icon={<Headphones className="size-4" />}
          href="/reception"
        />
        <MetricCard
          title="skill/mcp 接入"
          value={externalSummary?.routable ?? 0}
          hint={`可调度 ${externalSummary?.routable ?? 0} / ${externalSummary?.totalFamilies ?? externalItems.length}`}
          toneClass={externalProblemCount > 0 ? "bg-warning/10 text-warning-foreground" : "bg-success/10 text-success"}
          icon={<Wrench className="size-4" />}
          href="/tools"
        />
      </div>

      <Card className="bg-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-medium">主脑健康信号</CardTitle>
              <div className="mt-1 text-sm text-muted-foreground">
                直接看主脑整体运行质量和当前异常趋势
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {healthSignals.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {healthSignals.map((signal) => (
                <SignalCard
                  key={signal.key}
                  title={signal.label}
                  status={signal.status}
                  value={signal.value}
                  unit={signal.unit}
                  summary={signal.summary}
                />
              ))}
            </div>
          ) : (
            <SectionEmpty text="当前没有新的健康信号可展示。" />
          )}
        </CardContent>
      </Card>

      <Card className="bg-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-medium">skill/mcp 接入工作状态</CardTitle>
              <div className="mt-1 text-sm text-muted-foreground">
                先看外接能力是否可调度，再看谁降级、谁离线、谁熔断
              </div>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/tools">
                查看接入详情
                <ArrowRight className="ml-2 size-4" />
              </Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {externalError ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              外部触手状态加载失败：{externalError instanceof Error ? externalError.message : "未知错误"}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryPill label="触手家族" value={externalSummary?.totalFamilies ?? externalItems.length} />
            <SummaryPill label="可调度" value={externalSummary?.routable ?? 0} />
            <SummaryPill label="熔断打开" value={externalSummary?.openCircuits ?? 0} />
            <SummaryPill label="离线/未知" value={externalSummary?.offline ?? 0} />
          </div>

          {externalRiskItems.length > 0 ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {externalRiskItems.map((item) => (
                <div key={`${item.capabilityType}-${item.family}`} className="rounded-xl border border-border bg-secondary/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-foreground">{item.name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{item.family}</div>
                    </div>
                    <Badge
                      variant="secondary"
                      className={
                        externalRiskScore(item) > 60
                          ? "bg-destructive/10 text-destructive"
                          : "bg-warning/10 text-warning-foreground"
                      }
                    >
                      {formatExternalStatus(item.status, item.circuitState)}
                    </Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <Badge variant="secondary">可调度 {item.routable ? "是" : "否"}</Badge>
                    <Badge variant="secondary">当前版本 {item.currentVersion || "-"}</Badge>
                    <Badge variant="secondary">心跳 {formatTimestamp(item.lastHeartbeatAt)}</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : highlightedTentacles.length > 0 ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {highlightedTentacles.map((item) => (
                <div key={item.agentId ?? item.name} className="rounded-xl border border-border bg-secondary/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-foreground">{item.name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{item.type}</div>
                    </div>
                    <Badge
                      variant="secondary"
                      className={
                        item.successRate >= 95
                          ? "bg-success/10 text-success"
                          : "bg-warning/10 text-warning-foreground"
                      }
                    >
                      成功率 {item.successRate.toFixed(1)}%
                    </Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <Badge variant="secondary">调用 {item.calls}</Badge>
                    <Badge variant="secondary">成功 {item.successCalls}</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <SectionEmpty text="当前还没有可展示的外部触手运行记录。" />
          )}
        </CardContent>
      </Card>

      {(dashboardQuery.isLoading || runningTasksQuery.isLoading || workflowsQuery.isLoading) && !data ? (
        <div className="text-sm text-muted-foreground">正在加载主脑运行状态...</div>
      ) : null}
    </div>
  )
}
