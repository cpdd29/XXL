"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AgentAvatar } from "@/components/agent-avatar"
import { cn } from "@/lib/utils"
import type { DashboardAgentStatus } from "@/types"

const statusLabels = {
  idle: "空闲",
  running: "运行中",
  waiting: "等待中",
  error: "错误",
}

const statusColors = {
  idle: "bg-muted-foreground/20 text-muted-foreground",
  running: "bg-success/20 text-success",
  waiting: "bg-warning/20 text-warning-foreground",
  error: "bg-destructive/20 text-destructive",
}

export function AgentStatusGrid({ agents }: { agents: DashboardAgentStatus[] }) {
  return (
    <Card className="bg-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-medium">Agent 状态</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3 transition-colors hover:bg-secondary/50"
            >
              <AgentAvatar
                name={agent.name}
                type={agent.type}
                status={agent.status}
                size="md"
              />
              <div className="flex-1 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground">
                    {agent.name}
                  </span>
                  <Badge
                    variant="secondary"
                    className={cn("text-xs", statusColors[agent.status])}
                  >
                    {statusLabels[agent.status]}
                  </Badge>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>完成: {agent.tasksCompleted}</span>
                  <span>响应: {agent.avgResponseTime}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
