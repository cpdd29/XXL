"use client"

import Link from "next/link"
import { startTransition, useEffect, useState } from "react"
import { ArrowRight, Bot, Clock3, ListTodo, Search, Wifi, WifiOff } from "lucide-react"
import { useTasks } from "@/modules/dispatch/hooks/use-tasks"
import type { TaskListResponse, TaskPriority, TaskStatus } from "@/shared/types"
import { buildAuthenticatedWebSocketUrl } from "@/platform/api/auth-storage"
import { WS_BASE_URL } from "@/platform/api/config"
import { Badge } from "@/shared/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/shared/ui/empty"
import { Input } from "@/shared/ui/input"
import { Skeleton } from "@/shared/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs"

type LiveConnectionState = "connecting" | "connected" | "disconnected" | "error"

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

function formatTime(value?: string | null) {
  const normalized = String(value || "").trim()
  if (!normalized) return "--"
  const parsed = Date.parse(normalized)
  if (!Number.isFinite(parsed)) return normalized
  return new Date(parsed).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function channelLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "dingtalk") return "钉钉"
  if (normalized === "wecom") return "企业微信"
  if (normalized === "feishu") return "飞书"
  if (normalized === "telegram") return "Telegram"
  return normalized || "未标记渠道"
}

function displayText(value?: string | null, fallback = "--") {
  const normalized = String(value || "").trim()
  return normalized || fallback
}

function liveConnectionMeta(state: LiveConnectionState) {
  if (state === "connected") {
    return {
      label: "实时刷新已连接",
      tone: "bg-success/10 text-success",
      icon: <Wifi className="size-3.5" />,
    }
  }
  if (state === "connecting") {
    return {
      label: "实时刷新连接中",
      tone: "bg-warning/10 text-warning-foreground",
      icon: <Wifi className="size-3.5" />,
    }
  }
  if (state === "error") {
    return {
      label: "实时刷新异常",
      tone: "bg-destructive/10 text-destructive",
      icon: <WifiOff className="size-3.5" />,
    }
  }
  return {
    label: "实时刷新未连接",
    tone: "bg-muted text-muted-foreground",
    icon: <WifiOff className="size-3.5" />,
  }
}

