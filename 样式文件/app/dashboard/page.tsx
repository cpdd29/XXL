"use client"

import { StatsCards } from "@/components/dashboard/stats-cards"
import { RealtimeLog } from "@/components/dashboard/realtime-log"
import { AgentStatusGrid } from "@/components/dashboard/agent-status-grid"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useDashboardStats } from "@/hooks/use-dashboard"
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

export default function DashboardPage() {
  const { data, isLoading, error } = useDashboardStats()
  const chartData = data?.chartData ?? []

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">控制台</h1>
          <p className="text-sm text-muted-foreground">
            监控系统运行状态和实时数据
          </p>
        </div>
      </div>

      {error && (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            仪表盘数据加载失败：{error instanceof Error ? error.message : "未知错误"}
          </CardContent>
        </Card>
      )}

      <StatsCards stats={data?.stats ?? []} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="bg-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">
              请求量趋势 (24h)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorRequests" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="5%"
                        stopColor="oklch(0.65 0.2 265)"
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor="oklch(0.65 0.2 265)"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="time"
                    stroke="oklch(0.65 0 0)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="oklch(0.65 0 0)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => `${value}`}
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
            <CardTitle className="text-base font-medium">
              Token 消耗趋势 (24h)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="5%"
                        stopColor="oklch(0.55 0.22 160)"
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor="oklch(0.55 0.22 160)"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="time"
                    stroke="oklch(0.65 0 0)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
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

      <div className="grid gap-6 lg:grid-cols-2">
        <AgentStatusGrid agents={data?.agentStatuses ?? []} />
        <RealtimeLog initialLogs={data?.realtimeLogs ?? []} />
      </div>

      <Card className="bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium">失败归因分布</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {(data?.failureBreakdown ?? []).map((item) => (
              <div
                key={item.stage}
                className="min-w-[160px] rounded-xl border border-border bg-secondary/20 px-4 py-3"
              >
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

      {isLoading && !data && (
        <div className="text-sm text-muted-foreground">正在加载仪表盘数据...</div>
      )}
    </div>
  )
}
