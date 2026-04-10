"use client"

import { startTransition, useDeferredValue, useState } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { useCancelTask, useRetryTask, useTasks } from "@/hooks/use-tasks"
import { toast } from "@/hooks/use-toast"
import type { Task, TaskStatus } from "@/types"
import {
  Search,
  Filter,
  MoreVertical,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  PlayCircle,
} from "lucide-react"

const statusConfig: Record<
  TaskStatus,
  { label: string; color: string; icon: React.ReactNode }
> = {
  pending: {
    label: "待处理",
    color: "bg-muted-foreground/20 text-muted-foreground",
    icon: <Clock className="size-4" />,
  },
  running: {
    label: "运行中",
    color: "bg-primary/20 text-primary",
    icon: <PlayCircle className="size-4" />,
  },
  completed: {
    label: "已完成",
    color: "bg-success/20 text-success",
    icon: <CheckCircle2 className="size-4" />,
  },
  failed: {
    label: "失败",
    color: "bg-destructive/20 text-destructive",
    icon: <XCircle className="size-4" />,
  },
  cancelled: {
    label: "已取消",
    color: "bg-warning/20 text-warning-foreground",
    icon: <AlertCircle className="size-4" />,
  },
}

const priorityConfig = {
  low: { label: "低", color: "bg-muted-foreground/20 text-muted-foreground" },
  medium: { label: "中", color: "bg-primary/20 text-primary" },
  high: { label: "高", color: "bg-destructive/20 text-destructive" },
}

const failureStageLabels: Record<string, string> = {
  route: "路由失败",
  dispatch: "调度失败",
  execution: "执行失败",
  outbound: "回传失败",
}

function getTaskMetaLine(task: Task) {
  if (task.statusReason) return task.statusReason
  if (task.failureStage) {
    return failureStageLabels[task.failureStage] ?? task.failureStage
  }
  if (task.currentStage) {
    return `当前阶段：${task.currentStage}`
  }
  return null
}

function TaskCard({
  task,
  onCancel,
  onView,
  onRetry,
}: {
  task: Task
  onCancel: (taskId: string) => Promise<void>
  onView: (taskId: string) => void
  onRetry: (taskId: string) => Promise<void>
}) {
  const status = statusConfig[task.status]
  const priority = priorityConfig[task.priority]
  const metaLine = getTaskMetaLine(task)

  return (
    <Card className="bg-card transition-colors hover:bg-secondary/30">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <span className={cn("rounded p-1", status.color)}>{status.icon}</span>
              <h3 className="font-medium text-foreground">{task.title}</h3>
            </div>
            <p className="text-sm text-muted-foreground">{task.description}</p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Badge variant="secondary" className={cn("text-xs", status.color)}>
                {status.label}
              </Badge>
              <Badge variant="secondary" className={cn("text-xs", priority.color)}>
                优先级: {priority.label}
              </Badge>
              <Badge variant="secondary" className="text-xs">
                {task.agent}
              </Badge>
              {task.tokens > 0 && (
                <Badge variant="secondary" className="bg-accent/20 text-accent text-xs">
                  {task.tokens} tokens
                </Badge>
              )}
              {task.duration && (
                <Badge variant="secondary" className="text-xs">
                  耗时: {task.duration}
                </Badge>
              )}
            </div>
            {metaLine ? (
              <div className="rounded-lg border border-border/70 bg-secondary/20 px-3 py-2 text-xs text-muted-foreground">
                {metaLine}
              </div>
            ) : null}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="size-8">
                <MoreVertical className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={() => onView(task.id)}
              >
                查看详情
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => void onRetry(task.id)}
              >
                重新执行
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                onSelect={() => {
                  if (task.status === "completed" || task.status === "cancelled") {
                    toast({
                      title: "当前任务无需取消",
                      description: "只有待处理或运行中的任务适合取消。",
                    })
                    return
                  }
                  void onCancel(task.id)
                }}
              >
                取消任务
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="mt-3 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
          <span>创建时间: {task.createdAt}</span>
          {task.completedAt && <span>完成时间: {task.completedAt}</span>}
        </div>
      </CardContent>
    </Card>
  )
}