export default function TasksPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [activeTab, setActiveTab] = useState("all")
  const [liveData, setLiveData] = useState<TaskListResponse | null>(null)
  const [liveState, setLiveState] = useState<LiveConnectionState>("connecting")
  const trimmedSearch = searchQuery.trim()
  const tasksQuery = useTasks({
    status: activeTab,
    search: trimmedSearch || undefined,
  })
  const taskData = liveData ?? tasksQuery.data
  const items = taskData?.items ?? []
  const liveMeta = liveConnectionMeta(liveState)

  useEffect(() => {
    setLiveData(null)
  }, [activeTab, trimmedSearch])

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const wsUrl = buildAuthenticatedWebSocketUrl("/api/tasks/realtime", WS_BASE_URL)
      if (!wsUrl) {
        setLiveState("error")
        return
      }

      const url = new URL(wsUrl)
      if (activeTab !== "all") {
        url.searchParams.set("status", activeTab)
      }
      if (trimmedSearch) {
        url.searchParams.set("search", trimmedSearch)
      }

      setLiveState("connecting")
      socket = new WebSocket(url.toString())

      socket.onopen = () => {
        if (!cancelled) {
          setLiveState("connected")
        }
      }

      socket.onmessage = (event) => {
        if (cancelled) return
        try {
          setLiveData(JSON.parse(event.data))
        } catch {
          setLiveState("error")
        }
      }

      socket.onerror = () => {
        if (!cancelled) {
          setLiveState("error")
        }
      }

      socket.onclose = () => {
        if (cancelled) return
        setLiveState("disconnected")
        retryTimer = setTimeout(() => {
          connect()
        }, 3000)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimer) {
        clearTimeout(retryTimer)
      }
      if (socket) {
        socket.close()
      }
    }
  }, [activeTab, trimmedSearch])

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

  return (
    <div className="flex h-full flex-col p-6">
      <Tabs value={activeTab} onValueChange={handleStatusChange} className="flex-1 gap-4">
        <div className="mb-4 flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-4">
            <TabsList className="bg-secondary">
              <TabsTrigger value="all">全部</TabsTrigger>
              <TabsTrigger value="pending">待处理</TabsTrigger>
              <TabsTrigger value="running">运行中</TabsTrigger>
              <TabsTrigger value="completed">已完成</TabsTrigger>
              <TabsTrigger value="failed">失败</TabsTrigger>
            </TabsList>

            <div className="relative w-full max-w-md md:ml-auto md:w-80">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="搜索任务标题、描述、Agent 或渠道..."
                value={searchQuery}
                onChange={(event) => handleSearchChange(event.target.value)}
                className="bg-secondary pl-10"
              />
            </div>
          </div>

          <Card className="bg-card">
            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <div className="text-sm text-muted-foreground">当前任务总数</div>
                <div className="mt-1 text-2xl font-semibold text-foreground">
                  {tasksQuery.isLoading && !taskData ? "--" : taskData?.total ?? 0}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Badge variant="secondary" className={liveMeta.tone}>
                  <span className="mr-1">{liveMeta.icon}</span>
                  {liveMeta.label}
                </Badge>
                <div className="text-sm text-muted-foreground">
                  当前筛选：{activeTab === "all" ? "全部状态" : statusConfig[activeTab as TaskStatus]?.label || activeTab}
                  {trimmedSearch ? ` · 关键词「${trimmedSearch}」` : ""}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="bg-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">任务列表</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {tasksQuery.isLoading && !taskData ? (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton key={`task-list-skeleton-${index}`} className="h-40 w-full" />
                ))}
              </div>
            ) : tasksQuery.isError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                任务列表加载失败：{tasksQuery.error instanceof Error ? tasksQuery.error.message : "未知错误"}
              </div>
            ) : items.length === 0 ? (
              <Empty className="border-border py-12">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <ListTodo className="size-5" />
                  </EmptyMedia>
                  <EmptyTitle>当前没有可展示的任务</EmptyTitle>
                  <EmptyDescription>
                    Hermes 识别为任务后的记录，会在这里展示为待处理、运行中或已完成任务。
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <div className="max-h-[calc(100vh-280px)] space-y-3 overflow-y-auto pr-1">
                {items.map((task) => {
                  const status = statusConfig[task.status] ?? {
                    label: task.status,
                    color: "bg-muted text-muted-foreground",
                  }
                  const priority = priorityConfig[task.priority] ?? {
                    label: task.priority,
                    color: "bg-muted text-muted-foreground",
                  }
                  const nextOwner = task.managerPacket?.nextOwner || task.brainDispatchSummary?.nextOwner
                  const deliveryStatus =
                    task.deliveryStatus === "sent"
                      ? "已回传"
                      : task.deliveryStatus === "failed"
                        ? "回传失败"
                        : task.deliveryStatus === "skipped"
                          ? "未自动回传"
                          : null

                  return (
                    <Link
                      key={task.id}
                      href={`/tasks/${encodeURIComponent(task.id)}`}
                      className="block rounded-xl border border-border bg-secondary/20 p-4 transition hover:border-primary/40 hover:bg-secondary/35"
                    >
                      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="min-w-0 text-lg font-medium text-foreground">{task.title}</div>
                            <Badge variant="secondary" className={status.color}>
                              {status.label}
                            </Badge>
                            <Badge variant="secondary" className={priority.color}>
                              优先级 {priority.label}
                            </Badge>
                            <Badge variant="outline" className="border-border">
                              {channelLabel(task.channel)}
                            </Badge>
                            {deliveryStatus ? (
                              <Badge variant="outline" className="border-border">
                                {deliveryStatus}
                              </Badge>
                            ) : null}
                          </div>

                          <div className="mt-2 text-sm leading-6 text-muted-foreground">
                            {displayText(task.description)}
                          </div>

                          <div className="mt-3 flex flex-wrap gap-2">
                            <Badge variant="secondary" className="bg-primary/10 text-primary">
                              当前阶段：{displayText(task.currentStage)}
                            </Badge>
                            {nextOwner ? (
                              <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                                下一归属：{nextOwner}
                              </Badge>
                            ) : null}
                            {task.routeDecision?.interactionMode ? (
                              <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                                交互模式：{task.routeDecision.interactionMode}
                              </Badge>
                            ) : null}
                          </div>
                        </div>

                        <div className="grid shrink-0 gap-3 sm:grid-cols-2 xl:w-[360px]">
                          <div className="rounded-lg bg-background/70 p-3">
                            <div className="text-xs text-muted-foreground">主处理 Agent</div>
                            <div className="mt-2 flex items-center gap-2 text-sm font-medium text-foreground">
                              <Bot className="size-4 text-primary" />
                              {displayText(task.agent)}
                            </div>
                          </div>
                          <div className="rounded-lg bg-background/70 p-3">
                            <div className="text-xs text-muted-foreground">创建时间</div>
                            <div className="mt-2 flex items-center gap-2 text-sm font-medium text-foreground">
                              <Clock3 className="size-4 text-primary" />
                              {formatTime(task.createdAt)}
                            </div>
                          </div>
                          <div className="rounded-lg bg-background/70 p-3">
                            <div className="text-xs text-muted-foreground">租户 / 会话</div>
                            <div className="mt-2 text-sm font-medium text-foreground">
                              {displayText(task.tenantId)}
                            </div>
                            <div className="mt-1 break-all text-xs text-muted-foreground">
                              会话：{displayText(task.sessionId)}
                            </div>
                          </div>
                          <div className="rounded-lg bg-background/70 p-3">
                            <div className="text-xs text-muted-foreground">状态说明</div>
                            <div className="mt-2 text-sm font-medium text-foreground">
                              {displayText(task.statusReason)}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-border/70 pt-3 text-xs text-muted-foreground">
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                          <span>任务 ID：{task.id}</span>
                          <span>Trace：{displayText(task.traceId)}</span>
                        </div>
                        <div className="flex items-center gap-1 text-primary">
                          查看详情
                          <ArrowRight className="size-3.5" />
                        </div>
                      </div>
                    </Link>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </Tabs>
    </div>
  )
}
