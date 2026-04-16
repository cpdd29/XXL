"use client"

import { startTransition, useDeferredValue, useEffect, useState } from "react"
import { Activity, Bot, RefreshCw, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/hooks/use-auth"
import {
  useExternalAgentVersions,
  useExternalCapabilityAuditLogs,
  useExternalCapabilityGovernanceOverview,
  useExternalSkillVersions,
  usePromoteExternalAgentVersion,
  usePromoteExternalSkillVersion,
  useSetExternalAgentDeprecated,
  useSetExternalAgentFallback,
  useSetExternalAgentRollbackPolicy,
  useSetExternalAgentRolloutPolicy,
  useSetExternalSkillDeprecated,
  useSetExternalSkillFallback,
  useSetExternalSkillRollbackPolicy,
  useSetExternalSkillRolloutPolicy,
} from "@/hooks/use-external-connections"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"
import type {
  AuditLog,
  ExternalCapabilityGovernanceFamilySummary,
  ExternalCapabilityType,
  ExternalCapabilityVersionItem,
} from "@/types"

const capabilityLabels: Record<ExternalCapabilityType, string> = {
  agent: "Agent",
  skill: "Skill",
}

const statusTone: Record<string, string> = {
  online: "bg-success/15 text-success",
  healthy: "bg-success/15 text-success",
  idle: "bg-success/15 text-success",
  degraded: "bg-warning/20 text-warning-foreground",
  disabled: "bg-muted text-muted-foreground",
  offline: "bg-destructive/15 text-destructive",
  unknown: "bg-muted text-muted-foreground",
  open: "bg-destructive/15 text-destructive",
}

const channelTone: Record<string, string> = {
  stable: "bg-success/15 text-success",
  canary: "bg-warning/20 text-warning-foreground",
  beta: "bg-warning/20 text-warning-foreground",
  deprecated: "bg-muted text-muted-foreground",
}

type GovernanceHealthFilter = "all" | "healthy" | "degraded" | "offline" | "open"
type GovernanceRouteFilter = "all" | "routable" | "non_routable" | "deprecated"

function toDisplayDate(value: string | null | undefined) {
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

function normalizeTone(value: string | null | undefined) {
  const normalized = String(value || "unknown").trim().toLowerCase()
  return statusTone[normalized] ?? "bg-secondary text-secondary-foreground"
}

function normalizeChannelTone(value: string | null | undefined) {
  const normalized = String(value || "unknown").trim().toLowerCase()
  return channelTone[normalized] ?? "bg-secondary text-secondary-foreground"
}

function normalizedCapabilityStatus(value: string | null | undefined) {
  return String(value || "unknown").trim().toLowerCase()
}

function governanceHealthState(item: ExternalCapabilityGovernanceFamilySummary): GovernanceHealthFilter {
  if ((item.circuitState || "").trim().toLowerCase() === "open") return "open"
  const normalizedStatus = normalizedCapabilityStatus(item.status)
  if (["online", "healthy", "idle"].includes(normalizedStatus)) return "healthy"
  if (normalizedStatus === "degraded") return "degraded"
  return "offline"
}

function governanceRiskScore(item: ExternalCapabilityGovernanceFamilySummary) {
  let score = 0
  if ((item.circuitState || "").trim().toLowerCase() === "open") score += 50
  if (!item.routable) score += 30
  if (governanceHealthState(item) === "offline") score += 20
  if (governanceHealthState(item) === "degraded") score += 12
  if ((item.releaseChannel || "").trim().toLowerCase() === "canary") score += 6
  if (item.deprecated) score += 4
  return score
}

function rolloutSummary(policy: { canaryPercent: number; routeKey: string } | null | undefined) {
  if (!policy) return "未配置"
  return `${policy.canaryPercent}% · ${policy.routeKey || "global"}`
}

function rollbackSummary(policy: { active: boolean; targetVersionId: string | null } | null | undefined) {
  if (!policy) return "未配置"
  if (!policy.active) return `关闭 · ${policy.targetVersionId || "未指定"}`
  return `启用 · ${policy.targetVersionId || "未指定"}`
}

function mutationErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "未知错误"
}

function EmptyState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="rounded-lg border border-border bg-secondary/20 p-8 text-center">
      <div className="text-sm font-medium text-foreground">{title}</div>
      <div className="mt-1 text-xs text-muted-foreground">{description}</div>
    </div>
  )
}

