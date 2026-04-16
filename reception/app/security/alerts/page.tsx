"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  useAcknowledgeAlert,
  useResolveAlert,
  useSecurityAlertCenter,
  useSuppressAlert,
} from "@/hooks/use-security"
import type { AlertCenterSeverity, AlertCenterStatus } from "@/types"

const severityTone = {
  info: "bg-secondary text-secondary-foreground",
  warning: "bg-warning/10 text-warning",
  critical: "bg-destructive/10 text-destructive",
} as const

const statusTone = {
  open: "bg-primary/10 text-primary",
  acknowledged: "bg-secondary text-secondary-foreground",
  resolved: "bg-success/10 text-success",
  suppressed: "bg-warning/10 text-warning",
} as const

export default function SecurityAlertsPage() {
  const searchParams = useSearchParams()
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState<AlertCenterStatus | "all">("all")
  const [severity, setSeverity] = useState<AlertCenterSeverity | "all">("all")
  const [source, setSource] = useState(searchParams.get("source") ?? "all")

  const query = useMemo(
    () => ({
      search: search.trim() || undefined,
      status,
      severity,
      source,
      limit: 100,
      offset: 0,
    }),
    [search, severity, source, status],
  )
  const { data, isLoading, error } = useSecurityAlertCenter(query)
  const acknowledgeAlert = useAcknowledgeAlert()
  const resolveAlert = useResolveAlert()
  const suppressAlert = useSuppressAlert()

  return (
    <div className="flex h-full flex-col gap-6 p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">统一告警中心</h1>
          <p className="text-sm text-muted-foreground">
            汇总 SLA、调度、安全与运行态异常，支持确认、抑制和关闭。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/security">
            <Button variant="outline" size="sm">返回安全中心</Button>
          </Link>
          <Link href="/dashboard">
            <Button size="sm">返回控制台</Button>
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-5">
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">总告警</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{data?.summary.total ?? 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">未处理</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{data?.summary.open ?? 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">已确认</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{data?.summary.acknowledged ?? 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">已关闭</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{data?.summary.resolved ?? 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">已抑制</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{data?.summary.suppressed ?? 0}</div>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium">筛选</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索标题、消息、分类"
            />
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value as AlertCenterStatus | "all")}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">全部状态</option>
              <option value="open">open</option>
              <option value="acknowledged">acknowledged</option>
              <option value="resolved">resolved</option>
              <option value="suppressed">suppressed</option>
            </select>
            <select
              value={severity}
              onChange={(event) => setSeverity(event.target.value as AlertCenterSeverity | "all")}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">全部等级</option>
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="critical">critical</option>
            </select>
            <select
              value={source}
              onChange={(event) => setSource(event.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">全部来源</option>
              <option value="workflow_runtime">workflow_runtime</option>
              <option value="security_gateway">security_gateway</option>
              <option value="security">security</option>
              <option value="runtime">runtime</option>
              <option value="audit">audit</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            告警中心加载失败：{error instanceof Error ? error.message : "未知错误"}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4">
        {(data?.items ?? []).map((item) => (
          <Card key={item.id} className="bg-card">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-medium text-foreground">{item.title}</div>
                    <Badge variant="secondary" className={severityTone[item.severity]}>
                      {item.severity}
                    </Badge>
                    <Badge variant="secondary" className={statusTone[item.status]}>
                      {item.status}
                    </Badge>
                    <Badge variant="secondary">{item.source}</Badge>
                    <Badge variant="secondary">{item.category}</Badge>
                  </div>
                  <div className="mt-2 text-sm leading-6 text-muted-foreground">{item.message}</div>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>发生于 {item.occurredAt}</span>
                    <span>更新于 {item.updatedAt}</span>
                    {item.resource ? <span>资源 {item.resource}</span> : null}
                    {item.workflowRunId ? <span>Run {item.workflowRunId}</span> : null}
                    {item.userKey ? <span>用户 {item.userKey}</span> : null}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {item.href ? (
                    <Link href={item.href}>
                      <Button variant="outline" size="sm">查看上下文</Button>
                    </Link>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={item.status !== "open" || acknowledgeAlert.isPending}
                    onClick={() => acknowledgeAlert.mutate({ alertId: item.id })}
                  >
                    确认
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={item.status === "resolved" || resolveAlert.isPending}
                    onClick={() => resolveAlert.mutate({ alertId: item.id })}
                  >
                    关闭
                  </Button>
                  <Button
                    size="sm"
                    disabled={item.status === "suppressed" || suppressAlert.isPending}
                    onClick={() =>
                      suppressAlert.mutate({
                        alertId: item.id,
                        payload: { durationMinutes: 60, note: "暂时抑制 60 分钟" },
                      })
                    }
                  >
                    抑制 1h
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {!isLoading && !(data?.items?.length) ? (
          <Card className="bg-card">
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              当前筛选条件下没有告警。
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  )
}
