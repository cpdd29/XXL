"use client"

import Link from "next/link"
import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react"
import { BrainSkillManagementActions } from "@/modules/capability/components/brain-skill-management-actions"
import { BrainSkillRegistrationActions } from "@/modules/capability/components/brain-skill-registration-actions"
import { ToolDetailSheet } from "@/modules/capability/components/tool-catalog-detail-sheet"
import { ToolRegistrationActions } from "@/modules/capability/components/tool-registration-actions"
import { ToolManagementActions, isControlPlaneManagedTool } from "@/modules/capability/components/tool-management-actions"
import { useBrainSkills, useUpdateBrainSkillScope } from "@/modules/capability/hooks/use-brain-skills"
import { toast } from "@/shared/hooks/use-toast"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent } from "@/shared/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Skeleton } from "@/shared/ui/skeleton"
import { Switch } from "@/shared/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui/table"
import { useToolSources, useUpdateToolMcp } from "@/modules/capability/hooks/use-tool-sources"
import { useToolDetail, useTools } from "@/modules/capability/hooks/use-tools"
import { cn } from "@/shared/utils"
import type { BrainSkillItem, CapabilityScope, Tool, ToolHealthStatus, ToolSourceType, ToolType } from "@/shared/types"
import { RefreshCw, Search } from "lucide-react"

const LOCAL_MCP_SOURCE_ID = "local-mcp-services"
const CONTROL_PLANE_MCP_SOURCE_ID = "control-plane-mcp-registry"
const pageSizeOptions = ["10", "20", "50"] as const

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

const scopeFilterOptions = ["all", "global", "tenant"] as const
type ScopeFilterOption = (typeof scopeFilterOptions)[number]

const capabilityScopeLabel: Record<CapabilityScope, string> = {
  global: "通用",
  tenant: "专用",
  unknown: "未标记",
}

const capabilityScopeClass: Record<CapabilityScope, string> = {
  global: "bg-primary/15 text-primary",
  tenant: "bg-warning/20 text-warning-foreground",
  unknown: "bg-muted text-muted-foreground",
}

const capabilityScopeSortOrder: Record<CapabilityScope, number> = {
  tenant: 1,
  global: 2,
  unknown: 3,
}

function boolLabel(value: boolean) {
  return value ? "是" : "否"
}

