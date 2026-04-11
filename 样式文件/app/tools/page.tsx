"use client"

import { startTransition, useDeferredValue, useMemo, useState } from "react"
import { ToolDetailSheet, ToolSourceDetailSheet } from "@/components/tools/tool-catalog-detail-sheet"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useToolSourceDetail, useToolSources } from "@/hooks/use-tool-sources"
import { useToolDetail, useTools } from "@/hooks/use-tools"
import { cn } from "@/lib/utils"
import type { Tool, ToolHealthStatus, ToolSource, ToolSourceType, ToolType } from "@/types"
import { RefreshCw, Search, Wrench } from "lucide-react"

const toolTypeLabels: Record<ToolType, string> = {
  skill: "Skill",
  tool: "Tool",
  mcp: "MCP",
  unknown: "未分类",
}

const sourceTypeLabels: Record<ToolSourceType, string> = {
  internal: "内部",
  local_tool: "Legacy Fallback",
  external_repo: "外部仓库",
  mcp_server: "MCP Server",
  unknown: "未知来源",
}

const healthLabels: Record<ToolHealthStatus, string> = {
  healthy: "健康",
  degraded: "降级",
  unhealthy: "异常",
  unknown: "未知",
}

const healthClasses: Record<ToolHealthStatus, string> = {
  healthy: "bg-success/20 text-success",
  degraded: "bg-warning/20 text-warning-foreground",
  unhealthy: "bg-destructive/20 text-destructive",
  unknown: "bg-muted-foreground/20 text-muted-foreground",
}

const healthPriority: Record<ToolHealthStatus, number> = {
  healthy: 4,
  degraded: 3,
  unknown: 2,
  unhealthy: 1,
}

const migrationStageLabel: Record<string, string> = {
  retained: "保留",
  bridging: "桥接中",
  externalized: "已外置",
  pending_removal: "待删除",
  deprecated: "已弃用",
  unknown: "未知",
}

const migrationStageClass: Record<string, string> = {
  retained: "bg-success/20 text-success",
  bridging: "bg-warning/20 text-warning-foreground",
  externalized: "bg-primary/15 text-primary",
  pending_removal: "bg-destructive/15 text-destructive",
  deprecated: "bg-muted text-muted-foreground",
  unknown: "bg-muted text-muted-foreground",
}

const sourceModeLabels: Record<string, string> = {
  external_only: "external_only",
  hybrid: "hybrid",
  local_only: "local_only",
  unknown: "unknown",
  mixed: "mixed",
}

const sourceModeClasses: Record<string, string> = {
  external_only: "bg-primary/15 text-primary",
  hybrid: "bg-warning/20 text-warning-foreground",
  local_only: "bg-secondary text-foreground",
  unknown: "bg-muted text-muted-foreground",
  mixed: "bg-warning/20 text-warning-foreground",
}

