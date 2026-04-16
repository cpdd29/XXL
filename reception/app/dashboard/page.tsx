"use client"

import Link from "next/link"
import { AgentStatusGrid } from "@/components/dashboard/agent-status-grid"
import { RealtimeLog } from "@/components/dashboard/realtime-log"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useDashboardStats } from "@/hooks/use-dashboard"
import {
  runtimeQueueRiskState,
  summarizeRuntimeAlerts,
  summarizeRuntimeQueues,
} from "@/lib/runtime-monitor"
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Clock3,
  Headphones,
  Layers3,
  ListTodo,
  Shield,
  Wrench,
} from "lucide-react"

function formatDurationMs(durationMs?: number | null) {
  if (!durationMs || durationMs <= 0) return "--"
  if (durationMs >= 60_000) return `${(durationMs / 60_000).toFixed(1)}m`
  if (durationMs >= 1_000) return `${(durationMs / 1_000).toFixed(1)}s`
  return `${durationMs}ms`
}

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function clipText(value?: string | null, limit = 56) {
  const normalized = String(value || "").trim()
  if (!normalized) return "--"
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit)}...`
}

const healthTone = {
  healthy: "bg-success/10 text-success",
  degraded: "bg-warning/10 text-warning-foreground",
  critical: "bg-destructive/10 text-destructive",
} as const

const healthLabel = {
  healthy: "健康",
  degraded: "关注",
  critical: "高风险",
} as const

const queueTone = {
  healthy: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning-foreground",
  critical: "bg-destructive/10 text-destructive",
} as const

const queueToneLabel = {
  healthy: "稳定",
  warning: "关注",
  critical: "高风险",
} as const

const alertTone = {
  critical: "bg-destructive/10 text-destructive",
  warning: "bg-warning/10 text-warning-foreground",
} as const

function OverviewMetricCard({
  title,
  value,
  hint,
  toneClass,
  icon,
}: {
  title: string
  value: string | number
  hint: string
  toneClass: string
  icon: React.ReactNode
}) {
  return (
    <Card className="bg-card">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs text-muted-foreground">{title}</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
            <div className="mt-2 text-xs leading-5 text-muted-foreground">{hint}</div>
          </div>
          <div className={`rounded-xl p-2 ${toneClass}`}>{icon}</div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { data, isLoading, error } = useDashboardStats()

  const chartData = data?.chartData ?? []
  const runtime = data?.runtime
  const runtimeQueues = runtime?.queues ?? []
  const runtimeAlerts = runtime?.recentAlerts ?? []
  const preparedAlerts = data?.preparedAlerts ?? []
  const managerQueue = data?.managerQueue ?? []
  const replyQueue = data?.replyQueue ?? []
  const healthSignals = data?.healthSignals ?? []
  const costDistribution = data?.costDistribution ?? []
  const tentacleMetrics = data?.tentacleMetrics ?? []
  const failureBreakdown = data?.failureBreakdown ?? []
  const brainBreakdown = data?.brainBreakdown ?? []

  const runtimeQueueSummary = summarizeRuntimeQueues(runtimeQueues)
  const runtimeAlertSummary = summarizeRuntimeAlerts(runtimeAlerts)

  const overviewHealth = data?.slaSummary.healthStatus ?? "healthy"
  const managerFocus = managerQueue.slice(0, 4)
  const replyFocus = replyQueue.slice(0, 4)
  const riskFeed = [
    ...preparedAlerts.map((item) => ({
      key: `prepared:${item.key}`,
      title: item.title,
      detail: item.detail,
      severity: item.severity,
      source: item.source,
      href: item.href,
      timestamp: "",
    })),
    ...runtimeAlerts.map((item) => ({
      key: `runtime:${item.key}`,
      title: item.title,
      detail: item.detail,
      severity: item.severity,
      source: item.source,
      href: item.href,
      timestamp: item.updatedAt ?? "",
    })),
  ]
    .sort((left, right) => {
      const severityDiff =
        (left.severity === "critical" ? 2 : 1) - (right.severity === "critical" ? 2 : 1)
      if (severityDiff !== 0) return -severityDiff
      return Date.parse(right.timestamp || "") - Date.parse(left.timestamp || "")
    })
    .slice(0, 6)

  const priorityRuntimeQueues = [...runtimeQueues]
    .sort((left, right) => {
      const riskScore = { critical: 3, warning: 2, healthy: 1 } as const
      const riskDiff =
        riskScore[runtimeQueueRiskState(right)] - riskScore[runtimeQueueRiskState(left)]
      if (riskDiff !== 0) return riskDiff
      return (right.depth ?? 0) - (left.depth ?? 0)
    })
    .slice(0, 6)

  const priorityRuntimeAlerts = [...runtimeAlerts]
    .sort((left, right) => {
      const severityDiff =
        (right.severity === "critical" ? 2 : 1) - (left.severity === "critical" ? 2 : 1)
      if (severityDiff !== 0) return severityDiff
      return Date.parse(right.updatedAt ?? "") - Date.parse(left.updatedAt ?? "")
    })
    .slice(0, 6)

  const highlightedTentacles = [...tentacleMetrics]
    .sort((left, right) => {
      if (right.calls !== left.calls) return right.calls - left.calls
      return left.successRate - right.successRate
    })
    .slice(0, 6)

  const highlightedCosts = [...costDistribution]
    .sort((left, right) => right.sharePercent - left.sharePercent)
    .slice(0, 5)

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">总览</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            先看系统状态、当前待办和风险提醒；更深的调度、成本和能力细节放到下方分页签。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/reception">进入待办中心</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/tasks">查看任务中心</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/security">打开风险中心</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            总览数据加载失败：{error instanceof Error ? error.message : "未知错误"}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <OverviewMetricCard
          title="系统健康"
          value={healthLabel[overviewHealth]}
          hint={`成功率 ${data?.slaSummary.successRate?.toFixed(1) ?? "0.0"}% · 高风险率 ${data?.slaSummary.securityRiskRate?.toFixed(1) ?? "0.0"}%`}
          toneClass={healthTone[overviewHealth]}
          icon={<Shield className="size-4" />}
        />
        <OverviewMetricCard
          title="经理待办"
          value={managerQueue.length}
          hint={managerQueue.length > 0 ? "有任务等待项目经理继续分发或澄清。" : "当前没有需要项目经理优先处理的事项。"}
          toneClass="bg-primary/10 text-primary"
          icon={<ListTodo className="size-4" />}
        />
        <OverviewMetricCard
          title="待用户回复"
          value={replyQueue.length}
          hint={replyQueue.length > 0 ? "有会话需要继续对话推进。" : "当前没有待用户回复的会话。"}
          toneClass="bg-warning/10 text-warning-foreground"
          icon={<Headphones className="size-4" />}
        />
        <OverviewMetricCard
          title="运行风险"
          value={runtimeAlertSummary.critical + runtimeQueueSummary.critical}
          hint={`Critical 告警 ${runtimeAlertSummary.critical} 条 · 高风险队列 ${runtimeQueueSummary.critical} 个`}
          toneClass="bg-destructive/10 text-destructive"
          icon={<AlertTriangle className="size-4" />}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="bg-card">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base font-medium">现在最该处理</CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link href="/tasks">
                  任务中心
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {managerFocus.map((item) => (
              <Link
                key={item.taskId}
                href={`/tasks/${encodeURIComponent(item.taskId)}`}
                className="block rounded-xl border border-border bg-secondary/20 p-4 transition-colors hover:bg-secondary/35"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-foreground">{item.title}</div>
                  <Badge variant="secondary" className="text-xs">
                    {item.status}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.managerAction ? (
                    <Badge variant="secondary" className="bg-primary/10 text-xs text-primary">
                      pm: {item.managerAction}
                    </Badge>
                  ) : null}
                  {item.nextOwner ? <Badge variant="secondary" className="text-xs">next: {item.nextOwner}</Badge> : null}
                </div>
                <div className="mt-3 text-xs text-muted-foreground">
                  {clipText(item.clarifyQuestion || item.currentStage || "等待进一步处理")}
                </div>
              </Link>
            ))}
            {!managerFocus.length ? (
              <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                当前没有需要项目经理优先处理的任务。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base font-medium">待用户回复</CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link href="/reception">
                  待办中心
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {replyFocus.map((item) => (
              <Link
                key={item.taskId}
                href={`/reception?taskId=${encodeURIComponent(item.taskId)}`}
                className="block rounded-xl border border-border bg-secondary/20 p-4 transition-colors hover:bg-secondary/35"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-foreground">{item.title}</div>
                  <Badge variant="secondary" className="text-xs">
                    {item.channel?.trim() || "unknown"}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.userLabel ? <Badge variant="secondary" className="text-xs">user: {item.userLabel}</Badge> : null}
                  {item.nextOwner ? (
                    <Badge variant="secondary" className="bg-primary/10 text-xs text-primary">
                      next: {item.nextOwner}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-3 text-xs text-muted-foreground">
                  {clipText(item.clarifyQuestion || item.currentStage || "等待继续对话")}
                </div>
              </Link>
            ))}
            {!replyFocus.length ? (
              <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                当前没有待用户回复的会话。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base font-medium">风险提醒</CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link href="/security/alerts">
                  查看全部
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {riskFeed.map((item) => (
              <div key={item.key} className="rounded-xl border border-border bg-secondary/20 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium text-foreground">{item.title}</div>
                  <Badge variant="secondary" className={alertTone[item.severity as keyof typeof alertTone] ?? alertTone.warning}>
                    {item.severity}
                  </Badge>
                </div>
                <div className="mt-2 text-xs leading-5 text-muted-foreground">{clipText(item.detail, 88)}</div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className="text-xs">
                    {item.source}
                  </Badge>
                  {item.timestamp ? <Badge variant="secondary" className="text-xs">{formatTimestamp(item.timestamp)}</Badge> : null}
                  {item.href ? (
                    <Link
                      href={item.href}
                      className="rounded-md border border-border px-3 py-1 text-xs text-foreground transition-colors hover:bg-background"
                    >
                      查看
                    </Link>
                  ) : null}
                </div>
              </div>
            ))}
            {!riskFeed.length ? (
              <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                当前没有需要升级处理的风险提醒。
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="runtime" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3 lg:w-[420px]">
          <TabsTrigger value="runtime">运行状态</TabsTrigger>
          <TabsTrigger value="trend">趋势与成本</TabsTrigger>
          <TabsTrigger value="capabilities">能力状态</TabsTrigger>
        </TabsList>

        <TabsContent value="runtime" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <OverviewMetricCard
              title="总队列深度"
              value={runtime?.totalQueueDepth ?? 0}
              hint="当前所有调度队列中的累计任务量。"
              toneClass="bg-primary/10 text-primary"
              icon={<Layers3 className="size-4" />}
            />
            <OverviewMetricCard
              title="活跃 Lease"
              value={
                (runtime?.activeDispatchLeases ?? 0) +
                (runtime?.activeWorkflowExecutionLeases ?? 0) +
                (runtime?.activeAgentExecutionLeases ?? 0)
              }
              hint="正在被 dispatcher / worker 持有的 claim 数。"
              toneClass="bg-primary/10 text-primary"
              icon={<Clock3 className="size-4" />}
            />
            <OverviewMetricCard
              title="过期 Claim"
              value={runtime?.staleClaims ?? 0}
              hint="需要 reclaim 的过期调度占用。"
              toneClass={queueTone.warning}
              icon={<AlertTriangle className="size-4" />}
            />
            <OverviewMetricCard
              title="死信 / 重试"
              value={`${runtime?.deadLetters ?? 0} / ${runtime?.retryScheduled ?? 0}`}
              hint="死信堆积和重试积压是调度关注重点。"
              toneClass={queueTone.critical}
              icon={<AlertTriangle className="size-4" />}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">重点队列</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary" className="text-xs">
                    非零队列 {runtimeQueueSummary.nonZero}
                  </Badge>
                  <Badge variant="secondary" className={queueTone.critical}>
                    高风险 {runtimeQueueSummary.critical}
                  </Badge>
                  <Badge variant="secondary" className={queueTone.warning}>
                    重试/Lease {runtimeQueueSummary.retryHotspots + runtimeQueueSummary.leaseHotspots}
                  </Badge>
                  <Badge variant="secondary" className="text-xs">
                    死信 {runtimeQueueSummary.deadLetterHotspots}
                  </Badge>
                </div>

                {priorityRuntimeQueues.map((queue) => {
                  const tone = runtimeQueueRiskState(queue)
                  return (
                    <div key={queue.key} className="rounded-xl border border-border bg-secondary/20 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="font-medium text-foreground">{queue.label}</div>
                          <div className="mt-1 text-[11px] text-muted-foreground">{queue.key}</div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="secondary" className={queueTone[tone]}>
                            {queueToneLabel[tone]}
                          </Badge>
                          <Badge variant="secondary">{queue.depth}</Badge>
                        </div>
                      </div>
                      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                        <div>Ready {queue.ready}</div>
                        <div>Delay {queue.delayed}</div>
                        <div>Lease {queue.activeLeases}</div>
                        <div>Stale {queue.staleClaims}</div>
                        <div>Retry {queue.retryScheduled}</div>
                        <div>Dead {queue.deadLetters}</div>
                      </div>
                    </div>
                  )
                })}

                {!priorityRuntimeQueues.length ? (
                  <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                    当前没有可用的调度快照。
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">最近运行告警</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary" className={alertTone.critical}>
                    Critical {runtimeAlertSummary.critical}
                  </Badge>
                  <Badge variant="secondary" className={alertTone.warning}>
                    Warning {runtimeAlertSummary.warning}
                  </Badge>
                  <Badge variant="secondary" className="text-xs">
                    来源 {runtimeAlertSummary.distinctSources}
                  </Badge>
                </div>

                {priorityRuntimeAlerts.map((alert) => (
                  <div key={alert.key} className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="font-medium text-foreground">{alert.title}</div>
                      <Badge variant="secondary" className={alertTone[alert.severity]}>
                        {alert.severity}
                      </Badge>
                    </div>
                    <div className="mt-2 text-xs leading-5 text-muted-foreground">{clipText(alert.detail, 96)}</div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className="text-xs">
                        {alert.source}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        {formatTimestamp(alert.updatedAt)}
                      </Badge>
                      {alert.href ? (
                        <Link
                          href={alert.href}
                          className="rounded-md border border-border px-3 py-1 text-xs text-foreground transition-colors hover:bg-background"
                        >
                          查看
                        </Link>
                      ) : null}
                    </div>
                  </div>
                ))}

                {!priorityRuntimeAlerts.length ? (
                  <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                    当前没有新的 retry / dead-letter / reclaim 告警。
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">主脑分发摘要</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  {brainBreakdown.map((item) => (
                    <div key={item.key} className="rounded-xl border border-border bg-secondary/20 px-4 py-3">
                      <div className="text-xs text-muted-foreground">{item.label}</div>
                      <div className="mt-2 text-2xl font-semibold text-foreground">{item.count}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{item.hint ?? "--"}</div>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-3">
                  {failureBreakdown.map((item) => (
                    <div key={item.stage} className="min-w-[140px] rounded-xl border border-border bg-secondary/20 px-4 py-3">
                      <div className="text-xs text-muted-foreground">{item.label}</div>
                      <div className="mt-2 flex items-center gap-2">
                        <span className="text-2xl font-semibold text-foreground">{item.count}</span>
                        <Badge variant="secondary" className="bg-secondary text-muted-foreground">
                          {item.stage}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <RealtimeLog initialLogs={data?.realtimeLogs ?? []} />
          </div>
        </TabsContent>

        <TabsContent value="trend" className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">请求量趋势 (24h)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[250px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="colorRequests" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="oklch(0.65 0.2 265)" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="oklch(0.65 0.2 265)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="time" stroke="oklch(0.65 0 0)" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis stroke="oklch(0.65 0 0)" fontSize={12} tickLine={false} axisLine={false} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "oklch(0.16 0.01 260)",
                          border: "1px solid oklch(0.28 0.01 260)",
                          borderRadius: "8px",
                          color: "oklch(0.98 0 0)",
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="requests"
                        stroke="oklch(0.65 0.2 265)"
                        strokeWidth={2}
                        fill="url(#colorRequests)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">Token 消耗趋势 (24h)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[250px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="oklch(0.55 0.22 160)" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="oklch(0.55 0.22 160)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="time" stroke="oklch(0.65 0 0)" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis
                        stroke="oklch(0.65 0 0)"
                        fontSize={12}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(value) => `${Math.round(value / 1000)}k`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "oklch(0.16 0.01 260)",
                          border: "1px solid oklch(0.28 0.01 260)",
                          borderRadius: "8px",
                          color: "oklch(0.98 0 0)",
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="tokens"
                        stroke="oklch(0.55 0.22 160)"
                        strokeWidth={2}
                        fill="url(#colorTokens)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">成本概况</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="text-xs text-muted-foreground">Run 数</div>
                    <div className="mt-2 text-2xl font-semibold text-foreground">{data?.costSummary.runCount ?? 0}</div>
                  </div>
                  <div className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="text-xs text-muted-foreground">累计 Token</div>
                    <div className="mt-2 text-2xl font-semibold text-foreground">{data?.costSummary.totalTokens ?? 0}</div>
                  </div>
                  <div className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="text-xs text-muted-foreground">平均耗时</div>
                    <div className="mt-2 text-2xl font-semibold text-foreground">
                      {formatDurationMs(data?.costSummary.avgDurationMs)}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      总耗时 {formatDurationMs(data?.costSummary.totalDurationMs)}
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  {highlightedCosts.map((item) => (
                    <div key={item.label} className="rounded-xl border border-border bg-secondary/20 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-foreground">{item.label}</div>
                        <Badge variant="secondary" className="text-xs">
                          {item.sharePercent.toFixed(1)}%
                        </Badge>
                      </div>
                      <div className="mt-3 h-2 rounded-full bg-secondary">
                        <div
                          className="h-2 rounded-full bg-primary"
                          style={{ width: `${Math.min(Math.max(item.sharePercent, 0), 100)}%` }}
                        />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>{item.calls} 次调用</span>
                        <span>{item.tokens} tokens</span>
                        <span>{formatDurationMs(item.durationMs)}</span>
                      </div>
                    </div>
                  ))}

                  {!highlightedCosts.length ? (
                    <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                      当前还没有可展示的成本分布数据。
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">健康信号</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {healthSignals.map((signal) => (
                  <div key={signal.key} className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium text-foreground">{signal.label}</div>
                      <Badge variant="secondary" className={healthTone[signal.status]}>
                        {healthLabel[signal.status]}
                      </Badge>
                    </div>
                    <div className="mt-2 text-xl font-semibold text-foreground">
                      {signal.value.toFixed(1)}
                      {signal.unit}
                    </div>
                    <div className="mt-2 text-xs leading-5 text-muted-foreground">{signal.summary}</div>
                  </div>
                ))}

                {!healthSignals.length ? (
                  <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                    当前没有可展示的健康信号。
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="capabilities" className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <AgentStatusGrid agents={data?.agentStatuses ?? []} />

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-base font-medium">能力调用概况</CardTitle>
                  <Button asChild variant="ghost" size="sm">
                    <Link href="/tools">
                      能力中心
                      <ArrowRight className="ml-2 size-4" />
                    </Link>
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {highlightedTentacles.map((item) => (
                  <div key={item.agentId ?? item.name} className="rounded-xl border border-border bg-secondary/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium text-foreground">{item.name}</div>
                        <div className="text-xs text-muted-foreground">{item.type}</div>
                      </div>
                      <Badge variant="secondary" className="bg-primary/10 text-xs text-primary">
                        {item.successRate.toFixed(1)}% 成功率
                      </Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs">
                      <Badge variant="secondary">{item.calls} 次调用</Badge>
                      <Badge variant="secondary">{item.successCalls} 次成功</Badge>
                      <Badge variant="secondary">{item.tokens} tokens</Badge>
                      <Badge variant="secondary">{formatDurationMs(item.durationMs)}</Badge>
                    </div>
                  </div>
                ))}

                {!highlightedTentacles.length ? (
                  <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
                    当前还没有可展示的能力调用数据。
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">能力侧重点</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-3">
                <OverviewMetricCard
                  title="活跃 Agent"
                  value={(data?.agentStatuses ?? []).filter((item) => item.status === "running").length}
                  hint="当前处于运行中的 Agent 数量。"
                  toneClass="bg-success/10 text-success"
                  icon={<Bot className="size-4" />}
                />
                <OverviewMetricCard
                  title="触手调用数"
                  value={tentacleMetrics.reduce((sum, item) => sum + item.calls, 0)}
                  hint="当前窗口内累计的外接能力调用次数。"
                  toneClass="bg-primary/10 text-primary"
                  icon={<Wrench className="size-4" />}
                />
                <OverviewMetricCard
                  title="能力风险项"
                  value={tentacleMetrics.filter((item) => item.successRate < 95).length}
                  hint="成功率低于 95% 的能力建议重点观察。"
                  toneClass="bg-warning/10 text-warning-foreground"
                  icon={<AlertTriangle className="size-4" />}
                />
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">总览说明</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
                <div className="rounded-xl border border-border bg-secondary/20 p-4">
                  这页现在只保留“先判断现在是不是健康、有没有待办、有没有风险”的信息。更深的排查请进入任务中心、风险中心和能力中心。
                </div>
                <div className="rounded-xl border border-border bg-secondary/20 p-4">
                  如果你是运营或项目经理，优先看“现在最该处理”和“待用户回复”；如果你是值班或运维，优先看“风险提醒”和“运行状态”分页签。
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {isLoading && !data ? (
        <div className="text-sm text-muted-foreground">正在加载总览数据...</div>
      ) : null}
    </div>
  )
}