function getConfigString(config: Record<string, unknown> | null, keys: string[], fallback = "") {
  if (!config) return fallback
  for (const key of keys) {
    const value = config[key]
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return fallback
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

function isRecentlyInvoked(tool: Tool) {
  return tool.invocationSummary.callCount > 0 || Boolean(tool.invocationSummary.lastCalledAt)
}

function isBrainMcpTool(tool: Tool) {
  if (tool.type !== "mcp") {
    return false
  }

  return (
    tool.sourceType === "mcp_server" ||
    tool.sourceKind === "mcp_server" ||
    tool.sourceId === LOCAL_MCP_SOURCE_ID ||
    tool.sourceId === CONTROL_PLANE_MCP_SOURCE_ID ||
    isControlPlaneManagedTool(tool)
  )
}

function normalizeCapabilityScope(value: unknown): CapabilityScope {
  if (typeof value !== "string") return "unknown"
  const normalized = value.trim().toLowerCase().replace(/-/g, "_")
  if (["global", "public", "shared", "platform"].includes(normalized)) return "global"
  if (["tenant", "private", "dedicated", "tenant_private"].includes(normalized)) return "tenant"
  return "unknown"
}

function normalizeOwnerTenantId(value: unknown) {
  if (typeof value !== "string") return null
  const trimmed = value.trim()
  return trimmed || null
}

function toEditableScopePayload(scope: CapabilityScope): "shared" | "tenant" | null {
  if (scope === "global") return "shared"
  if (scope === "tenant") return "tenant"
  return null
}

function resolveBrainSkillScope(skill: BrainSkillItem): CapabilityScope {
  const row = skill as unknown as Record<string, unknown>
  return normalizeCapabilityScope(row.scope ?? row.capabilityScope ?? row.capability_scope)
}

function resolveBrainSkillOwnerTenantId(skill: BrainSkillItem) {
  const row = skill as unknown as Record<string, unknown>
  return normalizeOwnerTenantId(
    row.ownerTenantId ?? row.owner_tenant_id ?? row.tenantId ?? row.tenant_id,
  )
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

function CapabilityScopeBadge({ scope }: { scope: CapabilityScope }) {
  return (
    <Badge variant="secondary" className={cn("text-xs", capabilityScopeClass[scope])}>
      {capabilityScopeLabel[scope]}
    </Badge>
  )
}

function CapabilityScopeEditor({
  title,
  description,
  scope,
  ownerTenantId,
  disabled = false,
  isSaving = false,
  onSave,
}: {
  title: string
  description?: string
  scope: CapabilityScope
  ownerTenantId: string | null
  disabled?: boolean
  isSaving?: boolean
  onSave: (payload: { scope: CapabilityScope; ownerTenantId: string | null }) => Promise<string | void>
}) {
  const [open, setOpen] = useState(false)
  const [draftScope, setDraftScope] = useState<CapabilityScope>(scope)
  const [draftTenantId, setDraftTenantId] = useState(ownerTenantId ?? "")

  const normalizedTenantId = draftTenantId.trim() || null

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-7 px-2 text-xs"
        disabled={disabled}
        onClick={() => {
          setDraftScope(scope)
          setDraftTenantId(ownerTenantId ?? "")
          setOpen(true)
        }}
      >
        作用域
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              {description || "修改并保存能力作用域与所属租户。"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>作用域</Label>
              <Select value={draftScope} onValueChange={(value) => setDraftScope(value as CapabilityScope)}>
                <SelectTrigger>
                  <SelectValue placeholder="选择作用域" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">通用</SelectItem>
                  <SelectItem value="tenant">专用</SelectItem>
                  <SelectItem value="unknown">未标记</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>所属租户 ID（专用可选）</Label>
              <Input
                placeholder="例如 tenant_acme"
                value={draftTenantId}
                onChange={(event) => setDraftTenantId(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={isSaving}
            >
              取消
            </Button>
            <Button
              disabled={disabled || isSaving}
              onClick={async () => {
                try {
                  const message = await onSave({
                    scope: draftScope,
                    ownerTenantId: draftScope === "tenant" ? normalizedTenantId : null,
                  })
                  toast({
                    title: "作用域已更新",
                    description: message || "已保存最新作用域配置。",
                  })
                  setOpen(false)
                } catch (error) {
                  const message = error instanceof Error ? error.message : "保存失败"
                  toast({
                    title: "作用域更新失败",
                    description: message,
                    variant: "destructive",
                  })
                }
              }}
            >
              {isSaving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
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

function clampPage(currentPage: number, totalPages: number) {
  return Math.min(Math.max(currentPage, 1), Math.max(totalPages, 1))
}

function paginateItems<T>(items: T[], currentPage: number, pageSize: number) {
  const startIndex = (currentPage - 1) * pageSize
  return items.slice(startIndex, startIndex + pageSize)
}

function TablePaginationFooter({
  totalItems,
  currentPage,
  totalPages,
  pageSize,
  currentCount,
  onPageChange,
  onPageSizeChange,
}: {
  totalItems: number
  currentPage: number
  totalPages: number
  pageSize: (typeof pageSizeOptions)[number]
  currentCount: number
  onPageChange: (page: number) => void
  onPageSizeChange: (value: (typeof pageSizeOptions)[number]) => void
}) {
  return (
    <div className="flex shrink-0 flex-col gap-3 border-t border-border bg-card px-4 py-3 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-col gap-3 text-xs text-muted-foreground md:flex-row md:items-center md:gap-4">
        <span>
          共 {totalItems} 条，当前第 {currentPage} / {totalPages} 页
        </span>
        <span>当前显示 {currentCount} 条</span>
        <Select value={pageSize} onValueChange={onPageSizeChange}>
          <SelectTrigger className="h-8 w-[140px] bg-secondary text-xs">
            <SelectValue placeholder="每页条数" />
          </SelectTrigger>
          <SelectContent>
            {pageSizeOptions.map((option) => (
              <SelectItem key={option} value={option}>
                每页 {option} 条
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
        >
          上一页
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}

const tableHeadClassName = "bg-secondary/40 text-muted-foreground"
const wrapCellClassName = "align-top whitespace-normal break-words"
const compactCellClassName = "align-top"

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
  const [activeTab, setActiveTab] = useState("brain-mcp")
  const [searchQuery, setSearchQuery] = useState("")
  const [scopeFilter, setScopeFilter] = useState<ScopeFilterOption>("all")
  const [mcpPage, setMcpPage] = useState(1)
  const [mcpPageSize, setMcpPageSize] = useState<(typeof pageSizeOptions)[number]>("10")
  const [skillPage, setSkillPage] = useState(1)
  const [skillPageSize, setSkillPageSize] = useState<(typeof pageSizeOptions)[number]>("10")
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null)
  const [toolDetailOpen, setToolDetailOpen] = useState(false)
  const [updatingEnabledToolId, setUpdatingEnabledToolId] = useState<string | null>(null)
  const [updatingScopeKey, setUpdatingScopeKey] = useState<string | null>(null)
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
    isFetching: sourcesFetching,
    error: sourcesError,
    refetch: refetchSources,
  } = useToolSources()
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
  const updateBrainSkillScope = useUpdateBrainSkillScope()
  const updateMcp = useUpdateToolMcp()

  const tools = toolsData?.items ?? []
  const sources = sourceData?.items ?? []
  const brainMcpTools = tools.filter(isBrainMcpTool)
  const brainSkills = useMemo(() => brainSkillsData?.items ?? [], [brainSkillsData?.items])
  const selectedToolFromList = brainMcpTools.find((tool) => tool.id === selectedToolId) ?? null
  const selectedTool = toolDetailData ?? selectedToolFromList
  const selectedSourceFromTools =
    sources.find((source) => source.id === selectedTool?.sourceId) ??
    sources.find((source) => source.name === selectedTool?.sourceName) ??
    null

  const filteredBrainMcpTools = useMemo(() => {
    const matched = brainMcpTools.filter((tool) => {
      const matchesScope = scopeFilter === "all" ? true : tool.scope === scopeFilter
      const matchesSearch =
        !deferredSearch ||
        tool.name.toLowerCase().includes(deferredSearch) ||
        tool.description.toLowerCase().includes(deferredSearch) ||
        tool.sourceName.toLowerCase().includes(deferredSearch) ||
        tool.providerSummary.toLowerCase().includes(deferredSearch) ||
        tool.configSummary.toLowerCase().includes(deferredSearch) ||
        tool.invocationSummary.summary.toLowerCase().includes(deferredSearch) ||
        tool.linkedAgents.some((agent) => agent.toLowerCase().includes(deferredSearch)) ||
        tool.requiredCapabilities.some((capability) => capability.toLowerCase().includes(deferredSearch))

      return matchesScope && matchesSearch
    })

    return sortToolsByPriority(matched).sort((left, right) => {
      const scopeDiff = capabilityScopeSortOrder[left.scope] - capabilityScopeSortOrder[right.scope]
      if (scopeDiff !== 0) return scopeDiff
      return left.name.localeCompare(right.name, "zh-CN")
    })
  }, [brainMcpTools, deferredSearch, scopeFilter])

  const filteredBrainSkills = useMemo(() => {
    return brainSkills
      .filter((skill) => {
        const skillScope = resolveBrainSkillScope(skill)
        const matchesScope = scopeFilter === "all" ? true : skillScope === scopeFilter
        if (!matchesScope) return false
        if (!deferredSearch) return true
        return getBrainSkillSearchValues(skill).some((value) => value.includes(deferredSearch))
      })
      .sort((left, right) => {
        const scopeDiff =
          capabilityScopeSortOrder[resolveBrainSkillScope(left)] -
          capabilityScopeSortOrder[resolveBrainSkillScope(right)]
        if (scopeDiff !== 0) return scopeDiff
        const uploadedDiff = toTimestamp(getBrainSkillUploadedAt(right)) - toTimestamp(getBrainSkillUploadedAt(left))
        if (uploadedDiff !== 0) return uploadedDiff
        return left.name.localeCompare(right.name, "zh-CN")
      })
  }, [brainSkills, deferredSearch, scopeFilter])

  const mcpLimit = Number(mcpPageSize)
  const skillLimit = Number(skillPageSize)
  const totalMcpPages = Math.max(1, Math.ceil(filteredBrainMcpTools.length / mcpLimit))
  const totalSkillPages = Math.max(1, Math.ceil(filteredBrainSkills.length / skillLimit))
  const paginatedBrainMcpTools = useMemo(
    () => paginateItems(filteredBrainMcpTools, mcpPage, mcpLimit),
    [filteredBrainMcpTools, mcpLimit, mcpPage],
  )
  const paginatedBrainSkills = useMemo(
    () => paginateItems(filteredBrainSkills, skillPage, skillLimit),
    [filteredBrainSkills, skillLimit, skillPage],
  )
  const totalScannedCapabilities = brainMcpTools.reduce((total, tool) => total + tool.capabilityCount, 0)
  const isRefreshing = toolsFetching || sourcesFetching || brainSkillsFetching

  useEffect(() => {
    setMcpPage(1)
    setSkillPage(1)
  }, [deferredSearch])

  useEffect(() => {
    setMcpPage((currentPage) => clampPage(currentPage, totalMcpPages))
  }, [totalMcpPages])

  useEffect(() => {
    setSkillPage((currentPage) => clampPage(currentPage, totalSkillPages))
  }, [totalSkillPages])

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

  const handleToggleEnabled = async (tool: Tool, checked: boolean) => {
    if (!isControlPlaneManagedTool(tool)) return
    const baseUrl = getConfigString(tool.configDetail, ["base_url", "baseUrl"])
    if (!tool.name.trim() || !baseUrl) {
      toast({
        title: "更新失败",
        description: "当前 MCP 缺少必要接入信息（名称或服务地址）。",
        variant: "destructive",
      })
      return
    }

    setUpdatingEnabledToolId(tool.id)
    try {
      const response = await updateMcp.mutateAsync({
        toolId: tool.id,
        payload: {
          name: tool.name.trim(),
          baseUrl,
          enabled: checked,
        },
      })
      toast({
        title: checked ? "已启用 MCP" : "已停用 MCP",
        description: response.message,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : "状态更新失败"
      toast({
        title: "状态更新失败",
        description: message,
        variant: "destructive",
      })
    } finally {
      setUpdatingEnabledToolId(null)
    }
  }

  const handleUpdateMcpScope = async ({
    tool,
    scope,
    ownerTenantId,
  }: {
    tool: Tool
    scope: CapabilityScope
    ownerTenantId: string | null
  }) => {
    if (!isControlPlaneManagedTool(tool)) {
      throw new Error("当前 MCP 来源不支持在此页面直接更新作用域。")
    }
    const payloadScope = toEditableScopePayload(scope)
    if (!payloadScope) {
      throw new Error("请先选择“通用”或“专用”作用域后再保存。")
    }
    const baseUrl = getConfigString(tool.configDetail, ["base_url", "baseUrl"])
    if (!tool.name.trim() || !baseUrl) {
      throw new Error("当前 MCP 缺少必要接入信息（名称或服务地址）。")
    }

    const key = `mcp:${tool.id}`
    setUpdatingScopeKey(key)
    try {
      const response = await updateMcp.mutateAsync({
        toolId: tool.id,
        payload: {
          name: tool.name.trim(),
          baseUrl,
          scope: payloadScope,
          ownerTenantId: payloadScope === "tenant" ? ownerTenantId : null,
        },
      })
      return response.message
    } finally {
      setUpdatingScopeKey((current) => (current === key ? null : current))
    }
  }

  const handleUpdateSkillScope = async ({
    skillId,
    scope,
    ownerTenantId,
  }: {
    skillId: string
    scope: CapabilityScope
    ownerTenantId: string | null
  }) => {
    const payloadScope = toEditableScopePayload(scope)
    if (!payloadScope) {
      throw new Error("请先选择“通用”或“专用”作用域后再保存。")
    }

    const key = `skill:${skillId}`
    setUpdatingScopeKey(key)
    try {
      const response = await updateBrainSkillScope.mutateAsync({
        skillId,
        payload: {
          scope: payloadScope,
          ownerTenantId: payloadScope === "tenant" ? ownerTenantId : null,
        },
      })
      return response.message
    } finally {
      setUpdatingScopeKey((current) => (current === key ? null : current))
    }
  }

  return (
    <>
      <div className="flex h-full min-h-0 w-full flex-col p-6">
        <Card className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-card">
          <CardContent className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-hidden p-6">
            <Tabs
              value={activeTab}
              onValueChange={setActiveTab}
              className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden"
            >
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <TabsList className="grid w-full grid-cols-2 md:w-[360px]">
                  <TabsTrigger value="brain-mcp">主脑 MCP</TabsTrigger>
                  <TabsTrigger value="brain-skills">主脑 Skill</TabsTrigger>
                </TabsList>

                <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center xl:w-auto">
                  <div className="relative w-full xl:w-80">
                    <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      placeholder={
                        activeTab === "brain-skills"
                          ? "搜索 Skill 名称 / 文件名 / 标签..."
                          : "搜索 MCP 名称 / 来源 / 关联角色 / 接入说明..."
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
                  <Select value={scopeFilter} onValueChange={(value) => setScopeFilter(value as ScopeFilterOption)}>
                    <SelectTrigger className="w-full bg-secondary sm:w-[150px]">
                      <SelectValue placeholder="作用域筛选" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部作用域</SelectItem>
                      <SelectItem value="global">仅通用</SelectItem>
                      <SelectItem value="tenant">仅专用</SelectItem>
                    </SelectContent>
                  </Select>
                  {activeTab === "brain-skills" ? (
                    <BrainSkillRegistrationActions />
                  ) : (
                    <ToolRegistrationActions mode="mcp-only" />
                  )}
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
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link href="/settings/admission-template">客户准入模板</Link>
                </Button>
              </div>

              <TabsContent value="brain-mcp" className="mt-4 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-border">
                  <div className="min-h-0 flex-1 overflow-auto">
                    <Table className="min-w-[1840px] table-fixed">
                      <colgroup>
                        <col className="w-[96px]" />
                        <col className="w-[390px]" />
                        <col className="w-[96px]" />
                        <col className="w-[160px]" />
                        <col className="w-[140px]" />
                        <col className="w-[170px]" />
                        <col className="w-[160px]" />
                        <col className="w-[180px]" />
                        <col className="w-[220px]" />
                        <col className="w-[120px]" />
                        <col className="w-[180px]" />
                        <col className="w-[120px]" />
                        <col className="w-[160px]" />
                      </colgroup>
                      <TableHeader className="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
                        <TableRow className="border-border">
                          <TableHead className={tableHeadClassName}>是否启用</TableHead>
                          <TableHead className={tableHeadClassName}>能力</TableHead>
                          <TableHead className={tableHeadClassName}>类型</TableHead>
                          <TableHead className={tableHeadClassName}>来源</TableHead>
                          <TableHead className={tableHeadClassName}>接入阶段</TableHead>
                          <TableHead className={tableHeadClassName}>接入策略</TableHead>
                          <TableHead className={tableHeadClassName}>健康</TableHead>
                          <TableHead className={tableHeadClassName}>关联角色</TableHead>
                          <TableHead className={tableHeadClassName}>接入说明</TableHead>
                          <TableHead className={tableHeadClassName}>调用要求</TableHead>
                          <TableHead className={tableHeadClassName}>作用域</TableHead>
                          <TableHead className={tableHeadClassName}>状态</TableHead>
                          <TableHead className={tableHeadClassName}>最近调用 / 扫描</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {toolsLoading ? (
                          Array.from({ length: 6 }).map((_, index) => (
                            <TableRow key={`tool-skeleton-${index}`}>
                              <TableCell colSpan={13}>
                              <Skeleton className="h-7 w-full" />
                            </TableCell>
                          </TableRow>
                        ))
                        ) : paginatedBrainMcpTools.length === 0 ? (
                          <EmptyRow
                            colSpan={13}
                            title="没有匹配的主脑 MCP"
                            description="请修改搜索条件，或先在右上角新增 MCP。"
                          />
                        ) : (
                          paginatedBrainMcpTools.map((tool) => (
                            <TableRow key={tool.id} className="border-border">
                              <TableCell className={compactCellClassName}>
                                <div className="flex items-center gap-2">
                                  <Switch
                                    checked={tool.enabled}
                                    disabled={
                                      !isControlPlaneManagedTool(tool) ||
                                      updateMcp.isPending ||
                                      updatingEnabledToolId === tool.id
                                    }
                                    onCheckedChange={(checked) => {
                                      void handleToggleEnabled(tool, checked)
                                    }}
                                  />
                                  <span className="text-xs text-muted-foreground">{tool.enabled ? "启用" : "停用"}</span>
                                </div>
                              </TableCell>
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
                                <div className="text-xs text-muted-foreground">
                                  {sourceTypeLabels[tool.sourceType]} / {tool.sourceKind}
                                </div>
                              </TableCell>
                              <TableCell className={compactCellClassName}>
                                <Badge
                                  variant="secondary"
                                  className={cn("text-xs", migrationStageClass[tool.migrationStage])}
                                >
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
                              <TableCell className={wrapCellClassName}>
                                <div className="space-y-2">
                                  <CapabilityScopeBadge scope={tool.scope} />
                                  <div className="text-[11px] text-muted-foreground">
                                    {tool.ownerTenantId ? `租户: ${tool.ownerTenantId}` : "租户: -"}
                                  </div>
                                  <CapabilityScopeEditor
                                    title={`编辑 MCP 作用域：${tool.name}`}
                                    description={
                                      isControlPlaneManagedTool(tool)
                                        ? "修改后将通过 MCP 管理接口持久化 scope / ownerTenantId。"
                                        : "当前来源为只读能力，不支持在此页面修改作用域。"
                                    }
                                    scope={tool.scope}
                                    ownerTenantId={tool.ownerTenantId}
                                    disabled={!isControlPlaneManagedTool(tool)}
                                    isSaving={updatingScopeKey === `mcp:${tool.id}`}
                                    onSave={({ scope, ownerTenantId }) =>
                                      handleUpdateMcpScope({ tool, scope, ownerTenantId })
                                    }
                                  />
                                </div>
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
                                <div className="mt-1 text-[11px]">扫描: {toDisplayDate(tool.lastScannedAt)}</div>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </div>
                  <TablePaginationFooter
                    totalItems={filteredBrainMcpTools.length}
                    currentPage={mcpPage}
                    totalPages={totalMcpPages}
                    pageSize={mcpPageSize}
                    currentCount={paginatedBrainMcpTools.length}
                    onPageChange={setMcpPage}
                    onPageSizeChange={(value) => {
                      setMcpPageSize(value)
                      setMcpPage(1)
                    }}
                  />
                </div>
              </TabsContent>

              <TabsContent value="brain-skills" className="mt-4 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-border">
                  <div className="min-h-0 flex-1 overflow-auto">
                    <Table className="min-w-[1120px] table-fixed">
                      <colgroup>
                        <col className="w-[260px]" />
                        <col className="w-[220px]" />
                        <col className="w-[120px]" />
                        <col className="w-[240px]" />
                        <col className="w-[220px]" />
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
                          <TableHead className={tableHeadClassName}>作用域</TableHead>
                          <TableHead className={tableHeadClassName}>说明</TableHead>
                          <TableHead className={tableHeadClassName}>上传时间</TableHead>
                          <TableHead className={tableHeadClassName}>操作</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {brainSkillsLoading ? (
                          Array.from({ length: 6 }).map((_, index) => (
                            <TableRow key={`brain-skill-skeleton-${index}`}>
                              <TableCell colSpan={8}>
                              <Skeleton className="h-7 w-full" />
                            </TableCell>
                          </TableRow>
                        ))
                        ) : paginatedBrainSkills.length === 0 ? (
                          <EmptyRow
                            colSpan={8}
                            title="还没有本地 Skill"
                            description="点击右上角上传 Skill 文件。"
                          />
                        ) : (
                          paginatedBrainSkills.map((skill) => (
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
                                <div className="space-y-2">
                                  <CapabilityScopeBadge scope={resolveBrainSkillScope(skill)} />
                                  <div className="text-[11px] text-muted-foreground">
                                    {resolveBrainSkillOwnerTenantId(skill)
                                      ? `租户: ${resolveBrainSkillOwnerTenantId(skill)}`
                                      : "租户: -"}
                                  </div>
                                  <CapabilityScopeEditor
                                    title={`编辑 Skill 作用域：${skill.name}`}
                                    description="修改后将通过 Skill 管理接口持久化 scope / ownerTenantId。"
                                    scope={resolveBrainSkillScope(skill)}
                                    ownerTenantId={resolveBrainSkillOwnerTenantId(skill)}
                                    isSaving={updatingScopeKey === `skill:${skill.id}`}
                                    onSave={({ scope, ownerTenantId }) =>
                                      handleUpdateSkillScope({ skillId: skill.id, scope, ownerTenantId })
                                    }
                                  />
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
                  <TablePaginationFooter
                    totalItems={filteredBrainSkills.length}
                    currentPage={skillPage}
                    totalPages={totalSkillPages}
                    pageSize={skillPageSize}
                    currentCount={paginatedBrainSkills.length}
                    onPageChange={setSkillPage}
                    onPageSizeChange={(value) => {
                      setSkillPageSize(value)
                      setSkillPage(1)
                    }}
                  />
                </div>
              </TabsContent>
            </Tabs>

            {(toolsError || sourcesError || brainSkillsError) && (
                <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <div className="mb-1 font-medium">数据加载存在异常</div>
                <div className="space-y-1 text-xs">
                  {toolsError ? (
                    <div>主脑 MCP 接口 `/api/tools`：{toolsError instanceof Error ? toolsError.message : "未知错误"}</div>
                  ) : null}
                  {sourcesError ? (
                    <div>
                      MCP 来源接口 `/api/tool-sources`：{sourcesError instanceof Error ? sourcesError.message : "未知错误"}
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

            {brainMcpTools.length > 0 && activeTab === "brain-mcp" ? (
              <div className="text-[11px] text-muted-foreground">
                当前共接入 {brainMcpTools.length} 个主脑 MCP，已声明能力点总计 {totalScannedCapabilities}。
                已支持按作用域筛选排序，点击“作用域”可直接保存更新。
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
    </>
  )
}
