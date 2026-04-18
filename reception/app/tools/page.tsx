"use client"

import { startTransition, useDeferredValue, useMemo, useState } from "react"
import { BrainSkillManagementActions } from "@/components/tools/brain-skill-management-actions"
import { BrainSkillRegistrationActions } from "@/components/tools/brain-skill-registration-actions"
import { ToolDetailSheet, ToolSourceDetailSheet } from "@/components/tools/tool-catalog-detail-sheet"
import { ToolManagementActions, isControlPlaneManagedTool } from "@/components/tools/tool-management-actions"
import { useBrainSkills } from "@/hooks/use-brain-skills"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import type { BrainSkillItem, Tool, ToolHealthStatus, ToolSource, ToolSourceType, ToolType } from "@/types"
import { RefreshCw, Search, Wrench } from "lucide-react"

const BRAIN_PRIVATE_SOURCE_ID = "local-agents"

const toolTypeLabels: Record<ToolType, string> = {
  skill: "技能",
  tool: "工具",
  mcp: "MCP",
  unknown: "未分类",
}

const sourceTypeLabels: Record<ToolSourceType, string> = {
  internal: "内部",
  local_tool: "本地兜底",
  external_repo: "外部仓库",
  mcp_server: "MCP 服务",
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
  retained: "保留中",
  bridging: "接入过渡中",
  externalized: "已外接",
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
  external_only: "全外接",
  hybrid: "混合接入",
  local_only: "本地主导",
  unknown: "未识别",
  mixed: "多种模式",
}

const sourceModeClasses: Record<string, string> = {
  external_only: "bg-primary/15 text-primary",
  hybrid: "bg-warning/20 text-warning-foreground",
  local_only: "bg-secondary text-foreground",
  unknown: "bg-muted text-muted-foreground",
  mixed: "bg-warning/20 text-warning-foreground",
}

function boolLabel(value: boolean) {
  return value ? "是" : "否"
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

function isBrainPrivateTool(tool: Tool) {
  return tool.sourceId === BRAIN_PRIVATE_SOURCE_ID || tool.sourceKind === "local_agents"
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
        <SelectValue placeholder="类型" />
      </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部类型</SelectItem>
          <SelectItem value="internal">内部</SelectItem>
          <SelectItem value="local_tool">本地兜底</SelectItem>
          <SelectItem value="external_repo">外部仓库</SelectItem>
          <SelectItem value="mcp_server">MCP 服务</SelectItem>
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
          启用方式: {source.activationMode}
        </Badge>
      ) : null}
      {source.legacyFallback ? (
        <Badge variant="secondary" className="bg-warning/20 text-xs text-warning-foreground">
          本地兜底
        </Badge>
      ) : null}
      {source.deprecated ? (
        <Badge variant="secondary" className="bg-destructive/15 text-xs text-destructive">
          已弃用
        </Badge>
      ) : null}
      {!mode && !source.activationMode && !source.legacyFallback && !source.deprecated ? (
        <span className="text-xs text-muted-foreground">未声明</span>
      ) : null}
    </div>
  )
}

function getBrainSkillFileName(skill: BrainSkillItem) {
  if (skill.fileName?.trim()) return skill.fileName.trim()
  return skill.name
}

function getBrainSkillFormat(skill: BrainSkillItem) {
  if (skill.format?.trim()) return skill.format.trim().toUpperCase()
  const fileName = getBrainSkillFileName(skill)
  const extension = fileName.includes(".") ? fileName.split(".").pop() ?? "" : ""
  if (extension.trim()) return extension.trim().toUpperCase()
  return "-"
}

function getBrainSkillDescription(skill: BrainSkillItem) {
  return skill.description?.trim() || "-"
}

function getBrainSkillUploadedAt(skill: BrainSkillItem) {
  return skill.uploadedAt ?? null
}

function getBrainSkillCapabilities(skill: BrainSkillItem) {
  const values = [...(skill.capabilities ?? []), ...(skill.tags ?? [])]
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))]
}

function getBrainSkillSearchValues(skill: BrainSkillItem) {
  return [
    skill.name,
    getBrainSkillFileName(skill),
    skill.format,
    skill.description,
    ...(skill.capabilities ?? []),
    ...(skill.tags ?? []),
  ]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase())
}