function toDisplayDate(value: string | null) {
  if (!value) return "-"
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function toTimestamp(value: string | null) {
  if (!value) return 0
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : 0
}

function isCurrentlyAvailable(tool: Tool) {
  return tool.enabled && tool.healthStatus !== "unhealthy"
}

function isConnectableTool(tool: Tool) {
  return !tool.enabled && tool.healthStatus !== "unhealthy"
}

function isRecentlyInvoked(tool: Tool) {
  return tool.invocationSummary.callCount > 0 || Boolean(tool.invocationSummary.lastCalledAt)
}

function isExternalSource(source: ToolSource) {
  return source.type === "external_repo" || source.type === "mcp_server"
}

function normalizeSourceModeValue(value: string | null): string | null {
  if (!value) return null
  const normalized = value.trim().toLowerCase().replace(/-/g, "_")
  if (!normalized) return null
  if (normalized === "external_only" || normalized === "hybrid" || normalized === "local_only") {
    return normalized
  }
  return null
}

function sortToolsByPriority(items: Tool[]) {
  return [...items].sort((left, right) => {
    const availableDiff = Number(isCurrentlyAvailable(right)) - Number(isCurrentlyAvailable(left))
    if (availableDiff !== 0) return availableDiff

    const invokedDiff = Number(isRecentlyInvoked(right)) - Number(isRecentlyInvoked(left))
    if (invokedDiff !== 0) return invokedDiff

    const invokeTimeDiff =
      toTimestamp(right.invocationSummary.lastCalledAt) - toTimestamp(left.invocationSummary.lastCalledAt)
    if (invokeTimeDiff !== 0) return invokeTimeDiff

    const healthDiff = healthPriority[right.healthStatus] - healthPriority[left.healthStatus]
    if (healthDiff !== 0) return healthDiff

    const scanDiff = toTimestamp(right.lastScannedAt) - toTimestamp(left.lastScannedAt)
    if (scanDiff !== 0) return scanDiff

    return left.name.localeCompare(right.name, "zh-CN")
  })
}

function sortSourcesByPriority(items: ToolSource[]) {
  return [...items].sort((left, right) => {
    const enabledDiff = Number(right.enabled) - Number(left.enabled)
    if (enabledDiff !== 0) return enabledDiff

    const healthDiff = healthPriority[right.healthStatus] - healthPriority[left.healthStatus]
    if (healthDiff !== 0) return healthDiff

    const scanDiff = right.scannedCapabilityCount - left.scannedCapabilityCount
    if (scanDiff !== 0) return scanDiff

    const timeDiff = toTimestamp(right.lastScannedAt) - toTimestamp(left.lastScannedAt)
    if (timeDiff !== 0) return timeDiff

    return left.name.localeCompare(right.name, "zh-CN")
  })
}

function ToolHealthBadge({
  status,
  message,
}: {
  status: ToolHealthStatus
  message: string
}) {
  return (
    <div className="space-y-1">
      <Badge variant="secondary" className={cn("text-xs", healthClasses[status])}>
        {healthLabels[status]}
      </Badge>
      {message ? (
        <div className="max-w-[220px] truncate text-xs text-muted-foreground" title={message}>
          {message}
        </div>
      ) : null}
    </div>
  )
}

function ToolSourceAgents({ names }: { names: string[] }) {
  if (names.length === 0) {
    return <span className="text-xs text-muted-foreground">未关联</span>
  }

  const visible = names.slice(0, 2)
  const hiddenCount = names.length - visible.length

  return (
    <div className="flex flex-wrap items-center gap-1">
      {visible.map((name) => (
        <Badge key={name} variant="secondary" className="text-xs">
          {name}
        </Badge>
      ))}
      {hiddenCount > 0 ? (
        <Badge variant="secondary" className="bg-secondary/60 text-xs text-muted-foreground">
          +{hiddenCount}
        </Badge>
      ) : null}
    </div>
  )
}

function EmptyRow({
  colSpan,
  title,
  description,
}: {
  colSpan: number
  title: string
  description: string
}) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="py-10 text-center">
        <div className="space-y-1">
          <div className="text-sm font-medium text-foreground">{title}</div>
          <div className="text-xs text-muted-foreground">{description}</div>
        </div>
      </TableCell>
    </TableRow>
  )
}

const tableHeadClassName = "bg-secondary/40 text-muted-foreground"
const wrapCellClassName = "align-top whitespace-normal break-words"
const compactCellClassName = "align-top"

function SourceTypeSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full bg-background sm:w-[180px]">
        <SelectValue placeholder="来源类型" />
      </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部来源类型</SelectItem>
          <SelectItem value="internal">内部</SelectItem>
          <SelectItem value="local_tool">Legacy Fallback</SelectItem>
          <SelectItem value="external_repo">外部仓库</SelectItem>
          <SelectItem value="mcp_server">MCP Server</SelectItem>
          <SelectItem value="unknown">未知来源</SelectItem>
      </SelectContent>
    </Select>
  )
}

function SourceGovernanceBadges({ source }: { source: ToolSource }) {
  const mode = normalizeSourceModeValue(source.sourceMode)

  return (
    <div className="flex flex-wrap gap-1">
      {mode ? (
        <Badge variant="secondary" className={cn("text-xs", sourceModeClasses[mode] ?? sourceModeClasses.unknown)}>
          {sourceModeLabels[mode] ?? mode}
        </Badge>
      ) : null}
      {source.activationMode ? (
        <Badge variant="secondary" className="text-xs">
          activation: {source.activationMode}
        </Badge>
      ) : null}
      {source.legacyFallback ? (
        <Badge variant="secondary" className="bg-warning/20 text-xs text-warning-foreground">
          legacy fallback
        </Badge>
      ) : null}
      {source.deprecated ? (
        <Badge variant="secondary" className="bg-destructive/15 text-xs text-destructive">
          deprecated
        </Badge>
      ) : null}
      {!mode && !source.activationMode && !source.legacyFallback && !source.deprecated ? (
        <span className="text-xs text-muted-foreground">未声明</span>
      ) : null}
    </div>
  )
}

