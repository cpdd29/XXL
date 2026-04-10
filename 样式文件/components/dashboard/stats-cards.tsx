"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Bot, GitBranch, ListTodo, Zap, TrendingUp, TrendingDown } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DashboardStat } from "@/types"

interface StatCardProps {
  title: string
  value: string | number
  description: string
  trend?: {
    value: number
    isPositive: boolean
  }
  icon: React.ReactNode
}

function StatCard({ title, value, description, trend, icon }: StatCardProps) {
  return (
    <Card className="bg-card">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <div className="text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold text-foreground">{value}</div>
        <div className="flex items-center gap-2 pt-1">
          <p className="text-xs text-muted-foreground">{description}</p>
          {trend && (
            <span
              className={cn(
                "flex items-center gap-0.5 text-xs font-medium",
                trend.isPositive ? "text-success" : "text-destructive"
              )}
            >
              {trend.isPositive ? (
                <TrendingUp className="size-3" />
              ) : (
                <TrendingDown className="size-3" />
              )}
              {Math.abs(trend.value)}%
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

const statIcons = {
  active_agents: <Bot className="size-4" />,
  workflows: <GitBranch className="size-4" />,
  pending_tasks: <ListTodo className="size-4" />,
  today_runs: <Zap className="size-4" />,
} as const

export function StatsCards({ stats }: { stats: DashboardStat[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <StatCard
          key={stat.key}
          title={stat.title}
          value={stat.value}
          description={stat.description}
          trend={{
            value: stat.trendValue,
            isPositive: stat.trendPositive,
          }}
          icon={statIcons[stat.key as keyof typeof statIcons] ?? <Bot className="size-4" />}
        />
      ))}
    </div>
  )
}