export default function ToolsPage() {
  const [activeTab, setActiveTab] = useState("tools")
  const [searchQuery, setSearchQuery] = useState("")
  const [toolTypeFilter, setToolTypeFilter] = useState("all")
  const [toolSourceFilter, setToolSourceFilter] = useState("all")
  const [toolEnabledFilter, setToolEnabledFilter] = useState("all")
  const [sourceTypeFilter, setSourceTypeFilter] = useState("all")
  const [sourceNameFilter, setSourceNameFilter] = useState("all")
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
  const {
    data: brainSkillsData,
    isLoading: brainSkillsLoading,
    isFetching: brainSkillsFetching,
    error: brainSkillsError,
    refetch: refetchBrainSkills,
  } = useBrainSkills()

  const tools = toolsData?.items ?? []
  const sources = sourceData?.items ?? []
  const externalTools = tools.filter((tool) => !isBrainPrivateTool(tool))
  const externalSources = sources.filter((source) => source.id !== BRAIN_PRIVATE_SOURCE_ID)
  const brainSkills = brainSkillsData?.items ?? []
  const selectedToolFromList = externalTools.find((tool) => tool.id === selectedToolId) ?? null
  const selectedTool = toolDetailData ?? selectedToolFromList
  const selectedSourceFromTools =
    externalSources.find((source) => source.id === selectedTool?.sourceId) ??
    externalSources.find((source) => source.name === selectedTool?.sourceName) ??
    null
  const selectedSource = sourceDetailData ?? externalSources.find((source) => source.id === selectedSourceId) ?? null

  const toolSourceNameOptions = [...new Set(externalTools.map((tool) => tool.sourceName).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "zh-CN"),
  )
  const sourceNameOptions = [...new Set(externalSources.map((source) => source.name).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "zh-CN"),
  )

  const filteredTools = useMemo(() => {
    const matched = externalTools.filter((tool) => {
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
      const matchesEnabled =
        toolEnabledFilter === "all" ||
        (toolEnabledFilter === "enabled" && tool.enabled) ||
        (toolEnabledFilter === "disabled" && !tool.enabled)

      return matchesSearch && matchesType && matchesSource && matchesEnabled
    })

    return sortToolsByPriority(matched)
  }, [deferredSearch, externalTools, toolEnabledFilter, toolSourceFilter, toolTypeFilter])

  const filteredSources = useMemo(() => {
    const matched = externalSources.filter((source) => {
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
      const matchesSource = sourceNameFilter === "all" || source.name === sourceNameFilter
      const matchesEnabled =
        sourceEnabledFilter === "all" ||
        (sourceEnabledFilter === "enabled" && source.enabled) ||
        (sourceEnabledFilter === "disabled" && !source.enabled)

      return matchesSearch && matchesType && matchesSource && matchesEnabled
    })

    return sortSourcesByPriority(matched)
  }, [deferredSearch, externalSources, sourceEnabledFilter, sourceNameFilter, sourceTypeFilter])

  const filteredBrainSkills = useMemo(() => {
    return brainSkills
      .filter((skill) => {
        if (!deferredSearch) return true
        return getBrainSkillSearchValues(skill).some((value) => value.includes(deferredSearch))
      })
      .sort((left, right) => {
        const uploadedDiff = toTimestamp(getBrainSkillUploadedAt(right)) - toTimestamp(getBrainSkillUploadedAt(left))
        if (uploadedDiff !== 0) return uploadedDiff
        return left.name.localeCompare(right.name, "zh-CN")
      })
  }, [brainSkills, deferredSearch])

  const totalScannedCapabilities = externalTools.reduce((total, tool) => total + tool.capabilityCount, 0)
  const isRefreshing = toolsFetching || sourcesFetching || brainSkillsFetching

  const relatedToolNamesForSource = selectedSource
    ? sortToolsByPriority(
        externalTools.filter((tool) => tool.sourceId === selectedSource.id || tool.sourceName === selectedSource.name),
      ).map((tool) => tool.name)
    : []

  const handleRefresh = async () => {
    await Promise.all([refetchTools(), refetchSources(), refetchBrainSkills()])
    if (selectedToolId) {
      await refetchToolDetail()
    }
  }

  const handleToolDeleted = (toolId: string) => {
    if (selectedToolId === toolId) {
      setSelectedToolId(null)
      setToolDetailOpen(false)
    }
  }

  return (
    <>
      <div className="flex h-full min-h-0 w-full flex-col p-6">
        <Card className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-card">
          <CardContent className="flex min-h-0 min-w-0 flex-1 flex-col space-y-4 p-6">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex min-h-0 w-full flex-1 min-w-0 flex-col">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <TabsList className="grid w-full grid-cols-3 md:w-[520px]">
                  <TabsTrigger value="tools">触手能力</TabsTrigger>
                  <TabsTrigger value="sources">触手来源</TabsTrigger>
                  <TabsTrigger value="brain-skills">主脑 Skill</TabsTrigger>
                </TabsList>

                <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center xl:w-auto">
                  <div className="relative w-full xl:w-80">
                    <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      placeholder={
                        activeTab === "brain-skills"
                          ? "搜索 Skill 名称 / 文件名 / 标签..."
                          : "搜索名称 / 来源 / 关联角色 / 接入说明..."
                      }
                      value={searchQuery}
                      onChange={(event) =>
                        startTransition(() => {
                          setSearchQuery(event.target.value)
                        })
                      }
                      className="w-full bg-secondary pl-10"
                    />
                  </div>
                  {activeTab === "brain-skills" ? <BrainSkillRegistrationActions /> : null}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void handleRefresh()}
                    disabled={isRefreshing}
                    className="shrink-0"
                  >
                    <RefreshCw className={cn("mr-2 size-4", isRefreshing && "animate-spin")} />
                    {isRefreshing ? "同步中..." : "刷新"}
                  </Button>
                </div>
              </div>

              <TabsContent value="tools" className="mt-4 flex min-h-0 min-w-0 flex-1 flex-col space-y-4">
                <div className="shrink-0 flex flex-col gap-3 rounded-xl border border-border bg-secondary/20 p-4 md:flex-row md:flex-wrap md:items-center">
                  <Select value={toolTypeFilter} onValueChange={setToolTypeFilter}>
                    <SelectTrigger className="w-full bg-background sm:w-[150px]">
                      <SelectValue placeholder="能力类型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部类型</SelectItem>
                      <SelectItem value="skill">技能</SelectItem>
                      <SelectItem value="tool">工具</SelectItem>
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
                      {toolSourceNameOptions.map((sourceName) => (
                        <SelectItem key={sourceName} value={sourceName}>
                          {sourceName}
                        </SelectItem>
                      ))}
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
                </div>

                <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-border">
                  <div className="h-full overflow-y-auto">
                  <Table className="min-w-[1760px] table-fixed">
                    <colgroup>
                      <col className="w-[390px]" />
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
                        <TableHead className={tableHeadClassName}>接入阶段</TableHead>
                        <TableHead className={tableHeadClassName}>接入策略</TableHead>
                        <TableHead className={tableHeadClassName}>健康</TableHead>
                        <TableHead className={tableHeadClassName}>关联角色</TableHead>
                        <TableHead className={tableHeadClassName}>接入说明</TableHead>
                        <TableHead className={tableHeadClassName}>调用要求</TableHead>
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
                                  <div className="flex items-center gap-1">
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
                                    {isControlPlaneManagedTool(tool) ? (
                                      <ToolManagementActions tool={tool} onDeleted={handleToolDeleted} />
                                    ) : null}
                                  </div>
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
                                <div className="text-foreground">接入方式: {tool.bridgeMode || "-"}</div>
                                <div className="text-muted-foreground">
                                  流量策略: {tool.trafficPolicy ? "已配置灰度/双跑" : "默认"}
                                </div>
                                <div className="text-muted-foreground">
                                  回滚预案: {tool.rollbackSummary ? "已准备" : "未声明"}
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
                              <div className="font-medium text-foreground">能力点 {tool.capabilityCount}</div>
                              <div className="mt-1">权限控制: {boolLabel(tool.permissions.requiresPermission)}</div>
                              <div>人工审批: {boolLabel(tool.permissions.approvalRequired)}</div>
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
                                成功 {tool.invocationSummary.successCalls} / 失败 {tool.invocationSummary.failedCalls}
                              </div>
                              <div className="text-[11px]">最近结果: {tool.invocationSummary.lastStatus}</div>
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
                  <Select value={sourceNameFilter} onValueChange={setSourceNameFilter}>
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
                        <TableHead className={tableHeadClassName}>接入位置 / 说明</TableHead>
                        <TableHead className={tableHeadClassName}>已扫描能力</TableHead>
                        <TableHead className={tableHeadClassName}>健康</TableHead>
                        <TableHead className={tableHeadClassName}>关联角色</TableHead>
                        <TableHead className={tableHeadClassName}>接入配置</TableHead>
                        <TableHead className={tableHeadClassName}>接入策略</TableHead>
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
                                      本地兜底
                                    </Badge>
                                  ) : null}
                                  {source.deprecated ? (
                                    <Badge variant="secondary" className="bg-destructive/15 text-xs text-destructive">
                                      已弃用
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

              <TabsContent value="brain-skills" className="mt-4 flex min-h-0 min-w-0 flex-1 flex-col space-y-4">
                <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-border">
                  <div className="h-full overflow-y-auto">
                    <Table className="min-w-[1120px] table-fixed">
                      <colgroup>
                        <col className="w-[260px]" />
                        <col className="w-[220px]" />
                        <col className="w-[120px]" />
                        <col className="w-[240px]" />
                        <col className="w-[320px]" />
                        <col className="w-[160px]" />
                        <col className="w-[120px]" />
                      </colgroup>
                      <TableHeader className="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
                        <TableRow className="border-border">
                          <TableHead className={tableHeadClassName}>Skill</TableHead>
                          <TableHead className={tableHeadClassName}>文件名</TableHead>
                          <TableHead className={tableHeadClassName}>格式</TableHead>
                          <TableHead className={tableHeadClassName}>能力 / 标签</TableHead>
                          <TableHead className={tableHeadClassName}>说明</TableHead>
                          <TableHead className={tableHeadClassName}>上传时间</TableHead>
                          <TableHead className={tableHeadClassName}>操作</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {brainSkillsLoading ? (
                          Array.from({ length: 6 }).map((_, index) => (
                            <TableRow key={`brain-skill-skeleton-${index}`}>
                              <TableCell colSpan={7}>
                                <Skeleton className="h-7 w-full" />
                              </TableCell>
                            </TableRow>
                          ))
                        ) : filteredBrainSkills.length === 0 ? (
                          <EmptyRow
                            colSpan={7}
                            title="还没有本地 Skill"
                            description="点击右上角上传 Skill 文件。"
                          />
                        ) : (
                          filteredBrainSkills.map((skill) => (
                            <TableRow key={skill.id} className="border-border">
                              <TableCell className={wrapCellClassName}>
                                <div className="space-y-2">
                                  <div className="font-medium text-foreground">{skill.name}</div>
                                  {skill.description ? (
                                    <div className="text-xs leading-5 text-muted-foreground">{skill.description}</div>
                                  ) : null}
                                  {skill.enabled === false ? (
                                    <Badge variant="secondary" className="w-fit bg-muted text-xs text-muted-foreground">
                                      已停用
                                    </Badge>
                                  ) : null}
                                </div>
                              </TableCell>
                              <TableCell className={wrapCellClassName}>
                                <div className="text-sm text-foreground">{getBrainSkillFileName(skill)}</div>
                              </TableCell>
                              <TableCell className={compactCellClassName}>
                                <Badge variant="secondary">{getBrainSkillFormat(skill)}</Badge>
                              </TableCell>
                              <TableCell className={wrapCellClassName}>
                                <div className="flex flex-wrap gap-1">
                                  {getBrainSkillCapabilities(skill).length > 0 ? (
                                    getBrainSkillCapabilities(skill).map((item) => (
                                      <Badge key={`${skill.id}-${item}`} variant="secondary" className="text-xs">
                                        {item}
                                      </Badge>
                                    ))
                                  ) : (
                                    <span className="text-xs text-muted-foreground">未解析</span>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className={wrapCellClassName}>
                                <div className="text-sm leading-6 text-foreground">{getBrainSkillDescription(skill)}</div>
                              </TableCell>
                              <TableCell className="align-top text-xs text-muted-foreground">
                                {toDisplayDate(getBrainSkillUploadedAt(skill))}
                              </TableCell>
                              <TableCell className="align-top">
                                <BrainSkillManagementActions skill={skill} />
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

            {(toolsError || sourcesError || brainSkillsError) && (
              <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <div className="mb-1 font-medium">数据加载存在异常</div>
                <div className="space-y-1 text-xs">
                  {toolsError ? (
                    <div>触手能力接口 `/api/tools`：{toolsError instanceof Error ? toolsError.message : "未知错误"}</div>
                  ) : null}
                  {sourcesError ? (
                    <div>
                      触手来源接口 `/api/tool-sources`：{sourcesError instanceof Error ? sourcesError.message : "未知错误"}
                    </div>
                  ) : null}
                  {brainSkillsError ? (
                    <div>
                      主脑 Skill 接口 `/api/agents/brain-skills`：
                      {brainSkillsError instanceof Error ? brainSkillsError.message : "未知错误"}
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {!toolsLoading && !sourcesLoading && externalTools.length === 0 && externalSources.length === 0 && activeTab !== "brain-skills" ? (
              <div className="mt-4 flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-secondary/20 text-center">
                <Wrench className="mb-3 size-8 text-muted-foreground" />
                <div className="text-sm font-medium text-foreground">外部触手中心暂时为空</div>
                <p className="mt-1 max-w-[520px] text-xs text-muted-foreground">
                  当前未发现可展示的能力或来源。请确认后端已实现 `/api/tools` 与 `/api/tool-sources`，并已完成一次扫描。
                </p>
              </div>
            ) : null}

            {externalTools.length > 0 && activeTab !== "brain-skills" ? (
              <div className="text-[11px] text-muted-foreground">
                已扫描能力点总计 {totalScannedCapabilities}。点击“详情”可查看输入输出、权限要求、接入说明和最近调用摘要。
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
