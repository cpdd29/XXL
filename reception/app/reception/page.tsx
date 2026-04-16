"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { useDashboardStats } from "@/hooks/use-dashboard"
import { useTaskDetail } from "@/hooks/use-tasks"
import type { DashboardReplyQueueItem } from "@/types"
import { Headphones, ArrowRightLeft, FileText, GitBranch, Search } from "lucide-react"

function groupByChannel<T extends { channel?: string | null }>(items: T[]): Array<[string, T[]]> {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const key = item.channel?.trim() || "unknown"
    const current = groups.get(key) ?? []
    current.push(item)
    groups.set(key, current)
  }
  return Array.from(groups.entries()).sort((left, right) => left[0].localeCompare(right[0], "zh-CN"))
}

export default function ReceptionPage() {
  const searchParams = useSearchParams()
  const initialTaskId = searchParams.get("taskId") ?? undefined
  const { data, isLoading, error } = useDashboardStats()
  const replyQueue: DashboardReplyQueueItem[] = data?.replyQueue ?? []
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>(initialTaskId)
  const [activeChannel, setActiveChannel] = useState<string>("all")
  const [keyword, setKeyword] = useState("")

  const availableChannels = useMemo(
    () => Array.from(new Set(replyQueue.map((item) => item.channel?.trim() || "unknown"))).sort((left, right) =>
      left.localeCompare(right, "zh-CN"),
    ),
    [replyQueue],
  )

  const filteredQueue = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    return replyQueue.filter((item) => {
      const channel = item.channel?.trim() || "unknown"
      if (activeChannel !== "all" && channel !== activeChannel) {
        return false
      }
      if (!normalizedKeyword) {
        return true
      }
      const haystack = [
        item.title,
        item.userLabel,
        item.sessionId,
        item.clarifyQuestion,
        item.nextOwner,
        item.stateLabel,
        item.sessionState,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return haystack.includes(normalizedKeyword)
    })
  }, [activeChannel, keyword, replyQueue])

  useEffect(() => {
    if (!selectedTaskId && filteredQueue.length > 0) {
      setSelectedTaskId(filteredQueue[0].taskId)
    }
  }, [filteredQueue, selectedTaskId])

  useEffect(() => {
    if (selectedTaskId && filteredQueue.some((item) => item.taskId === selectedTaskId)) {
      return
    }
    if (filteredQueue.length > 0) {
      setSelectedTaskId(filteredQueue[0].taskId)
    }
  }, [filteredQueue, selectedTaskId])

  const selectedQueueItem = useMemo(
    () => filteredQueue.find((item) => item.taskId === selectedTaskId) ?? filteredQueue[0],
    [filteredQueue, selectedTaskId],
  )
  const { data: task } = useTaskDetail(selectedQueueItem?.taskId ?? "")
  const groupedQueue = groupByChannel(filteredQueue)
  const runningCount = filteredQueue.filter((item) => item.status === "running").length

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">待办中心</h1>
          <p className="text-sm text-muted-foreground">
            聚焦需要继续对话推进的澄清任务，按渠道和会话快速回到处理链路。
          </p>
        </div>
        <Badge variant="secondary" className="bg-primary/10 text-primary">
          待回复 {replyQueue.length}
        </Badge>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">筛选后会话</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{filteredQueue.length}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">运行中澄清</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{runningCount}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">涉及渠道</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{availableChannels.length}</div>
          </CardContent>
        </Card>
      </div>

      {error ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            待办中心加载失败：{error instanceof Error ? error.message : "未知错误"}
          </CardContent>
        </Card>
      ) : null}

      {!isLoading && replyQueue.length === 0 ? (
        <Card className="bg-card">
          <CardContent className="p-8">
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Headphones className="size-5" />
                </EmptyMedia>
                <EmptyTitle>当前没有待回复会话</EmptyTitle>
                <EmptyDescription>
                  当项目经理要求先澄清再执行时，对应会话会出现在这里。
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button asChild variant="outline">
                  <Link href="/dashboard">返回控制台</Link>
                </Button>
              </EmptyContent>
            </Empty>
          </CardContent>
        </Card>
      ) : null}

      {replyQueue.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">待回复会话</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 p-4">
              <div className="space-y-3">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                    placeholder="搜索标题、用户、会话"
                    className="pl-9"
                  />
                </div>
                <ScrollArea className="w-full whitespace-nowrap">
                  <div className="flex gap-2 pb-1">
                    <Button
                      type="button"
                      variant={activeChannel === "all" ? "default" : "outline"}
                      size="sm"
                      onClick={() => setActiveChannel("all")}
                    >
                      全部
                    </Button>
                    {availableChannels.map((channel) => (
                      <Button
                        key={channel}
                        type="button"
                        variant={activeChannel === channel ? "default" : "outline"}
                        size="sm"
                        onClick={() => setActiveChannel(channel)}
                      >
                        {channel}
                      </Button>
                    ))}
                  </div>
                </ScrollArea>
              </div>
              <ScrollArea className="h-[720px] px-4 pb-4">
                <div className="space-y-4 pt-1">
                  {groupedQueue.map(([channel, items]) => (
                    <div key={channel} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="bg-primary/10 text-primary">
                          {channel}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{items.length} 个会话</span>
                      </div>
                      {items.map((item) => {
                        const selected = item.taskId === selectedQueueItem?.taskId
                        return (
                          <button
                            key={item.taskId}
                            type="button"
                            onClick={() => setSelectedTaskId(item.taskId)}
                            className={`w-full rounded-xl border p-3 text-left transition-colors ${
                              selected
                                ? "border-primary bg-primary/5"
                                : "border-border bg-secondary/20 hover:bg-secondary/35"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <div className="font-medium text-foreground">{item.title}</div>
                              <Badge variant="secondary" className="text-xs">
                                {item.status}
                              </Badge>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {item.userLabel ? (
                                <Badge variant="secondary" className="text-xs">
                                  user: {item.userLabel}
                                </Badge>
                              ) : null}
                              {item.sessionId ? (
                                <Badge variant="secondary" className="text-xs">
                                  session: {item.sessionId}
                                </Badge>
                              ) : null}
                              {item.stateLabel ? (
                                <Badge variant="secondary" className="bg-primary/10 text-primary text-xs">
                                  {item.stateLabel}
                                </Badge>
                              ) : null}
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  ))}
                  {groupedQueue.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
                      当前筛选条件下没有匹配的待回复会话。
                    </div>
                  ) : null}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">接待摘要</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold text-foreground">{selectedQueueItem?.title ?? "--"}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {selectedQueueItem?.channel ?? "--"} · {selectedQueueItem?.userLabel ?? "--"}
                    </div>
                  </div>
                  <Badge variant="secondary">{selectedQueueItem?.status ?? "--"}</Badge>
                </div>
                <div className="rounded-xl bg-warning/10 p-4 text-sm leading-6 text-foreground">
                  {selectedQueueItem?.clarifyQuestion ?? "当前未提供澄清问题。"}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl bg-secondary/30 p-3">
                    <div className="text-xs text-muted-foreground">会话</div>
                    <div className="mt-1 font-medium text-foreground">{selectedQueueItem?.sessionId ?? "--"}</div>
                  </div>
                  <div className="rounded-xl bg-secondary/30 p-3">
                    <div className="text-xs text-muted-foreground">下一归属</div>
                    <div className="mt-1 font-medium text-foreground">{selectedQueueItem?.nextOwner ?? "--"}</div>
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl bg-secondary/30 p-3">
                    <div className="text-xs text-muted-foreground">接待态</div>
                    <div className="mt-2">
                      <Badge variant="secondary" className="bg-primary/10 text-primary">
                        {task?.managerPacket?.receptionMode ?? selectedQueueItem?.receptionMode ?? "--"}
                      </Badge>
                    </div>
                  </div>
                  <div className="rounded-xl bg-secondary/30 p-3">
                    <div className="text-xs text-muted-foreground">执行态</div>
                    <div className="mt-2">
                      <Badge variant="secondary" className="bg-success/15 text-success">
                        {task?.managerPacket?.workflowMode ?? selectedQueueItem?.workflowMode ?? "--"}
                      </Badge>
                    </div>
                  </div>
                  <div className="rounded-xl bg-secondary/30 p-3">
                    <div className="text-xs text-muted-foreground">确认态</div>
                    <div className="mt-2">
                      <Badge variant="secondary" className="bg-warning/15 text-warning-foreground">
                        {task?.managerPacket?.responseContract ??
                          selectedQueueItem?.responseContract ??
                          task?.routeDecision?.confirmationStatus ??
                          selectedQueueItem?.confirmationStatus ??
                          "--"}
                      </Badge>
                    </div>
                  </div>
                </div>
                <div className="rounded-xl bg-secondary/30 p-3">
                  <div className="text-xs text-muted-foreground">项目经理状态</div>
                  <div className="mt-2 flex items-center gap-2">
                    <Badge variant="secondary" className="bg-primary/10 text-primary">
                      {task?.managerPacket?.stateLabel ?? selectedQueueItem?.stateLabel ?? "--"}
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {task?.managerPacket?.sessionState ?? selectedQueueItem?.sessionState ?? "--"}
                    </span>
                  </div>
                </div>
                {selectedQueueItem?.currentStage ? (
                  <div className="rounded-xl bg-secondary/30 p-3">
                    <div className="text-xs text-muted-foreground">当前阶段</div>
                    <div className="mt-1 font-medium text-foreground">{selectedQueueItem.currentStage}</div>
                  </div>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <Button asChild>
                    <Link href={`/collaboration?taskId=${encodeURIComponent(selectedQueueItem?.taskId ?? "")}`}>
                      <ArrowRightLeft className="size-4" />
                      执行过程
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href={`/tasks/${encodeURIComponent(selectedQueueItem?.taskId ?? "")}`}>
                      <FileText className="size-4" />
                      任务详情
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">主脑分发</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">接待态</span>
                  <Badge variant="secondary" className="bg-primary/10 text-primary">
                    {task?.managerPacket?.receptionMode ?? "--"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">执行态</span>
                  <Badge variant="secondary" className="bg-success/10 text-success">
                    {task?.managerPacket?.workflowMode ?? "--"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">确认态</span>
                  <Badge variant="secondary" className="bg-warning/20 text-warning-foreground">
                    {task?.managerPacket?.responseContract ?? task?.routeDecision?.confirmationStatus ?? "--"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">经理动作</span>
                  <span className="text-sm font-medium text-foreground">
                    {task?.managerPacket?.managerAction ?? "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">交付模式</span>
                  <span className="text-sm font-medium text-foreground">
                    {task?.managerPacket?.deliveryMode ?? "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">任务形态</span>
                  <span className="text-sm font-medium text-foreground">
                    {task?.managerPacket?.taskShape ?? "--"}
                  </span>
                </div>
                {task?.managerPacket?.handoffSummary ? (
                  <>
                    <Separator />
                    <div className="rounded-xl bg-secondary/30 p-3 text-xs leading-5 text-muted-foreground">
                      {task.managerPacket.handoffSummary}
                    </div>
                  </>
                ) : null}
              </CardContent>
            </Card>

            <Card className="bg-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">路由落点</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">意图</span>
                  <span className="text-sm font-medium text-foreground">
                    {task?.routeDecision?.intent ?? "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">工作流</span>
                  <span className="text-sm font-medium text-foreground">
                    {task?.routeDecision?.workflowName ?? "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-secondary/30 p-3">
                  <span className="text-sm text-muted-foreground">执行代理</span>
                  <span className="text-sm font-medium text-foreground">
                    {task?.routeDecision?.executionAgent ?? "--"}
                  </span>
                </div>
                <Button asChild variant="outline" className="w-full justify-between">
                  <Link href={`/workflow`}>
                    查看工作流监控
                    <GitBranch className="size-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  )
}