export default function ToolsPage() {
  const [activeTab, setActiveTab] = useState("tools")
  const [searchQuery, setSearchQuery] = useState("")
  const [toolTypeFilter, setToolTypeFilter] = useState("all")
  const [toolSourceFilter, setToolSourceFilter] = useState("all")
  const [toolMigrationFilter, setToolMigrationFilter] = useState("all")
  const [toolHealthFilter, setToolHealthFilter] = useState("all")
  const [toolEnabledFilter, setToolEnabledFilter] = useState("all")
  const [sourceTypeFilter, setSourceTypeFilter] = useState("all")
  const [sourceHealthFilter, setSourceHealthFilter] = useState("all")
  const [sourceEnabledFilter, setSourceEnabledFilter] = useState("all")
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null)
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null)
  const [toolDetailOpen, setToolDetailOpen] = useState(false)
  const [sourceDetailOpen, setSourceDetailOpen] = useState(false)
  const deferredSearch = useDeferredValue(searchQuery.trim().toLowerCase())

  const {
    data: toolsData,
    isLoading: toolsLoading,
    isFetching: toolsFetching,
    error: toolsError,
    refetch: refetchTools,
  } = useTools()
  const {
    data: sourceData,
    isLoading: sourcesLoading,
    isFetching: sourcesFetching,
    error: sourcesError,
    refetch: refetchSources,
  } = useToolSources()
  const { data: sourceDetailData } = useToolSourceDetail(selectedSourceId)
  const {
    data: toolDetailData,
    isFetching: toolDetailFetching,
    refetch: refetchToolDetail,
  } = useToolDetail(selectedToolId)

  const tools = toolsData?.items ?? []
  const sources = sourceData?.items ?? []
  const governanceSummary = sourceData?.governanceSummary ?? null
  const selectedToolFromList = tools.find((tool) => tool.id === selectedToolId) ?? null
  const selectedTool = toolDetailData ?? selectedToolFromList
  const selectedSourceFromTools =
    sources.find((source) => source.id === selectedTool?.sourceId) ??
    sources.find((source) => source.name === selectedTool?.sourceName) ??
    null
  const selectedSource = sourceDetailData ?? sources.find((source) => source.id === selectedSourceId) ?? null

  const sourceNameOptions = [...new Set(tools.map((tool) => tool.sourceName).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "zh-CN"),
  )

  const filteredTools = useMemo(() => {
    const matched = tools.filter((tool) => {
      const matchesSearch =
        !deferredSearch ||
        tool.name.toLowerCase().includes(deferredSearch) ||
        tool.description.toLowerCase().includes(deferredSearch) ||
        tool.sourceName.toLowerCase().includes(deferredSearch) ||
        tool.providerSummary.toLowerCase().includes(deferredSearch) ||
        tool.configSummary.toLowerCase().includes(deferredSearch) ||
        tool.invocationSummary.summary.toLowerCase().includes(deferredSearch) ||
        tool.linkedAgents.some((agent) => agent.toLowerCase().includes(deferredSearch)) ||
        tool.linkedWorkflows.some((workflow) => workflow.toLowerCase().includes(deferredSearch)) ||
        tool.requiredCapabilities.some((capability) => capability.toLowerCase().includes(deferredSearch))

      const matchesType = toolTypeFilter === "all" || tool.type === toolTypeFilter
      const matchesSource = toolSourceFilter === "all" || tool.sourceName === toolSourceFilter
      const matchesMigration = toolMigrationFilter === "all" || tool.migrationStage === toolMigrationFilter
      const matchesHealth = toolHealthFilter === "all" || tool.healthStatus === toolHealthFilter
      const matchesEnabled =
        toolEnabledFilter === "all" ||
        (toolEnabledFilter === "enabled" && tool.enabled) ||
        (toolEnabledFilter === "disabled" && !tool.enabled)

      return matchesSearch && matchesType && matchesSource && matchesMigration && matchesHealth && matchesEnabled
    })

    return sortToolsByPriority(matched)
  }, [
    deferredSearch,
    toolEnabledFilter,
    toolHealthFilter,
    toolMigrationFilter,
    toolSourceFilter,
    toolTypeFilter,
    tools,
  ])

  const filteredSources = useMemo(() => {
    const matched = sources.filter((source) => {
      const matchesSearch =
        !deferredSearch ||
        source.name.toLowerCase().includes(deferredSearch) ||
        source.description.toLowerCase().includes(deferredSearch) ||
        source.providerSummary.toLowerCase().includes(deferredSearch) ||
        source.configSummary.toLowerCase().includes(deferredSearch) ||
        source.path?.toLowerCase().includes(deferredSearch) ||
        source.notes.some((note) => note.toLowerCase().includes(deferredSearch)) ||
        source.linkedAgents.some((agent) => agent.toLowerCase().includes(deferredSearch))

      const matchesType = sourceTypeFilter === "all" || source.type === sourceTypeFilter
      const matchesHealth = sourceHealthFilter === "all" || source.healthStatus === sourceHealthFilter
      const matchesEnabled =
        sourceEnabledFilter === "all" ||
        (sourceEnabledFilter === "enabled" && source.enabled) ||
        (sourceEnabledFilter === "disabled" && !source.enabled)

      return matchesSearch && matchesType && matchesHealth && matchesEnabled
    })

    return sortSourcesByPriority(matched)
  }, [
    deferredSearch,
    sourceEnabledFilter,
    sourceHealthFilter,
    sourceTypeFilter,
    sources,
  ])

  const toolHealthStats = {
    healthy: tools.filter((tool) => tool.healthStatus === "healthy").length,
    degraded: tools.filter((tool) => tool.healthStatus === "degraded").length,
    unhealthy: tools.filter((tool) => tool.healthStatus === "unhealthy").length,
  }

  const sourceHealthStats = {
    healthy: sources.filter((source) => source.healthStatus === "healthy").length,
    degraded: sources.filter((source) => source.healthStatus === "degraded").length,
    unhealthy: sources.filter((source) => source.healthStatus === "unhealthy").length,
  }

  const availableToolCount = tools.filter(isCurrentlyAvailable).length
  const enabledToolCount = tools.filter((tool) => tool.enabled).length
  const connectableToolCount = tools.filter(isConnectableTool).length
  const recentInvokedToolCount = tools.filter(isRecentlyInvoked).length
  const externalSourceCount = sources.filter(isExternalSource).length
  const sourceTypeStats = {
    internal: sources.filter((source) => source.type === "internal").length,
    local_tool: sources.filter((source) => source.type === "local_tool").length,
    external_repo: sources.filter((source) => source.type === "external_repo").length,
    mcp_server: sources.filter((source) => source.type === "mcp_server").length,
  }
  const legacyFallbackCount = sources.filter((source) => source.legacyFallback).length
  const deprecatedSourceCount = sources.filter((source) => source.deprecated).length
  const activationModes = [...new Set(sources.map((source) => source.activationMode).filter(Boolean))] as string[]
  const declaredModes = [
    ...new Set(sources.map((source) => normalizeSourceModeValue(source.sourceMode)).filter(Boolean)),
  ] as string[]
  const declaredGlobalMode = normalizeSourceModeValue(
    typeof governanceSummary?.mode === "string" ? governanceSummary.mode : null,
  )
  const runtimeMode = (() => {
    if (declaredGlobalMode) return declaredGlobalMode
    if (declaredModes.length === 1) return declaredModes[0]
    if (declaredModes.length > 1) return "mixed"
    if (sources.length === 0) return "unknown"
    const externalCount = sources.filter(isExternalSource).length
    const localCount = sources.filter((source) => source.type === "local_tool" || source.type === "internal").length
    if (externalCount > 0 && localCount === 0) return "external_only"
    if (externalCount > 0 && localCount > 0) return "hybrid"
    if (externalCount === 0 && localCount > 0) return "local_only"
    return "unknown"
  })()
  const totalScannedCapabilities = tools.reduce((total, tool) => total + tool.capabilityCount, 0)
  const isRefreshing = toolsFetching || sourcesFetching

  const relatedToolNamesForSource = selectedSource
    ? sortToolsByPriority(
        tools.filter((tool) => tool.sourceId === selectedSource.id || tool.sourceName === selectedSource.name),
      ).map((tool) => tool.name)
    : []

  const handleRefresh = async () => {
    await Promise.all([refetchTools(), refetchSources()])
    if (selectedToolId) {
      await refetchToolDetail()
    }
  }

  return (
    <>
      <div className="flex h-full min-h-0 w-full flex-col p-6">
        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">工具库</h1>
            <p className="text-sm text-muted-foreground">
              统一查看当前系统中已扫描的 Skill / MCP / Tool 以及外部来源状态。
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void handleRefresh()} disabled={isRefreshing}>
            <RefreshCw className={cn("mr-2 size-4", isRefreshing && "animate-spin")} />
            {isRefreshing ? "同步中..." : "刷新"}
          </Button>
        </div>

        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Card className="bg-card">
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">能力总数</div>
              <div className="mt-1 text-2xl font-semibold text-foreground">{tools.length}</div>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">已启用能力</div>
              <div className="mt-1 text-2xl font-semibold text-success">{enabledToolCount}</div>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">可接入能力</div>
              <div className="mt-1 text-2xl font-semibold text-success">{availableToolCount}</div>
              <div className="mt-1 text-[11px] text-muted-foreground">未启用且健康状态可接入：{connectableToolCount}</div>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">外部来源</div>
              <div className="mt-1 text-2xl font-semibold text-foreground">{externalSourceCount}</div>
              <div className="mt-1 text-[11px] text-muted-foreground">总来源 {sources.length}</div>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground">最近被调用能力</div>
              <div className="mt-1 text-2xl font-semibold text-foreground">{recentInvokedToolCount}</div>
            </CardContent>
          </Card>
        </div>

        <Card className="mb-6 border-primary/30 bg-primary/5">
          <CardContent className="p-4">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-xs text-muted-foreground">治理状态</div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className={cn("text-xs", sourceModeClasses[runtimeMode] ?? sourceModeClasses.unknown)}>
                    运行模式: {sourceModeLabels[runtimeMode] ?? runtimeMode}
                  </Badge>
                  {declaredModes.length === 0 ? (
                    <Badge variant="secondary" className="text-xs text-muted-foreground">
                      mode: {declaredGlobalMode ? "governance" : "inferred"}
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="text-xs">
                      mode: {declaredGlobalMode ? "governance" : "declared"}
                    </Badge>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="secondary" className={legacyFallbackCount > 0 ? "bg-warning/20 text-warning-foreground" : "text-muted-foreground"}>
                  legacy fallback {legacyFallbackCount}
                </Badge>
                <Badge variant="secondary" className={deprecatedSourceCount > 0 ? "bg-destructive/15 text-destructive" : "text-muted-foreground"}>
                  deprecated {deprecatedSourceCount}
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  activation_mode {activationModes.length}
                </Badge>
              </div>
            </div>
            {runtimeMode !== "external_only" ? (
              <div className="mt-3 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning-foreground">
                当前不是 `external_only` 主链模式，系统仍允许部分 legacy fallback 路径参与运行或应急兜底。生产目标应保持大脑封闭、触手外接。
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-card">
          <CardHeader className="space-y-4 pb-3">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <CardTitle className="text-base">能力与来源总览</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {activeTab === "tools"
                    ? `当前显示 ${filteredTools.length} / ${tools.length} 个能力，默认按“可用 + 最近调用”优先排序`
                    : `当前显示 ${filteredSources.length} / ${sources.length} 个来源`}
                </p>
              </div>
              <div className="relative w-full xl:w-80">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="搜索名称 / 来源 / Agent / provider..."
                  value={searchQuery}
                  onChange={(event) =>
                    startTransition(() => {
                      setSearchQuery(event.target.value)
                    })
                  }
                  className="w-full bg-secondary pl-10"
                />
              </div>
            </div>
          </CardHeader>

          <CardContent className="flex min-h-0 min-w-0 flex-1 flex-col space-y-4">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex min-h-0 w-full flex-1 min-w-0 flex-col">
              <TabsList className="grid w-full grid-cols-2 md:w-[360px]">
                <TabsTrigger value="tools">能力列表</TabsTrigger>
                <TabsTrigger value="sources">外部来源</TabsTrigger>
              </TabsList>

              <TabsContent value="tools" className="mt-4 flex min-h-0 min-w-0 flex-1 flex-col space-y-4">
                <div className="shrink-0 flex flex-col gap-3 rounded-xl border border-border bg-secondary/20 p-4 md:flex-row md:flex-wrap md:items-center">
                  <Select value={toolTypeFilter} onValueChange={setToolTypeFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[150px]">
                      <SelectValue placeholder="能力类型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部类型</SelectItem>
                      <SelectItem value="skill">Skill</SelectItem>
                      <SelectItem value="tool">Tool</SelectItem>
                      <SelectItem value="mcp">MCP</SelectItem>
                      <SelectItem value="unknown">未分类</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={toolSourceFilter} onValueChange={setToolSourceFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[180px]">
                      <SelectValue placeholder="来源" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部来源</SelectItem>
                      {sourceNameOptions.map((sourceName) => (
                        <SelectItem key={sourceName} value={sourceName}>
                          {sourceName}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={toolMigrationFilter} onValueChange={setToolMigrationFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[170px]">
                      <SelectValue placeholder="迁移阶段" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部迁移阶段</SelectItem>
                      <SelectItem value="retained">保留</SelectItem>
                      <SelectItem value="bridging">桥接中</SelectItem>
                      <SelectItem value="externalized">已外置</SelectItem>
                      <SelectItem value="pending_removal">待删除</SelectItem>
                      <SelectItem value="deprecated">已弃用</SelectItem>
                      <SelectItem value="unknown">未知</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={toolHealthFilter} onValueChange={setToolHealthFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[150px]">
                      <SelectValue placeholder="健康状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部健康状态</SelectItem>
                      <SelectItem value="healthy">健康</SelectItem>
                      <SelectItem value="degraded">降级</SelectItem>
                      <SelectItem value="unhealthy">异常</SelectItem>
                      <SelectItem value="unknown">未知</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={toolEnabledFilter} onValueChange={setToolEnabledFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[130px]">
                      <SelectValue placeholder="启用状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部状态</SelectItem>
                      <SelectItem value="enabled">已启用</SelectItem>
                      <SelectItem value="disabled">已停用</SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="flex flex-wrap gap-2 md:ml-auto">
                    <Badge variant="secondary" className={cn("text-xs", healthClasses.healthy)}>
                      健康 {toolHealthStats.healthy}
                    </Badge>
                    <Badge variant="secondary" className={cn("text-xs", healthClasses.degraded)}>
                      降级 {toolHealthStats.degraded}
                    </Badge>
                    <Badge variant="secondary" className={cn("text-xs", healthClasses.unhealthy)}>
                      异常 {toolHealthStats.unhealthy}
                    </Badge>
                  </div>
                </div>

                <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-border">
                  <div className="h-full overflow-y-auto">
                  <Table className="min-w-[1760px] table-fixed">
                    <colgroup>
                      <col className="w-[320px]" />
                      <col className="w-[96px]" />
                      <col className="w-[160px]" />
                      <col className="w-[140px]" />
                      <col className="w-[170px]" />
                      <col className="w-[160px]" />
                      <col className="w-[180px]" />
                      <col className="w-[220px]" />
                      <col className="w-[120px]" />
                      <col className="w-[120px]" />
                      <col className="w-[160px]" />
                    </colgroup>
                    <TableHeader className="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
                      <TableRow className="border-border">
                        <TableHead className={tableHeadClassName}>能力</TableHead>
                        <TableHead className={tableHeadClassName}>类型</TableHead>
                        <TableHead className={tableHeadClassName}>来源</TableHead>
                        <TableHead className={tableHeadClassName}>迁移阶段</TableHead>
                        <TableHead className={tableHeadClassName}>桥接治理</TableHead>
                        <TableHead className={tableHeadClassName}>健康</TableHead>
                        <TableHead className={tableHeadClassName}>关联 Agent</TableHead>
                        <TableHead className={tableHeadClassName}>Provider / Config</TableHead>
                        <TableHead className={tableHeadClassName}>能力/权限</TableHead>
                        <TableHead className={tableHeadClassName}>状态</TableHead>
                        <TableHead className={tableHeadClassName}>最近调用 / 扫描</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {toolsLoading ? (
                        Array.from({ length: 6 }).map((_, index) => (
                          <TableRow key={`tool-skeleton-${index}`}>
                            <TableCell colSpan={11}>
                              <Skeleton className="h-7 w-full" />
                            </TableCell>
                          </TableRow>
                        ))
                      ) : filteredTools.length === 0 ? (
                        <EmptyRow colSpan={11} title="没有匹配的能力" description="请调整筛选条件或检查后端数据。" />
                      ) : (
                        filteredTools.map((tool) => (
                          <TableRow key={tool.id} className="border-border">
                            <TableCell className={wrapCellClassName}>
                              <div className="min-w-0 space-y-2">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="font-medium text-foreground">{tool.name}</div>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    className="h-7 px-2 text-xs"
                                    onClick={() => {
                                      setSelectedToolId(tool.id)
                                      setToolDetailOpen(true)
                                    }}
                                  >
                                    详情
                                  </Button>
                                </div>
                                <div className="text-xs leading-5 text-muted-foreground">{tool.description || "-"}</div>
                                <div className="flex flex-wrap gap-1">
                                  {isCurrentlyAvailable(tool) ? (
                                    <Badge variant="secondary" className="bg-success/20 text-xs text-success">
                                      当前可用
                                    </Badge>
                                  ) : null}
                                  {isRecentlyInvoked(tool) ? (
                                    <Badge variant="secondary" className="text-xs">
                                      最近调用
                                    </Badge>
                                  ) : null}
                                  {tool.tags.slice(0, 2).map((tag) => (
                                    <Badge key={`${tool.id}-${tag}`} variant="secondary" className="text-xs">
                                      {tag}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className={compactCellClassName}>
                              <Badge variant="secondary">{toolTypeLabels[tool.type]}</Badge>
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <div className="min-w-0 text-sm text-foreground">{tool.sourceName}</div>
                              <div className="text-xs text-muted-foreground">{sourceTypeLabels[tool.sourceType]} / {tool.sourceKind}</div>
                            </TableCell>
                            <TableCell className={compactCellClassName}>
                              <Badge variant="secondary" className={cn("text-xs", migrationStageClass[tool.migrationStage])}>
                                {migrationStageLabel[tool.migrationStage]}
                              </Badge>
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <div className="space-y-1 text-xs">
                                <div className="text-foreground">bridge: {tool.bridgeMode}</div>
                                <div className="text-muted-foreground">
                                  policy: {tool.trafficPolicy ? "双跑/灰度已配置" : "默认"}
                                </div>
                                <div className="text-muted-foreground">
                                  rollback: {tool.rollbackSummary ? "可回滚" : "未声明"}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <ToolHealthBadge status={tool.healthStatus} message={tool.healthMessage} />
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <ToolSourceAgents names={tool.linkedAgents} />
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <div className="min-w-0 space-y-1 text-xs">
                                <div className="text-foreground">{tool.providerSummary || "-"}</div>
                                <div className="leading-5 text-muted-foreground">{tool.configSummary || "-"}</div>
                              </div>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              <div className="font-medium text-foreground">cap: {tool.capabilityCount}</div>
                              <div className="mt-1">perm: {tool.permissions.requiresPermission ? "需要" : "无需"}</div>
                              <div>approval: {tool.permissions.approvalRequired ? "需要" : "无需"}</div>
                            </TableCell>
                            <TableCell className={compactCellClassName}>
                              <Badge
                                variant="secondary"
                                className={tool.enabled ? "bg-success/20 text-success" : "bg-muted text-muted-foreground"}
                              >
                                {tool.enabled ? "已启用" : "已停用"}
                              </Badge>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              <div>{toDisplayDate(tool.invocationSummary.lastCalledAt)}</div>
                              <div className="mt-1 text-[11px]">
                                {`ok ${tool.invocationSummary.successCalls} / fail ${tool.invocationSummary.failedCalls}`}
                              </div>
                              <div className="text-[11px]">状态: {tool.invocationSummary.lastStatus}</div>
                              <div className="mt-1 text-[11px]">
                                扫描: {toDisplayDate(tool.lastScannedAt)}
                              </div>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="sources" className="mt-4 flex min-h-0 min-w-0 flex-1 flex-col space-y-4">
                <div className="shrink-0 flex flex-col gap-3 rounded-xl border border-border bg-secondary/20 p-4 md:flex-row md:flex-wrap md:items-center">
                  <SourceTypeSelect value={sourceTypeFilter} onChange={setSourceTypeFilter} />
                  <Select value={sourceHealthFilter} onValueChange={setSourceHealthFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[150px]">
                      <SelectValue placeholder="健康状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部健康状态</SelectItem>
                      <SelectItem value="healthy">健康</SelectItem>
                      <SelectItem value="degraded">降级</SelectItem>
                      <SelectItem value="unhealthy">异常</SelectItem>
                      <SelectItem value="unknown">未知</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={sourceEnabledFilter} onValueChange={setSourceEnabledFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[130px]">
                      <SelectValue placeholder="启用状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部状态</SelectItem>
                      <SelectItem value="enabled">已启用</SelectItem>
                      <SelectItem value="disabled">已停用</SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="flex flex-wrap gap-2 md:ml-auto">
                    <Badge variant="secondary" className="text-xs">
                      外部仓库 {sourceTypeStats.external_repo}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      MCP Server {sourceTypeStats.mcp_server}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      内部 {sourceTypeStats.internal}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      Legacy {sourceTypeStats.local_tool}
                    </Badge>
                    <Badge variant="secondary" className={cn("text-xs", healthClasses.healthy)}>
                      健康 {sourceHealthStats.healthy}
                    </Badge>
                    <Badge variant="secondary" className={cn("text-xs", healthClasses.degraded)}>
                      降级 {sourceHealthStats.degraded}
                    </Badge>
                    <Badge variant="secondary" className={cn("text-xs", healthClasses.unhealthy)}>
                      异常 {sourceHealthStats.unhealthy}
                    </Badge>
                    <Badge
                      variant="secondary"
                      className={legacyFallbackCount > 0 ? "bg-warning/20 text-xs text-warning-foreground" : "text-xs"}
                    >
                      legacy {legacyFallbackCount}
                    </Badge>
                    <Badge
                      variant="secondary"
                      className={deprecatedSourceCount > 0 ? "bg-destructive/15 text-xs text-destructive" : "text-xs"}
                    >
                      deprecated {deprecatedSourceCount}
                    </Badge>
                  </div>
                </div>

                <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-border">
                  <div className="h-full overflow-y-auto">
                  <Table className="min-w-[1520px] table-fixed">
                    <colgroup>
                      <col className="w-[300px]" />
                      <col className="w-[110px]" />
                      <col className="w-[240px]" />
                      <col className="w-[110px]" />
                      <col className="w-[160px]" />
                      <col className="w-[160px]" />
                      <col className="w-[170px]" />
                      <col className="w-[220px]" />
                      <col className="w-[96px]" />
                      <col className="w-[170px]" />
                    </colgroup>
                    <TableHeader className="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
                      <TableRow className="border-border">
                        <TableHead className={tableHeadClassName}>来源</TableHead>
                        <TableHead className={tableHeadClassName}>类型</TableHead>
                        <TableHead className={tableHeadClassName}>路径 / Provider</TableHead>
                        <TableHead className={tableHeadClassName}>已扫描能力</TableHead>
                        <TableHead className={tableHeadClassName}>健康</TableHead>
                        <TableHead className={tableHeadClassName}>关联 Agent</TableHead>
                        <TableHead className={tableHeadClassName}>Config 摘要</TableHead>
                        <TableHead className={tableHeadClassName}>治理状态</TableHead>
                        <TableHead className={tableHeadClassName}>状态</TableHead>
                        <TableHead className={tableHeadClassName}>最近检查 / 扫描</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sourcesLoading ? (
                        Array.from({ length: 6 }).map((_, index) => (
                          <TableRow key={`source-skeleton-${index}`}>
                            <TableCell colSpan={10}>
                              <Skeleton className="h-7 w-full" />
                            </TableCell>
                          </TableRow>
                        ))
                      ) : filteredSources.length === 0 ? (
                        <EmptyRow colSpan={10} title="没有匹配的来源" description="请调整筛选条件或检查扫描任务结果。" />
                      ) : (
                        filteredSources.map((source) => (
                          <TableRow key={source.id} className="border-border">
                            <TableCell className={wrapCellClassName}>
                              <div className="min-w-0 space-y-2">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="font-medium text-foreground">{source.name}</div>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    className="h-7 px-2 text-xs"
                                    onClick={() => {
                                      setSelectedSourceId(source.id)
                                      setSourceDetailOpen(true)
                                    }}
                                  >
                                    详情
                                  </Button>
                                </div>
                                <div className="text-xs leading-5 text-muted-foreground">{source.description || "-"}</div>
                                <div className="flex flex-wrap gap-1">
                                  {source.legacyFallback ? (
                                    <Badge variant="secondary" className="bg-warning/20 text-xs text-warning-foreground">
                                      legacy fallback
                                    </Badge>
                                  ) : null}
                                  {source.deprecated ? (
                                    <Badge variant="secondary" className="bg-destructive/15 text-xs text-destructive">
                                      deprecated
                                    </Badge>
                                  ) : null}
                                  {source.tags.slice(0, 3).map((tag) => (
                                    <Badge key={`${source.id}-${tag}`} variant="secondary" className="text-xs">
                                      {tag}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className={compactCellClassName}>
                              <Badge variant="secondary">{sourceTypeLabels[source.type]}</Badge>
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <div className="min-w-0 text-sm text-foreground">{source.path || "-"}</div>
                              <div className="text-xs leading-5 text-muted-foreground">{source.providerSummary || "-"}</div>
                            </TableCell>
                            <TableCell className="align-top text-sm font-medium text-foreground">
                              {source.scannedCapabilityCount}
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <ToolHealthBadge status={source.healthStatus} message={source.healthMessage} />
                            </TableCell>
                            <TableCell className={wrapCellClassName}>
                              <ToolSourceAgents names={source.linkedAgents} />
                            </TableCell>
                            <TableCell className={wrapCellClassName}>{source.configSummary || "-"}</TableCell>
                            <TableCell className={wrapCellClassName}>
                              <SourceGovernanceBadges source={source} />
                            </TableCell>
                            <TableCell className={compactCellClassName}>
                              <Badge
                                variant="secondary"
                                className={source.enabled ? "bg-success/20 text-success" : "bg-muted text-muted-foreground"}
                              >
                                {source.enabled ? "已启用" : "已停用"}
                              </Badge>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              <div>{toDisplayDate(source.lastCheckedAt)}</div>
                              <div className="mt-1 text-[11px]">扫描: {toDisplayDate(source.lastScannedAt)}</div>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                  </div>
                </div>
              </TabsContent>
            </Tabs>

            {(toolsError || sourcesError) && (
              <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <div className="mb-1 font-medium">数据加载存在异常</div>
                <div className="space-y-1 text-xs">
                  {toolsError ? (
                    <div>能力接口 `/api/tools`：{toolsError instanceof Error ? toolsError.message : "未知错误"}</div>
                  ) : null}
                  {sourcesError ? (
                    <div>
                      来源接口 `/api/tool-sources`：{sourcesError instanceof Error ? sourcesError.message : "未知错误"}
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {!toolsLoading && !sourcesLoading && tools.length === 0 && sources.length === 0 ? (
              <div className="mt-4 flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-secondary/20 text-center">
                <Wrench className="mb-3 size-8 text-muted-foreground" />
                <div className="text-sm font-medium text-foreground">工具库暂时为空</div>
                <p className="mt-1 max-w-[520px] text-xs text-muted-foreground">
                  当前未发现可展示的能力或来源。请确认后端已实现 `/api/tools` 与 `/api/tool-sources`，并已完成一次扫描。
                </p>
              </div>
            ) : null}

            {tools.length > 0 ? (
              <div className="text-[11px] text-muted-foreground">
                已扫描能力点总计 {totalScannedCapabilities}。点击“详情”可查看 I/O、权限、配置与最近调用摘要。
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <ToolDetailSheet
        open={toolDetailOpen}
        onOpenChange={setToolDetailOpen}
        tool={selectedTool}
        source={selectedSourceFromTools}
        loading={toolDetailFetching}
      />
      <ToolSourceDetailSheet
        open={sourceDetailOpen}
        onOpenChange={setSourceDetailOpen}
        source={selectedSource}
        relatedToolNames={relatedToolNamesForSource}
      />
    </>
  )
}