function SummaryCard({
  title,
  value,
  hint,
}: {
  title: string
  value: number
  hint: string
}) {
  return (
    <Card className="bg-card">
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground">{title}</div>
        <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
        <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
      </CardContent>
    </Card>
  )
}

function buildRelatedAudits(
  audits: AuditLog[],
  versions: ExternalCapabilityVersionItem[],
) {
  if (versions.length === 0) return []
  const versionIds = new Set(versions.map((item) => item.id))
  return audits.filter((audit) => {
    for (const versionId of versionIds) {
      if (audit.resource.includes(versionId) || audit.details.includes(versionId)) {
        return true
      }
    }
    return false
  })
}

export default function ExternalCapabilitiesPage() {
  const { hasPermission } = useAuth()
  const canManageExternal = hasPermission("external:write")

  const [activeTab, setActiveTab] = useState<ExternalCapabilityType>("agent")
  const [search, setSearch] = useState("")
  const deferredSearch = useDeferredValue(search)
  const [healthFilter, setHealthFilter] = useState<GovernanceHealthFilter>("all")
  const [routeFilter, setRouteFilter] = useState<GovernanceRouteFilter>("all")
  const [channelFilter, setChannelFilter] = useState("all")
  const [selection, setSelection] = useState<{
    capabilityType: ExternalCapabilityType
    family: string
  } | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState("")
  const [fallbackVersionId, setFallbackVersionId] = useState("none")
  const [rolloutPercent, setRolloutPercent] = useState("0")
  const [routeKey, setRouteKey] = useState("global")
  const [rollbackActive, setRollbackActive] = useState(false)
  const [rollbackTargetVersionId, setRollbackTargetVersionId] = useState("none")
  const [deprecated, setDeprecated] = useState(false)

  const overview = useExternalCapabilityGovernanceOverview()
  const globalAudits = useExternalCapabilityAuditLogs({ limit: 80 })
  const agentVersions = useExternalAgentVersions(
    selection?.capabilityType === "agent" ? selection.family : null,
  )
  const skillVersions = useExternalSkillVersions(
    selection?.capabilityType === "skill" ? selection.family : null,
  )

  const promoteAgentVersion = usePromoteExternalAgentVersion()
  const promoteSkillVersion = usePromoteExternalSkillVersion()
  const setAgentFallback = useSetExternalAgentFallback()
  const setSkillFallback = useSetExternalSkillFallback()
  const setAgentDeprecated = useSetExternalAgentDeprecated()
  const setSkillDeprecated = useSetExternalSkillDeprecated()
  const setAgentRollout = useSetExternalAgentRolloutPolicy()
  const setSkillRollout = useSetExternalSkillRolloutPolicy()
  const setAgentRollback = useSetExternalAgentRollbackPolicy()
  const setSkillRollback = useSetExternalSkillRollbackPolicy()

  const overviewItems = overview.data?.items ?? []
  const releaseChannelOptions = Array.from(
    new Set(
      overviewItems
        .filter((item) => item.capabilityType === activeTab)
        .map((item) => String(item.releaseChannel || "unknown").trim().toLowerCase() || "unknown"),
    ),
  ).sort((left, right) => left.localeCompare(right, "zh-CN"))
  const resolvedChannelFilter =
    channelFilter === "all" || releaseChannelOptions.includes(channelFilter) ? channelFilter : "all"
  const filteredItems = overviewItems.filter((item) => {
    if (item.capabilityType !== activeTab) return false
    const keyword = deferredSearch.trim().toLowerCase()
    const matchesKeyword =
      !keyword ||
      (
      item.name.toLowerCase().includes(keyword) ||
      item.family.toLowerCase().includes(keyword) ||
      item.currentVersion?.toLowerCase().includes(keyword) ||
      item.currentId.toLowerCase().includes(keyword)
      )
    if (!matchesKeyword) return false
    if (healthFilter !== "all" && governanceHealthState(item) !== healthFilter) return false
    if (routeFilter === "routable" && !item.routable) return false
    if (routeFilter === "non_routable" && item.routable) return false
    if (routeFilter === "deprecated" && !item.deprecated) return false
    const normalizedChannel = String(item.releaseChannel || "unknown").trim().toLowerCase() || "unknown"
    if (resolvedChannelFilter !== "all" && normalizedChannel !== resolvedChannelFilter) return false
    return true
  }).sort((left, right) => {
    const riskDiff = governanceRiskScore(right) - governanceRiskScore(left)
    if (riskDiff !== 0) return riskDiff
    return left.family.localeCompare(right.family, "zh-CN")
  })
  const filteredSummary = {
    total: filteredItems.length,
    openCircuits: filteredItems.filter((item) => (item.circuitState || "").trim().toLowerCase() === "open").length,
    nonRoutable: filteredItems.filter((item) => !item.routable).length,
    canary: filteredItems.filter((item) => (item.releaseChannel || "").trim().toLowerCase() === "canary").length,
    offline: filteredItems.filter((item) => governanceHealthState(item) === "offline").length,
  }

  const selectedSummary =
    selection == null
      ? null
      : overviewItems.find(
          (item) =>
            item.capabilityType === selection.capabilityType && item.family === selection.family,
        ) ?? null

  const selectedVersions =
    selection?.capabilityType === "agent"
      ? agentVersions.data?.items ?? []
      : selection?.capabilityType === "skill"
        ? skillVersions.data?.items ?? []
        : []

  const relatedAudits = buildRelatedAudits(globalAudits.data?.items ?? [], selectedVersions)
  const selectedVersion =
    selectedVersions.find((item) => item.id === selectedVersionId) ?? null

  const isMutating =
    promoteAgentVersion.isPending ||
    promoteSkillVersion.isPending ||
    setAgentFallback.isPending ||
    setSkillFallback.isPending ||
    setAgentDeprecated.isPending ||
    setSkillDeprecated.isPending ||
    setAgentRollout.isPending ||
    setSkillRollout.isPending ||
    setAgentRollback.isPending ||
    setSkillRollback.isPending

  useEffect(() => {
    if (selectedVersions.length === 0) {
      setSelectedVersionId("")
      return
    }
    setSelectedVersionId((current) => {
      if (current && selectedVersions.some((item) => item.id === current)) {
        return current
      }
      return selectedVersions.find((item) => item.defaultVersion)?.id ?? selectedVersions[0].id
    })
  }, [selectedVersions])

  useEffect(() => {
    if (!selectedVersion) {
      setFallbackVersionId("none")
      setRolloutPercent("0")
      setRouteKey("global")
      setRollbackActive(false)
      setRollbackTargetVersionId("none")
      setDeprecated(false)
      return
    }
    setFallbackVersionId(selectedVersion.fallbackVersionId ?? "none")
    setRolloutPercent(String(selectedVersion.rolloutPolicy?.canaryPercent ?? 0))
    setRouteKey(selectedVersion.rolloutPolicy?.routeKey || "global")
    setRollbackActive(Boolean(selectedVersion.rollbackPolicy?.active))
    setRollbackTargetVersionId(selectedVersion.rollbackPolicy?.targetVersionId ?? "none")
    setDeprecated(Boolean(selectedVersion.deprecated))
  }, [selectedVersion])

  useEffect(() => {
    if (selection && selection.capabilityType !== activeTab) {
      setSelection(null)
    }
  }, [activeTab, selection])

  const handlePromote = async () => {
    if (!selection || !selectedVersionId) return
    try {
      if (selection.capabilityType === "agent") {
        await promoteAgentVersion.mutateAsync({
          family: selection.family,
          agentId: selectedVersionId,
        })
      } else {
        await promoteSkillVersion.mutateAsync({
          family: selection.family,
          skillId: selectedVersionId,
        })
      }
      toast({
        title: "版本切主已提交",
        description: `${selection.family} 当前主版本已切换为 ${selectedVersionId}。`,
      })
    } catch (error) {
      toast({
        title: "版本切主失败",
        description: mutationErrorMessage(error),
      })
    }
  }

  const handleUpdateFallback = async () => {
    if (!selection || !selectedVersionId) return
    try {
      const payload = {
        fallbackVersionId: fallbackVersionId === "none" ? null : fallbackVersionId,
      }
      if (selection.capabilityType === "agent") {
        await setAgentFallback.mutateAsync({
          family: selection.family,
          agentId: selectedVersionId,
          payload,
        })
      } else {
        await setSkillFallback.mutateAsync({
          family: selection.family,
          skillId: selectedVersionId,
          payload,
        })
      }
      toast({
        title: "Fallback 已更新",
        description: `${selectedVersionId} 的回退版本配置已写入。`,
      })
    } catch (error) {
      toast({
        title: "Fallback 更新失败",
        description: mutationErrorMessage(error),
      })
    }
  }

  const handleUpdateDeprecated = async () => {
    if (!selection || !selectedVersionId) return
    try {
      const payload = { deprecated }
      if (selection.capabilityType === "agent") {
        await setAgentDeprecated.mutateAsync({
          family: selection.family,
          agentId: selectedVersionId,
          payload,
        })
      } else {
        await setSkillDeprecated.mutateAsync({
          family: selection.family,
          skillId: selectedVersionId,
          payload,
        })
      }
      toast({
        title: "弃用状态已更新",
        description: `${selectedVersionId} 的 deprecated 状态已同步。`,
      })
    } catch (error) {
      toast({
        title: "弃用状态更新失败",
        description: mutationErrorMessage(error),
      })
    }
  }

  const handleUpdateRollout = async () => {
    if (!selection || !selectedVersionId) return
    const canaryPercent = Math.max(0, Math.min(100, Number.parseInt(rolloutPercent || "0", 10) || 0))
    try {
      const payload = {
        rolloutPolicy: {
          canaryPercent,
          routeKey: routeKey.trim() || "global",
        },
      }
      if (selection.capabilityType === "agent") {
        await setAgentRollout.mutateAsync({
          family: selection.family,
          agentId: selectedVersionId,
          payload,
        })
      } else {
        await setSkillRollout.mutateAsync({
          family: selection.family,
          skillId: selectedVersionId,
          payload,
        })
      }
      toast({
        title: "灰度策略已更新",
        description: `${selectedVersionId} 的 canary 和 route key 已生效。`,
      })
    } catch (error) {
      toast({
        title: "灰度策略更新失败",
        description: mutationErrorMessage(error),
      })
    }
  }

  const handleUpdateRollback = async () => {
    if (!selection || !selectedVersionId) return
    try {
      const payload = {
        rollbackPolicy: {
          active: rollbackActive,
          targetVersionId: rollbackTargetVersionId === "none" ? null : rollbackTargetVersionId,
        },
      }
      if (selection.capabilityType === "agent") {
        await setAgentRollback.mutateAsync({
          family: selection.family,
          agentId: selectedVersionId,
          payload,
        })
      } else {
        await setSkillRollback.mutateAsync({
          family: selection.family,
          skillId: selectedVersionId,
          payload,
        })
      }
      toast({
        title: "回滚策略已更新",
        description: `${selectedVersionId} 的 rollback policy 已写入。`,
      })
    } catch (error) {
      toast({
        title: "回滚策略更新失败",
        description: mutationErrorMessage(error),
      })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">外接治理</h1>
          <p className="text-sm text-muted-foreground">
            在主脑本地治理外接 Agent / Skill 的切主、灰度、回滚、弃用与最近审计动作。
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!canManageExternal ? (
            <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
              当前账号为只读
            </Badge>
          ) : (
            <Badge variant="secondary" className="bg-primary/10 text-primary">
              可执行治理操作
            </Badge>
          )}
          <Button
            variant="outline"
            onClick={() => {
              void overview.refetch()
              void globalAudits.refetch()
            }}
            disabled={overview.isFetching || globalAudits.isFetching}
          >
            <RefreshCw className={cn("mr-2 size-4", (overview.isFetching || globalAudits.isFetching) && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      {!canManageExternal ? (
        <div className="rounded-lg border border-border bg-secondary/30 p-3 text-sm text-muted-foreground">
          你当前只有 `external:read` 权限，可以查看版本、健康和审计，但不能执行切主、灰度或回滚。
        </div>
      ) : null}

      {overview.error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          外接治理视图加载失败：{overview.error instanceof Error ? overview.error.message : "未知错误"}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <SummaryCard title="Agent 家族" value={overview.data?.summary.agentFamilies ?? 0} hint="可治理 Agent family" />
        <SummaryCard title="Skill 家族" value={overview.data?.summary.skillFamilies ?? 0} hint="可治理 Skill family" />
        <SummaryCard title="总版本数" value={overview.data?.summary.totalVersions ?? 0} hint="已纳入控制面的版本" />
        <SummaryCard title="可路由" value={overview.data?.summary.routable ?? 0} hint="当前可参与调度" />
        <SummaryCard title="打开熔断" value={overview.data?.summary.openCircuits ?? 0} hint="需要重点关注的执行单元" />
        <SummaryCard title="离线/未知" value={overview.data?.summary.offline ?? 0} hint="可能需要恢复或摘除" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_420px]">
        <Card className="bg-card">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-base">版本治理面板</CardTitle>
                <div className="mt-1 text-sm text-muted-foreground">
                  以 family 为治理单元查看当前主版本、回退与灰度状态。
                </div>
              </div>
              <div className="w-full sm:w-72">
                <Input
                  value={search}
                  onChange={(event) => {
                    const nextValue = event.target.value
                    startTransition(() => {
                      setSearch(nextValue)
                    })
                  }}
                  placeholder="搜索 family / 版本 / 版本 ID"
                />
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg border border-border bg-background/60 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="text-xs">
                  当前视图 {filteredSummary.total}
                </Badge>
                <Badge variant="secondary" className="bg-destructive/15 text-destructive">
                  熔断 {filteredSummary.openCircuits}
                </Badge>
                <Badge variant="secondary" className="bg-warning/20 text-warning-foreground">
                  非可路由 {filteredSummary.nonRoutable}
                </Badge>
                <Badge variant="secondary" className="bg-warning/20 text-warning-foreground">
                  Canary {filteredSummary.canary}
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  离线/未知 {filteredSummary.offline}
                </Badge>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <Select
                  value={healthFilter}
                  onValueChange={(value) => setHealthFilter(value as GovernanceHealthFilter)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="健康状态" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部健康态</SelectItem>
                    <SelectItem value="healthy">健康 / 在线</SelectItem>
                    <SelectItem value="degraded">降级</SelectItem>
                    <SelectItem value="offline">离线 / 未知</SelectItem>
                    <SelectItem value="open">熔断打开</SelectItem>
                  </SelectContent>
                </Select>
                <Select
                  value={routeFilter}
                  onValueChange={(value) => setRouteFilter(value as GovernanceRouteFilter)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="路由状态" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部路由态</SelectItem>
                    <SelectItem value="routable">仅可路由</SelectItem>
                    <SelectItem value="non_routable">仅不可路由</SelectItem>
                    <SelectItem value="deprecated">仅 deprecated</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={resolvedChannelFilter} onValueChange={setChannelFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="发布通道" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部通道</SelectItem>
                    {releaseChannelOptions.map((channel) => (
                      <SelectItem key={channel} value={channel}>
                        {channel}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Tabs
              value={activeTab}
              onValueChange={(value) => setActiveTab(value as ExternalCapabilityType)}
            >
              <TabsList>
                <TabsTrigger value="agent">外接 Agent</TabsTrigger>
                <TabsTrigger value="skill">外接 Skill</TabsTrigger>
              </TabsList>
              <TabsContent value="agent" className="mt-4">
                {overview.isLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : filteredItems.length === 0 ? (
                  <EmptyState title="没有匹配的 Agent family" description="调整搜索条件，或等待外接 Agent 注册进控制面。" />
                ) : (
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Family</TableHead>
                          <TableHead>当前版本</TableHead>
                          <TableHead>健康</TableHead>
                          <TableHead>治理状态</TableHead>
                          <TableHead>最近心跳</TableHead>
                          <TableHead className="w-[90px] text-right">操作</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredItems.map((item) => (
                          <TableRow key={`${item.capabilityType}-${item.family}`}>
                            <TableCell className="align-top">
                              <div className="font-medium text-foreground">{item.name}</div>
                              <div className="text-xs text-muted-foreground">{item.family}</div>
                              <div className="mt-2 flex flex-wrap gap-1">
                                <Badge variant="outline">{item.versionCount} versions</Badge>
                                {item.deprecated ? <Badge variant="secondary">deprecated</Badge> : null}
                              </div>
                            </TableCell>
                            <TableCell className="align-top">
                              <div className="font-medium text-foreground">{item.currentVersion || "-"}</div>
                              <div className="mt-1 flex flex-wrap gap-1">
                                <Badge variant="secondary" className={normalizeChannelTone(item.releaseChannel)}>
                                  {item.releaseChannel || "unknown"}
                                </Badge>
                                {item.defaultVersionId ? <Badge variant="outline">default</Badge> : null}
                              </div>
                              <div className="mt-2 text-xs text-muted-foreground">
                                fallback: {item.fallbackVersionId || "-"}
                              </div>
                            </TableCell>
                            <TableCell className="align-top">
                              <Badge variant="secondary" className={normalizeTone(item.status)}>
                                {item.status}
                              </Badge>
                              <div className="mt-2 text-xs text-muted-foreground">
                                routable: {item.routable ? "yes" : "no"}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                circuit: {item.circuitState || "-"}
                              </div>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              <div>rollout: {rolloutSummary(item.rolloutPolicy)}</div>
                              <div className="mt-1">rollback: {rollbackSummary(item.rollbackPolicy)}</div>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              {toDisplayDate(item.lastHeartbeatAt)}
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  setSelection({
                                    capabilityType: item.capabilityType,
                                    family: item.family,
                                  })
                                }
                              >
                                治理
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </TabsContent>
              <TabsContent value="skill" className="mt-4">
                {overview.isLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : filteredItems.length === 0 ? (
                  <EmptyState title="没有匹配的 Skill family" description="调整搜索条件，或等待外接 Skill 注册进控制面。" />
                ) : (
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Family</TableHead>
                          <TableHead>当前版本</TableHead>
                          <TableHead>健康</TableHead>
                          <TableHead>治理状态</TableHead>
                          <TableHead>最近心跳</TableHead>
                          <TableHead className="w-[90px] text-right">操作</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredItems.map((item) => (
                          <TableRow key={`${item.capabilityType}-${item.family}`}>
                            <TableCell className="align-top">
                              <div className="font-medium text-foreground">{item.name}</div>
                              <div className="text-xs text-muted-foreground">{item.family}</div>
                              <div className="mt-2 flex flex-wrap gap-1">
                                <Badge variant="outline">{item.versionCount} versions</Badge>
                                {item.deprecated ? <Badge variant="secondary">deprecated</Badge> : null}
                              </div>
                            </TableCell>
                            <TableCell className="align-top">
                              <div className="font-medium text-foreground">{item.currentVersion || "-"}</div>
                              <div className="mt-1 flex flex-wrap gap-1">
                                <Badge variant="secondary" className={normalizeChannelTone(item.releaseChannel)}>
                                  {item.releaseChannel || "unknown"}
                                </Badge>
                                {item.defaultVersionId ? <Badge variant="outline">default</Badge> : null}
                              </div>
                              <div className="mt-2 text-xs text-muted-foreground">
                                fallback: {item.fallbackVersionId || "-"}
                              </div>
                            </TableCell>
                            <TableCell className="align-top">
                              <Badge variant="secondary" className={normalizeTone(item.status)}>
                                {item.status}
                              </Badge>
                              <div className="mt-2 text-xs text-muted-foreground">
                                routable: {item.routable ? "yes" : "no"}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                circuit: {item.circuitState || "-"}
                              </div>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              <div>rollout: {rolloutSummary(item.rolloutPolicy)}</div>
                              <div className="mt-1">rollback: {rollbackSummary(item.rollbackPolicy)}</div>
                            </TableCell>
                            <TableCell className="align-top text-xs text-muted-foreground">
                              {toDisplayDate(item.lastHeartbeatAt)}
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  setSelection({
                                    capabilityType: item.capabilityType,
                                    family: item.family,
                                  })
                                }
                              >
                                治理
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">最近治理动作</CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[620px] pr-4">
              <div className="space-y-3">
                {(overview.data?.recentAudits ?? []).map((audit) => (
                  <div key={audit.id} className="rounded-lg border border-border bg-secondary/20 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium text-foreground">{audit.action}</div>
                      <Badge variant="secondary" className={normalizeTone(audit.status)}>
                        {audit.status}
                      </Badge>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {audit.user} · {toDisplayDate(audit.timestamp)}
                    </div>
                    <div className="mt-2 text-sm text-muted-foreground">{audit.details}</div>
                    <div className="mt-2 text-xs text-muted-foreground">{audit.resource}</div>
                  </div>
                ))}
                {!overview.isLoading && (overview.data?.recentAudits?.length ?? 0) === 0 ? (
                  <div className="text-sm text-muted-foreground">当前还没有外接治理审计。</div>
                ) : null}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      <Sheet
        open={Boolean(selection)}
        onOpenChange={(open) => {
          if (!open) {
            setSelection(null)
          }
        }}
      >
        <SheetContent className="w-full sm:max-w-5xl">
          <SheetHeader>
            <SheetTitle>
              {selectedSummary ? `${capabilityLabels[selectedSummary.capabilityType]} · ${selectedSummary.name}` : "外接治理"}
            </SheetTitle>
            <SheetDescription>
              版本切主、fallback、灰度、回滚与弃用操作都在本地主脑控制面执行并写审计。
            </SheetDescription>
          </SheetHeader>

          {!selectedSummary ? null : (
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden px-4 pb-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_360px]">
                <div className="rounded-lg border border-border bg-secondary/20 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{capabilityLabels[selectedSummary.capabilityType]}</Badge>
                    <Badge variant="secondary" className={normalizeTone(selectedSummary.status)}>
                      {selectedSummary.status}
                    </Badge>
                    <Badge variant="secondary" className={normalizeChannelTone(selectedSummary.releaseChannel)}>
                      {selectedSummary.releaseChannel || "unknown"}
                    </Badge>
                  </div>
                  <div className="mt-3 text-sm text-muted-foreground">
                    <div>family: {selectedSummary.family}</div>
                    <div>current: {selectedSummary.currentId} · v{selectedSummary.currentVersion || "-"}</div>
                    <div>fallback: {selectedSummary.fallbackVersionId || "-"}</div>
                    <div>rollout: {rolloutSummary(selectedSummary.rolloutPolicy)}</div>
                    <div>rollback: {rollbackSummary(selectedSummary.rollbackPolicy)}</div>
                    <div>heartbeat: {toDisplayDate(selectedSummary.lastHeartbeatAt)}</div>
                  </div>
                </div>

                <div className="rounded-lg border border-border bg-secondary/20 p-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
                    {selectedSummary.capabilityType === "agent" ? <Bot className="size-4" /> : <Sparkles className="size-4" />}
                    版本治理表单
                  </div>
                  {(agentVersions.isLoading || skillVersions.isLoading) && selectedVersions.length === 0 ? (
                    <div className="space-y-2">
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                    </div>
                  ) : selectedVersions.length === 0 ? (
                    <div className="text-sm text-muted-foreground">当前 family 还没有可治理版本。</div>
                  ) : (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">治理版本</div>
                        <Select value={selectedVersionId} onValueChange={setSelectedVersionId}>
                          <SelectTrigger>
                            <SelectValue placeholder="选择版本" />
                          </SelectTrigger>
                          <SelectContent>
                            {selectedVersions.map((item) => (
                              <SelectItem key={item.id} value={item.id}>
                                {item.version} · {item.id}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground">Fallback 版本</div>
                          <Select value={fallbackVersionId} onValueChange={setFallbackVersionId}>
                            <SelectTrigger>
                              <SelectValue placeholder="选择 fallback 版本" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">不设置</SelectItem>
                              {selectedVersions.map((item) => (
                                <SelectItem key={`fallback-${item.id}`} value={item.id}>
                                  {item.version} · {item.id}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            variant="outline"
                            className="w-full"
                            disabled={!canManageExternal || !selectedVersionId || isMutating}
                            onClick={() => void handleUpdateFallback()}
                          >
                            保存 fallback
                          </Button>
                        </div>

                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground">弃用状态</div>
                          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                            <div className="text-sm text-foreground">deprecated</div>
                            <Switch
                              checked={deprecated}
                              disabled={!canManageExternal || !selectedVersionId || isMutating}
                              onCheckedChange={setDeprecated}
                            />
                          </div>
                          <Button
                            variant="outline"
                            className="w-full"
                            disabled={!canManageExternal || !selectedVersionId || isMutating}
                            onClick={() => void handleUpdateDeprecated()}
                          >
                            保存弃用状态
                          </Button>
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground">灰度流量百分比</div>
                          <Input
                            type="number"
                            min={0}
                            max={100}
                            value={rolloutPercent}
                            disabled={!canManageExternal || !selectedVersionId || isMutating}
                            onChange={(event) => setRolloutPercent(event.target.value)}
                          />
                        </div>
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground">Route Key</div>
                          <Input
                            value={routeKey}
                            disabled={!canManageExternal || !selectedVersionId || isMutating}
                            onChange={(event) => setRouteKey(event.target.value)}
                          />
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        className="w-full"
                        disabled={!canManageExternal || !selectedVersionId || isMutating}
                        onClick={() => void handleUpdateRollout()}
                      >
                        保存灰度策略
                      </Button>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground">启用回滚</div>
                          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                            <div className="text-sm text-foreground">rollback active</div>
                            <Switch
                              checked={rollbackActive}
                              disabled={!canManageExternal || !selectedVersionId || isMutating}
                              onCheckedChange={setRollbackActive}
                            />
                          </div>
                        </div>
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground">回滚目标版本</div>
                          <Select value={rollbackTargetVersionId} onValueChange={setRollbackTargetVersionId}>
                            <SelectTrigger>
                              <SelectValue placeholder="选择回滚版本" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">不设置</SelectItem>
                              {selectedVersions.map((item) => (
                                <SelectItem key={`rollback-${item.id}`} value={item.id}>
                                  {item.version} · {item.id}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        className="w-full"
                        disabled={!canManageExternal || !selectedVersionId || isMutating}
                        onClick={() => void handleUpdateRollback()}
                      >
                        保存回滚策略
                      </Button>

                      <Button
                        className="w-full"
                        disabled={!canManageExternal || !selectedVersionId || isMutating}
                        onClick={() => void handlePromote()}
                      >
                        {isMutating ? "执行中..." : "切主到当前版本"}
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1.25fr)_360px]">
                <div className="min-h-0 rounded-lg border border-border">
                  <div className="border-b border-border px-4 py-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Activity className="size-4" />
                      版本清单
                    </div>
                  </div>
                  <ScrollArea className="h-[420px]">
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>版本</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead>治理</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {selectedVersions.map((item) => (
                            <TableRow
                              key={item.id}
                              className={cn(item.id === selectedVersionId && "bg-primary/5")}
                            >
                              <TableCell className="align-top">
                                <button
                                  type="button"
                                  className="text-left"
                                  onClick={() => setSelectedVersionId(item.id)}
                                >
                                  <div className="font-medium text-foreground">{item.version}</div>
                                  <div className="text-xs text-muted-foreground">{item.id}</div>
                                </button>
                                <div className="mt-2 flex flex-wrap gap-1">
                                  <Badge variant="secondary" className={normalizeChannelTone(item.releaseChannel)}>
                                    {item.releaseChannel || "unknown"}
                                  </Badge>
                                  {item.defaultVersion ? <Badge variant="outline">default</Badge> : null}
                                  {item.deprecated ? <Badge variant="secondary">deprecated</Badge> : null}
                                </div>
                              </TableCell>
                              <TableCell className="align-top">
                                <Badge variant="secondary" className={normalizeTone(item.status)}>
                                  {item.status || "unknown"}
                                </Badge>
                                <div className="mt-2 text-xs text-muted-foreground">
                                  routable: {item.routable ? "yes" : "no"}
                                </div>
                              </TableCell>
                              <TableCell className="align-top text-xs text-muted-foreground">
                                <div>fallback: {item.fallbackVersionId || "-"}</div>
                                <div className="mt-1">rollout: {rolloutSummary(item.rolloutPolicy)}</div>
                                <div className="mt-1">rollback: {rollbackSummary(item.rollbackPolicy)}</div>
                              </TableCell>
                            </TableRow>
                          ))}
                          {selectedVersions.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={3} className="py-10 text-center text-sm text-muted-foreground">
                                当前没有版本记录。
                              </TableCell>
                            </TableRow>
                          ) : null}
                        </TableBody>
                      </Table>
                    </div>
                  </ScrollArea>
                </div>

                <div className="min-h-0 rounded-lg border border-border">
                  <div className="border-b border-border px-4 py-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Sparkles className="size-4" />
                      相关审计
                    </div>
                  </div>
                  <ScrollArea className="h-[420px] p-4">
                    <div className="space-y-3">
                      {relatedAudits.map((audit) => (
                        <div key={audit.id} className="rounded-lg border border-border bg-secondary/20 p-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-sm font-medium text-foreground">{audit.action}</div>
                            <Badge variant="secondary" className={normalizeTone(audit.status)}>
                              {audit.status}
                            </Badge>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {audit.user} · {toDisplayDate(audit.timestamp)}
                          </div>
                          <div className="mt-2 text-sm text-muted-foreground">{audit.details}</div>
                          <div className="mt-2 text-xs text-muted-foreground">{audit.resource}</div>
                        </div>
                      ))}
                      {!globalAudits.isLoading && relatedAudits.length === 0 ? (
                        <div className="text-sm text-muted-foreground">
                          当前还没有与该 family 直接关联的治理审计。
                        </div>
                      ) : null}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