export default function TasksPage() {
  const router = useRouter()
  const [searchQuery, setSearchQuery] = useState("")
  const [activeTab, setActiveTab] = useState("all")
  const [showFilters, setShowFilters] = useState(false)
  const [priorityFilter, setPriorityFilter] = useState("all")
  const [agentFilter, setAgentFilter] = useState("all")
  const [channelFilter, setChannelFilter] = useState("all")
  const deferredSearchQuery = useDeferredValue(searchQuery.trim())
  const { data: allTasksData } = useTasks()
  const { data, isLoading, error, isFetching } = useTasks({
    status: activeTab,
    search: deferredSearchQuery || undefined,
    priority: priorityFilter,
    agent: agentFilter,
    channel: channelFilter,
  })
  const cancelTaskMutation = useCancelTask()
  const retryTaskMutation = useRetryTask()
  const tasks = data?.items ?? []
  const allTasks = allTasksData?.items ?? []

  const availableAgents = [...new Set(allTasks.map((task) => task.agent).filter(Boolean))].sort(
    (left, right) => left.localeCompare(right, "zh-CN"),
  )

  const availableChannels = [
    ...new Set(allTasks.map((task) => task.channel).filter(Boolean)),
  ].sort((left, right) => String(left).localeCompare(String(right), "zh-CN")) as string[]

  const taskCounts = {
    all: allTasks.length,
    pending: allTasks.filter((t) => t.status === "pending").length,
    running: allTasks.filter((t) => t.status === "running").length,
    completed: allTasks.filter((t) => t.status === "completed").length,
    failed: allTasks.filter((t) => t.status === "failed").length,
  }
  const activeAdvancedFilterCount = [
    priorityFilter !== "all",
    agentFilter !== "all",
    channelFilter !== "all",
  ].filter(Boolean).length

  const handleCancelTask = async (taskId: string) => {
    try {
      const result = await cancelTaskMutation.mutateAsync(taskId)
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

  const handleRetryTask = async (taskId: string) => {
    try {
      const result = await retryTaskMutation.mutateAsync(taskId)
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

  const handleViewTask = (taskId: string) => {
    router.push(`/tasks/${encodeURIComponent(taskId)}`)
  }

  const handleSearchChange = (value: string) => {
    startTransition(() => {
      setSearchQuery(value)
    })
  }

  const handleStatusChange = (value: string) => {
    startTransition(() => {
      setActiveTab(value)
    })
  }

  const resetAdvancedFilters = () => {
    startTransition(() => {
      setPriorityFilter("all")
      setAgentFilter("all")
      setChannelFilter("all")
    })
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">任务管理</h1>
          <p className="text-sm text-muted-foreground">
            查看和管理所有任务的执行状态
          </p>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索任务标题、描述、Agent 或渠道..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="bg-secondary pl-10"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowFilters((current) => !current)}
        >
          <Filter className="mr-2 size-4" />
          {activeAdvancedFilterCount > 0 ? `筛选中 (${activeAdvancedFilterCount})` : "筛选"}
        </Button>
      </div>

      {showFilters && (
        <Card className="mb-4 bg-card">
          <CardContent className="flex flex-wrap items-end gap-3 p-4">
            <div className="min-w-[180px] flex-1 space-y-2">
              <p className="text-sm font-medium text-foreground">优先级</p>
              <Select value={priorityFilter} onValueChange={setPriorityFilter}>
                <SelectTrigger className="bg-secondary">
                  <SelectValue placeholder="全部优先级" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部优先级</SelectItem>
                  <SelectItem value="high">高优先级</SelectItem>
                  <SelectItem value="medium">中优先级</SelectItem>
                  <SelectItem value="low">低优先级</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="min-w-[180px] flex-1 space-y-2">
              <p className="text-sm font-medium text-foreground">执行 Agent</p>
              <Select value={agentFilter} onValueChange={setAgentFilter}>
                <SelectTrigger className="bg-secondary">
                  <SelectValue placeholder="全部 Agent" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部 Agent</SelectItem>
                  {availableAgents.map((agent) => (
                    <SelectItem key={agent} value={agent}>
                      {agent}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {availableChannels.length > 0 && (
              <div className="min-w-[180px] flex-1 space-y-2">
                <p className="text-sm font-medium text-foreground">渠道</p>
                <Select value={channelFilter} onValueChange={setChannelFilter}>
                  <SelectTrigger className="bg-secondary">
                    <SelectValue placeholder="全部渠道" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部渠道</SelectItem>
                    {availableChannels.map((channel) => (
                      <SelectItem key={channel} value={channel}>
                        {channel}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <Button
              variant="ghost"
              onClick={resetAdvancedFilters}
              disabled={activeAdvancedFilterCount === 0}
            >
              清空筛选
            </Button>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="mb-4 text-sm text-destructive">
          任务数据加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      )}

      <Tabs value={activeTab} onValueChange={handleStatusChange} className="flex-1">
        <TabsList className="mb-4 bg-secondary">
          <TabsTrigger value="all" className="gap-2">
            全部
            <Badge variant="secondary" className="ml-1 text-xs">
              {taskCounts.all}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="pending" className="gap-2">
            待处理
            <Badge variant="secondary" className="ml-1 text-xs">
              {taskCounts.pending}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="running" className="gap-2">
            运行中
            <Badge variant="secondary" className="ml-1 text-xs">
              {taskCounts.running}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="completed" className="gap-2">
            已完成
            <Badge variant="secondary" className="ml-1 text-xs">
              {taskCounts.completed}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="failed" className="gap-2">
            失败
            <Badge variant="secondary" className="ml-1 text-xs">
              {taskCounts.failed}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="mt-0 flex-1">
          <ScrollArea className="h-[calc(100vh-280px)]">
            <div className="grid gap-4 pr-4 md:grid-cols-2 lg:grid-cols-3">
              {tasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onCancel={handleCancelTask}
                  onView={handleViewTask}
                  onRetry={handleRetryTask}
                />
              ))}
            </div>
            {!isLoading && tasks.length === 0 && (
              <div className="flex h-40 items-center justify-center text-muted-foreground">
                没有找到匹配的任务
              </div>
            )}
            {(isLoading || isFetching) && (
              <div className="flex h-40 items-center justify-center text-muted-foreground">
                正在加载任务...
              </div>
            )}
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  )
}
