"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AgentAvatar } from "@/components/agent-avatar"
import { cn } from "@/lib/utils"
import { useAgents, useReloadAgent } from "@/hooks/use-agents"
import { toast } from "@/hooks/use-toast"
import type { Agent } from "@/types"
import {
  Search,
  Plus,
  Settings,
  BarChart3,
  Activity,
  Zap,
  Clock,
  CheckCircle2,
} from "lucide-react"

const statusLabels = {
  idle: "空闲",
  running: "运行中",
  waiting: "等待中",
  busy: "忙碌",
  degraded: "降级",
  offline: "离线",
  maintenance: "维护中",
  error: "错误",
}

const statusColors = {
  idle: "bg-muted-foreground/20 text-muted-foreground",
  running: "bg-success/20 text-success",
  waiting: "bg-warning/20 text-warning-foreground",
  busy: "bg-success/20 text-success",
  degraded: "bg-warning/20 text-warning-foreground",
  offline: "bg-muted-foreground/20 text-muted-foreground",
  maintenance: "bg-primary/20 text-primary",
  error: "bg-destructive/20 text-destructive",
}

const runtimeLabels = {
  online: "在线",
  degraded: "降级",
  offline: "离线",
  unknown: "待心跳",
}

const runtimeColors = {
  online: "bg-success/20 text-success",
  degraded: "bg-warning/20 text-warning-foreground",
  offline: "bg-destructive/15 text-destructive",
  unknown: "bg-muted-foreground/15 text-muted-foreground",
}

function AgentCard({
  agent,
  onReload,
}: {
  agent: Agent
  onReload: (agentId: string) => Promise<void>
}) {
  const tokenUsagePercent = (agent.tokensUsed / agent.tokensLimit) * 100
  const runtimeStatus = agent.runtimeStatus ?? "unknown"

  return (
    <Card className={cn("bg-card", !agent.enabled && "opacity-60")}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <AgentAvatar
              name={agent.name}
              type={agent.type}
              status={agent.status}
              size="lg"
            />
            <div>
              <CardTitle className="text-base">{agent.name}</CardTitle>
              <p className="text-xs text-muted-foreground">{agent.description}</p>
            </div>
          </div>
          <Switch checked={agent.enabled} disabled />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge
              variant="secondary"
              className={cn("text-xs", statusColors[agent.status])}
            >
              {statusLabels[agent.status]}
            </Badge>
            <Badge
              variant="secondary"
              className={cn("text-xs", runtimeColors[runtimeStatus])}
            >
              {runtimeLabels[runtimeStatus]}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            最后活跃: {agent.lastActive}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-secondary/50 p-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <CheckCircle2 className="size-3" />
              任务完成
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.tasksCompleted.toLocaleString()}
            </div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="size-3" />
              平均响应
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.avgResponseTime}
            </div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Activity className="size-3" />
              成功率
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.successRate}%
            </div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Zap className="size-3" />
              Token 用量
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {(agent.tokensUsed / 1000).toFixed(0)}k
            </div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <BarChart3 className="size-3" />
              队列长度
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.runtimeMetrics?.queueDepth ?? 0}
            </div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="size-3" />
              心跳年龄
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {agent.runtimeMetrics?.heartbeatAgeSeconds ?? 0}s
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Token 配额</span>
            <span className="text-foreground">
              {(agent.tokensUsed / 1000).toFixed(0)}k / {(agent.tokensLimit / 1000).toFixed(0)}k
            </span>
          </div>
          <Progress
            value={tokenUsagePercent}
            className={cn(
              "h-2",
              tokenUsagePercent > 90 && "[&>div]:bg-destructive",
              tokenUsagePercent > 70 && tokenUsagePercent <= 90 && "[&>div]:bg-warning"
            )}
          />
        </div>

        <div className="flex gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="secondary" size="sm" className="flex-1">
                <BarChart3 className="mr-2 size-4" />
                统计
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{agent.name} - 统计数据</DialogTitle>
                <DialogDescription>
                  查看 Agent 的详细运行统计
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <Card className="bg-secondary/50">
                    <CardContent className="p-4">
                      <div className="text-2xl font-bold text-foreground">
                        {agent.tasksCompleted.toLocaleString()}
                      </div>
                      <div className="text-xs text-muted-foreground">总完成任务</div>
                    </CardContent>
                  </Card>
                  <Card className="bg-secondary/50">
                    <CardContent className="p-4">
                      <div className="text-2xl font-bold text-foreground">
                        {agent.successRate}%
                      </div>
                      <div className="text-xs text-muted-foreground">成功率</div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </DialogContent>
          </Dialog>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => void onReload(agent.id)}
          >
            <Settings className="mr-2 size-4" />
            热重载
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function AgentsPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const { data, isLoading, error } = useAgents()
  const reloadAgentMutation = useReloadAgent()
  const agents = data?.items ?? []

  const filteredAgents = agents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const activeCount = agents.filter((a) => a.enabled).length
  const runningCount = agents.filter((a) => a.status === "running").length
  const onlineCount = agents.filter((a) => (a.runtimeStatus ?? "unknown") === "online").length

  const handleReload = async (agentId: string) => {
    try {
      const result = await reloadAgentMutation.mutateAsync(agentId)
      toast({
        title: "Agent 已热重载",
        description: `${result.agentId} 当前状态：${result.status}`,
      })
    } catch (reloadError) {
      toast({
        title: "热重载失败",
        description: reloadError instanceof Error ? reloadError.message : "未知错误",
      })
    }
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agent 管理</h1>
          <p className="text-sm text-muted-foreground">
            管理和配置所有 AI Agent
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>活跃: {activeCount}</span>
            <span>|</span>
            <span className="text-success">运行中: {runningCount}</span>
            <span>|</span>
            <span className="text-success">在线: {onlineCount}</span>
          </div>
          <Button
            size="sm"
            onClick={() =>
              toast({
                title: "添加 Agent 入口已保留",
                description: "下一轮会接入 Agent 创建与配置页。",
              })
            }
          >
            <Plus className="mr-2 size-4" />
            添加 Agent
          </Button>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索 Agent..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-secondary pl-10"
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 text-sm text-destructive">
          Agent 数据加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      )}

      <Tabs defaultValue="all" className="flex-1">
        <TabsList className="mb-4 bg-secondary">
          <TabsTrigger value="all">全部 ({agents.length})</TabsTrigger>
          <TabsTrigger value="active">
            活跃 ({agents.filter((a) => a.enabled).length})
          </TabsTrigger>
          <TabsTrigger value="inactive">
            停用 ({agents.filter((a) => !a.enabled).length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-0">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} onReload={handleReload} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="active" className="mt-0">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents
              .filter((a) => a.enabled)
              .map((agent) => (
                <AgentCard key={agent.id} agent={agent} onReload={handleReload} />
              ))}
          </div>
        </TabsContent>

        <TabsContent value="inactive" className="mt-0">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents
              .filter((a) => !a.enabled)
              .map((agent) => (
                <AgentCard key={agent.id} agent={agent} onReload={handleReload} />
              ))}
          </div>
        </TabsContent>
      </Tabs>

      {isLoading && (
        <div className="pt-4 text-sm text-muted-foreground">正在加载 Agent 数据...</div>
      )}
    </div>
  )
}
