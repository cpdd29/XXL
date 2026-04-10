"use client"

import type { ReactNode } from "react"
import { startTransition, useDeferredValue, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import {
  downloadAuditLogs,
  useAuditLogs,
  useReleaseSecurityPenalty,
  useSecurityPenalties,
  useSecurityPolicy,
  useSecurityReport,
  useSecurityRules,
  useUpdateSecurityPolicy,
  useUpdateSecurityRule,
} from "@/hooks/use-security"
import { toast } from "@/hooks/use-toast"
import type { AuditLog, SecurityPenalty, SecurityPolicySettings, SecurityRule } from "@/types"
import {
  Search,
  Shield,
  ShieldOff,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Filter,
  Download,
  Plus,
  Settings,
  BarChart3,
  Radar,
} from "lucide-react"

const statusConfig: Record<AuditLog["status"], { icon: ReactNode; color: string }> = {
  success: {
    icon: <CheckCircle2 className="size-4" />,
    color: "bg-success/20 text-success",
  },
  warning: {
    icon: <AlertTriangle className="size-4" />,
    color: "bg-warning/20 text-warning-foreground",
  },
  error: {
    icon: <XCircle className="size-4" />,
    color: "bg-destructive/20 text-destructive",
  },
}

const ruleTypeConfig = {
  filter: { label: "过滤", color: "bg-primary/20 text-primary" },
  block: { label: "阻止", color: "bg-destructive/20 text-destructive" },
  alert: { label: "告警", color: "bg-warning/20 text-warning-foreground" },
}

const penaltyLevelConfig: Record<string, { label: string; color: string }> = {
  cooldown: { label: "冷却", color: "bg-warning/20 text-warning-foreground" },
  ban: { label: "封禁", color: "bg-destructive/20 text-destructive" },
}

const pageSizeOptions = ["10", "20", "50"] as const
const reportWindowOptions = [
  { value: "24", label: "最近 24 小时" },
  { value: "72", label: "最近 72 小时" },
  { value: "168", label: "最近 7 天" },
] as const
type SecurityPolicyNumericKey =
  | "messageRateLimitPerMinute"
  | "messageRateLimitCooldownSeconds"
  | "messageRateLimitBanThreshold"
  | "messageRateLimitBanSeconds"
  | "securityIncidentWindowSeconds"
  | "promptRuleBlockThreshold"
  | "promptClassifierBlockThreshold"
type SecurityPolicyBooleanKey = "promptInjectionEnabled" | "contentRedactionEnabled"

export default function SecurityPage() {
  const [activeTab, setActiveTab] = useState("logs")
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | AuditLog["status"]>("all")
  const [userFilter, setUserFilter] = useState("")
  const [resourceFilter, setResourceFilter] = useState("")
  const [pageSize, setPageSize] = useState<(typeof pageSizeOptions)[number]>("10")
  const [reportWindowHours, setReportWindowHours] = useState<(typeof reportWindowOptions)[number]["value"]>("24")
  const [offset, setOffset] = useState(0)
  const [isExporting, setIsExporting] = useState(false)
  const [policyDraft, setPolicyDraft] = useState<SecurityPolicySettings | null>(null)
  const [releasingUserKey, setReleasingUserKey] = useState<string | null>(null)

  const deferredSearchQuery = useDeferredValue(searchQuery.trim())
  const deferredUserFilter = useDeferredValue(userFilter.trim())
  const deferredResourceFilter = useDeferredValue(resourceFilter.trim())
  const limit = Number(pageSize)

  const { data: logsData, isLoading: logsLoading, error: logsError } = useAuditLogs({
    search: deferredSearchQuery || undefined,
    status: statusFilter === "all" ? undefined : statusFilter,
    user: deferredUserFilter || undefined,
    resource: deferredResourceFilter || undefined,
    limit,
    offset,
  })
  const { data: rulesData, isLoading: rulesLoading, error: rulesError } = useSecurityRules()
  const { data: penaltiesData, isLoading: penaltiesLoading, error: penaltiesError } = useSecurityPenalties()
  const { data: policyData, isLoading: policyLoading, error: policyError } = useSecurityPolicy()
  const {
    data: reportData,
    isLoading: reportLoading,
    error: reportError,
  } = useSecurityReport(Number(reportWindowHours))
  const updateRuleMutation = useUpdateSecurityRule()
  const updatePolicyMutation = useUpdateSecurityPolicy()
  const releasePenaltyMutation = useReleaseSecurityPenalty()

  const auditLogs = logsData?.items ?? []
  const totalLogs = logsData?.total ?? 0
  const appliedLimit = logsData?.limit ?? limit
  const currentPage = Math.floor(offset / appliedLimit) + 1
  const totalPages = Math.max(1, Math.ceil(totalLogs / appliedLimit))
  const canLoadPrevious = offset > 0
  const canLoadNext = Boolean(logsData?.hasMore)
  const isSyncingFilters =
    deferredSearchQuery !== searchQuery.trim() ||
    deferredUserFilter !== userFilter.trim() ||
    deferredResourceFilter !== resourceFilter.trim()
  const securityRules = rulesData?.items ?? []
  const summary = rulesData?.summary ?? {
    todayEvents: auditLogs.length,
    blockedThreats: securityRules.filter((rule) => rule.type === "block").length,
    alertNotifications: securityRules.filter((rule) => rule.type === "alert").length,
    activeRules: securityRules.filter((rule) => rule.enabled).length,
  }
  const reportSummary = reportData?.summary
  const activePenalties = penaltiesData?.items ?? []

  useEffect(() => {
    if (policyData?.settings) {
      setPolicyDraft(policyData.settings)
    }
  }, [policyData])

  const handleRuleToggle = async (rule: SecurityRule, enabled: boolean) => {
    try {
      await updateRuleMutation.mutateAsync({
        ruleId: rule.id,
        payload: { enabled },
      })
      toast({
        title: "安全规则已更新",
        description: `${rule.name} 已${enabled ? "启用" : "停用"}`,
      })
    } catch (mutationError) {
      toast({
        title: "更新规则失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleSearchChange = (value: string) => {
    startTransition(() => {
      setSearchQuery(value)
      setOffset(0)
    })
  }

  const handleStatusChange = (value: "all" | AuditLog["status"]) => {
    startTransition(() => {
      setStatusFilter(value)
      setOffset(0)
    })
  }

  const handleUserFilterChange = (value: string) => {
    startTransition(() => {
      setUserFilter(value)
      setOffset(0)
    })
  }

  const handleResourceFilterChange = (value: string) => {
    startTransition(() => {
      setResourceFilter(value)
      setOffset(0)
    })
  }

  const handlePageSizeChange = (value: (typeof pageSizeOptions)[number]) => {
    startTransition(() => {
      setPageSize(value)
      setOffset(0)
    })
  }

  const handleExportLogs = async () => {
    try {
      setIsExporting(true)
      const { blob, filename } = await downloadAuditLogs({
        search: deferredSearchQuery || undefined,
        status: statusFilter === "all" ? undefined : statusFilter,
        user: deferredUserFilter || undefined,
        resource: deferredResourceFilter || undefined,
      })

      const objectUrl = window.URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = objectUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(objectUrl)

      toast({
        title: "日志导出成功",
        description: `已按当前筛选条件导出 ${totalLogs} 条日志。`,
      })
    } catch (exportError) {
      toast({
        title: "日志导出失败",
        description: exportError instanceof Error ? exportError.message : "未知错误",
      })
    } finally {
      setIsExporting(false)
    }
  }

  const handlePolicyNumberChange = (key: SecurityPolicyNumericKey, value: string) => {
    setPolicyDraft((current) => {
      if (!current) return current
      const normalized = Number(value)
      return {
        ...current,
        [key]: Number.isFinite(normalized) ? normalized : 0,
      }
    })
  }

  const handlePolicyToggle = (key: SecurityPolicyBooleanKey, value: boolean) => {
    setPolicyDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const handleSavePolicy = async () => {
    if (!policyDraft) return
    try {
      await updatePolicyMutation.mutateAsync(policyDraft)
      toast({
        title: "安全策略已保存",
        description: "安全网关阈值与策略开关已更新。",
      })
    } catch (mutationError) {
      toast({
        title: "保存安全策略失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleReleasePenalty = async (penalty: SecurityPenalty) => {
    try {
      setReleasingUserKey(penalty.userKey)
      await releasePenaltyMutation.mutateAsync({ userKey: penalty.userKey })
      toast({
        title: "处罚已解除",
        description: `${penalty.userKey} 的${penaltyLevelConfig[penalty.level]?.label ?? "处罚"}状态已清除。`,
      })
    } catch (mutationError) {
      toast({
        title: "解除处罚失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    } finally {
      setReleasingUserKey(null)
    }
  }

  const formatDateTime = (value: string | undefined) => {
    if (!value) return "--"
    return value.replace("T", " ").replace("Z", "").slice(0, 19)
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">安全中心</h1>
          <p className="text-sm text-muted-foreground">
            监控安全事件和管理安全规则
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportLogs}
            disabled={isExporting || logsLoading || isSyncingFilters}
          >
            <Download className="mr-2 size-4" />
            {isExporting ? "导出中..." : "导出日志"}
          </Button>
          <Button
            size="sm"
            onClick={() => setActiveTab("report")}
          >
            <BarChart3 className="mr-2 size-4" />
            安全报告
          </Button>
        </div>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">今日事件</p>
                <p className="text-2xl font-bold text-foreground">{summary.todayEvents}</p>
              </div>
              <div className="rounded-lg bg-primary/20 p-2 text-primary">
                <Shield className="size-5" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">已阻止威胁</p>
                <p className="text-2xl font-bold text-destructive">{summary.blockedThreats}</p>
              </div>
              <div className="rounded-lg bg-destructive/20 p-2 text-destructive">
                <XCircle className="size-5" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">告警通知</p>
                <p className="text-2xl font-bold text-warning">{summary.alertNotifications}</p>
              </div>
              <div className="rounded-lg bg-warning/20 p-2 text-warning-foreground">
                <AlertTriangle className="size-5" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">活跃规则</p>
                <p className="text-2xl font-bold text-success">{summary.activeRules}</p>
              </div>
              <div className="rounded-lg bg-success/20 p-2 text-success">
                <CheckCircle2 className="size-5" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="mb-4 bg-secondary">
          <TabsTrigger value="logs">审计日志</TabsTrigger>
          <TabsTrigger value="rules">安全规则</TabsTrigger>
          <TabsTrigger value="policy">策略配置</TabsTrigger>
          <TabsTrigger value="penalties">处罚运营</TabsTrigger>
          <TabsTrigger value="report">安全报告</TabsTrigger>
        </TabsList>

        <TabsContent value="logs" className="mt-0">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <CardTitle className="text-base">审计日志</CardTitle>
                <div className="flex flex-col gap-2 xl:items-end">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        placeholder="搜索动作、用户、详情..."
                        value={searchQuery}
                        onChange={(e) => handleSearchChange(e.target.value)}
                        className="w-72 bg-secondary pl-10"
                      />
                    </div>
                    <div className="flex items-center gap-2 rounded-md border border-border bg-secondary px-3 py-2 text-xs text-muted-foreground">
                      <Filter className="size-4" />
                      服务端筛选
                    </div>
                    <Select value={statusFilter} onValueChange={handleStatusChange}>
                      <SelectTrigger className="w-[140px] bg-secondary">
                        <SelectValue placeholder="全部状态" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">全部状态</SelectItem>
                        <SelectItem value="success">成功</SelectItem>
                        <SelectItem value="warning">告警</SelectItem>
                        <SelectItem value="error">异常</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select value={pageSize} onValueChange={handlePageSizeChange}>
                      <SelectTrigger className="w-[140px] bg-secondary">
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
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      placeholder="按用户筛选"
                      value={userFilter}
                      onChange={(e) => handleUserFilterChange(e.target.value)}
                      className="w-44 bg-secondary"
                    />
                    <Input
                      placeholder="按资源筛选"
                      value={resourceFilter}
                      onChange={(e) => handleResourceFilterChange(e.target.value)}
                      className="w-44 bg-secondary"
                    />
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {logsError && (
                <div className="mb-4 text-sm text-destructive">
                  审计日志加载失败：{logsError instanceof Error ? logsError.message : "未知错误"}
                </div>
              )}
              <div className="mb-4 flex flex-col gap-2 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
                <span>
                  共 {totalLogs} 条日志，当前第 {currentPage} / {totalPages} 页
                </span>
                <span>{isSyncingFilters ? "正在同步筛选条件..." : "筛选结果由后端直接返回"}</span>
              </div>
              <ScrollArea className="h-[400px]">
                <div className="space-y-3">
                  {auditLogs.map((log) => (
                    <div
                      key={log.id}
                      className="flex items-start gap-4 rounded-lg border border-border bg-secondary/30 p-3"
                    >
                      <div
                        className={cn(
                          "mt-0.5 rounded p-1.5",
                          statusConfig[log.status].color
                        )}
                      >
                        {statusConfig[log.status].icon}
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-foreground">
                            {log.action}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {log.timestamp}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {log.details}
                        </p>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>用户: {log.user}</span>
                          <span>资源: {log.resource}</span>
                          <span>IP: {log.ip}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                  {logsLoading && auditLogs.length === 0 && (
                    <div className="flex h-40 items-center justify-center text-muted-foreground">
                      正在加载审计日志...
                    </div>
                  )}
                  {!logsLoading && auditLogs.length === 0 && (
                    <div className="flex h-40 items-center justify-center text-muted-foreground">
                      没有找到匹配的日志
                    </div>
                  )}
                </div>
              </ScrollArea>
              <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4 md:flex-row md:items-center md:justify-between">
                <div className="text-xs text-muted-foreground">
                  当前显示 {auditLogs.length} 条，偏移 {logsData?.offset ?? offset}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canLoadPrevious || logsLoading}
                    onClick={() => setOffset((currentOffset) => Math.max(0, currentOffset - appliedLimit))}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canLoadNext || logsLoading}
                    onClick={() => setOffset((currentOffset) => currentOffset + appliedLimit)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="rules" className="mt-0">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">安全规则</CardTitle>
                <Button
                  size="sm"
                  onClick={() =>
                    toast({
                      title: "添加规则入口已保留",
                      description: "后续会接入安全规则创建表单。",
                    })
                  }
                >
                  <Plus className="mr-2 size-4" />
                  添加规则
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {rulesError && (
                <div className="mb-4 text-sm text-destructive">
                  安全规则加载失败：{rulesError instanceof Error ? rulesError.message : "未知错误"}
                </div>
              )}
              <div className="space-y-3">
                {securityRules.map((rule) => (
                  <div
                    key={rule.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-4"
                  >
                    <div className="flex items-center gap-4">
                      <div className="rounded-lg bg-primary/20 p-2 text-primary">
                        <Shield className="size-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">
                            {rule.name}
                          </span>
                          <Badge
                            variant="secondary"
                            className={cn(
                              "text-xs",
                              ruleTypeConfig[rule.type].color
                            )}
                          >
                            {ruleTypeConfig[rule.type].label}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {rule.description}
                        </p>
                        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                          <span>触发次数: {rule.hitCount.toLocaleString()}</span>
                          <span>最后触发: {rule.lastTriggered}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <Switch
                        checked={rule.enabled}
                        onCheckedChange={(checked) => void handleRuleToggle(rule, checked)}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={() =>
                          toast({
                            title: "规则详情入口已保留",
                            description: `规则 ${rule.name} 的配置页下一轮接入。`,
                          })
                        }
                      >
                        <Settings className="size-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {rulesLoading && (
                  <div className="flex h-40 items-center justify-center text-muted-foreground">
                    正在加载安全规则...
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="policy" className="mt-0">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <CardTitle className="text-base">安全策略配置</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    调整安全网关的限流、封禁与 Prompt Injection 判定阈值。
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="rounded-md border border-border bg-secondary px-3 py-2 text-xs text-muted-foreground">
                    更新时间 {policyData?.updatedAt?.replace("T", " ").replace("Z", "").slice(0, 19) ?? "--"}
                  </div>
                  <Button
                    size="sm"
                    onClick={() => void handleSavePolicy()}
                    disabled={!policyDraft || policyLoading || updatePolicyMutation.isPending}
                  >
                    {updatePolicyMutation.isPending ? "保存中..." : "保存策略"}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {policyError && (
                <div className="text-sm text-destructive">
                  安全策略加载失败：{policyError instanceof Error ? policyError.message : "未知错误"}
                </div>
              )}
              <div className="grid gap-4 xl:grid-cols-2">
                <Card className="bg-secondary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">限流与封禁</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">每分钟消息上限</div>
                      <Input
                        type="number"
                        min={1}
                        value={policyDraft?.messageRateLimitPerMinute ?? ""}
                        onChange={(event) => handlePolicyNumberChange("messageRateLimitPerMinute", event.target.value)}
                        className="bg-secondary"
                      />
                    </div>
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">冷却时长（秒）</div>
                      <Input
                        type="number"
                        min={1}
                        value={policyDraft?.messageRateLimitCooldownSeconds ?? ""}
                        onChange={(event) => handlePolicyNumberChange("messageRateLimitCooldownSeconds", event.target.value)}
                        className="bg-secondary"
                      />
                    </div>
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">升级封禁阈值</div>
                      <Input
                        type="number"
                        min={1}
                        value={policyDraft?.messageRateLimitBanThreshold ?? ""}
                        onChange={(event) => handlePolicyNumberChange("messageRateLimitBanThreshold", event.target.value)}
                        className="bg-secondary"
                      />
                    </div>
                    <div className="space-y-2">
                      <div className="text-xs text-muted-foreground">封禁时长（秒）</div>
                      <Input
                        type="number"
                        min={1}
                        value={policyDraft?.messageRateLimitBanSeconds ?? ""}
                        onChange={(event) => handlePolicyNumberChange("messageRateLimitBanSeconds", event.target.value)}
                        className="bg-secondary"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <div className="text-xs text-muted-foreground">事件窗口（秒）</div>
                      <Input
                        type="number"
                        min={1}
                        value={policyDraft?.securityIncidentWindowSeconds ?? ""}
                        onChange={(event) => handlePolicyNumberChange("securityIncidentWindowSeconds", event.target.value)}
                        className="bg-secondary"
                      />
                    </div>
                  </CardContent>
                </Card>

                <Card className="bg-secondary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">检测与内容策略</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">规则层阻断阈值</div>
                        <Input
                          type="number"
                          min={1}
                          value={policyDraft?.promptRuleBlockThreshold ?? ""}
                          onChange={(event) => handlePolicyNumberChange("promptRuleBlockThreshold", event.target.value)}
                          className="bg-secondary"
                        />
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs text-muted-foreground">分类层阻断阈值</div>
                        <Input
                          type="number"
                          min={1}
                          value={policyDraft?.promptClassifierBlockThreshold ?? ""}
                          onChange={(event) => handlePolicyNumberChange("promptClassifierBlockThreshold", event.target.value)}
                          className="bg-secondary"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-border bg-card/70 px-4 py-3">
                      <div>
                        <div className="font-medium text-foreground">启用 Prompt Injection 检测</div>
                        <div className="text-xs text-muted-foreground">关闭后将跳过提示注入双层判定。</div>
                      </div>
                      <Switch
                        checked={policyDraft?.promptInjectionEnabled ?? false}
                        onCheckedChange={(checked) => handlePolicyToggle("promptInjectionEnabled", checked)}
                      />
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-border bg-card/70 px-4 py-3">
                      <div>
                        <div className="font-medium text-foreground">启用敏感信息改写</div>
                        <div className="text-xs text-muted-foreground">关闭后将不再对 PII / 凭证进行改写放行。</div>
                      </div>
                      <Switch
                        checked={policyDraft?.contentRedactionEnabled ?? false}
                        onCheckedChange={(checked) => handlePolicyToggle("contentRedactionEnabled", checked)}
                      />
                    </div>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="penalties" className="mt-0">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">活跃处罚</CardTitle>
                  <p className="text-sm text-muted-foreground">查看当前处于冷却/封禁状态的用户，并支持人工解除。</p>
                </div>
                <Badge variant="secondary" className="text-xs">
                  {activePenalties.length} 条
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {penaltiesError && (
                <div className="mb-4 text-sm text-destructive">
                  处罚列表加载失败：{penaltiesError instanceof Error ? penaltiesError.message : "未知错误"}
                </div>
              )}
              <div className="space-y-3">
                {activePenalties.map((penalty) => {
                  const levelMeta = penaltyLevelConfig[penalty.level] ?? {
                    label: penalty.level,
                    color: "bg-secondary text-secondary-foreground",
                  }

                  return (
                    <div
                      key={`${penalty.userKey}:${penalty.until}`}
                      className="rounded-lg border border-border bg-secondary/30 p-4"
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <div className="rounded-lg bg-destructive/10 p-2 text-destructive">
                              <ShieldOff className="size-4" />
                            </div>
                            <span className="font-medium text-foreground">{penalty.userKey}</span>
                            <Badge variant="secondary" className={cn("text-xs", levelMeta.color)}>
                              {levelMeta.label}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground">{penalty.detail}</p>
                          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                            <span>状态码: {penalty.statusCode}</span>
                            <span>截至: {formatDateTime(penalty.until)}</span>
                            <span>更新时间: {formatDateTime(penalty.updatedAt)}</span>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={releasePenaltyMutation.isPending}
                          onClick={() => void handleReleasePenalty(penalty)}
                        >
                          {releasePenaltyMutation.isPending && releasingUserKey === penalty.userKey ? "解除中..." : "解除处罚"}
                        </Button>
                      </div>
                    </div>
                  )
                })}
                {penaltiesLoading && activePenalties.length === 0 && (
                  <div className="flex h-40 items-center justify-center text-muted-foreground">
                    正在加载处罚列表...
                  </div>
                )}
                {!penaltiesLoading && activePenalties.length === 0 && (
                  <div className="flex h-40 items-center justify-center text-muted-foreground">
                    当前没有活跃处罚
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="report" className="mt-0">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <CardTitle className="text-base">安全报告</CardTitle>
                <div className="flex items-center gap-2">
                  <Select value={reportWindowHours} onValueChange={(value) => setReportWindowHours(value as (typeof reportWindowOptions)[number]["value"])}>
                    <SelectTrigger className="w-[160px] bg-secondary">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {reportWindowOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <div className="rounded-md border border-border bg-secondary px-3 py-2 text-xs text-muted-foreground">
                    生成时间 {reportData?.generatedAt?.replace("T", " ").replace("Z", "").slice(0, 19) ?? "--"}
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {reportError && (
                <div className="text-sm text-destructive">
                  安全报告加载失败：{reportError instanceof Error ? reportError.message : "未知错误"}
                </div>
              )}
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <Card className="bg-secondary/40">
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">窗口内事件</div>
                    <div className="mt-2 text-2xl font-bold text-foreground">{reportSummary?.totalEvents ?? 0}</div>
                    <div className="mt-1 text-xs text-muted-foreground">唯一用户 {reportSummary?.uniqueUsers ?? 0}</div>
                  </CardContent>
                </Card>
                <Card className="bg-secondary/40">
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">高风险事件</div>
                    <div className="mt-2 text-2xl font-bold text-destructive">{reportSummary?.highRiskEvents ?? 0}</div>
                    <div className="mt-1 text-xs text-muted-foreground">已阻止 {reportSummary?.blockedThreats ?? 0}</div>
                  </CardContent>
                </Card>
                <Card className="bg-secondary/40">
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">改写放行</div>
                    <div className="mt-2 text-2xl font-bold text-warning">{reportSummary?.rewriteEvents ?? 0}</div>
                    <div className="mt-1 text-xs text-muted-foreground">告警 {reportSummary?.alertNotifications ?? 0}</div>
                  </CardContent>
                </Card>
                <Card className="bg-secondary/40">
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">活跃规则</div>
                    <div className="mt-2 text-2xl font-bold text-success">{reportSummary?.activeRules ?? 0}</div>
                    <div className="mt-1 text-xs text-muted-foreground">规则库当前启用数量</div>
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <Card className="bg-secondary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Radar className="size-4" />
                      状态分布
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {(reportData?.statusBreakdown ?? []).map((item) => (
                      <div key={item.key} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-foreground">{item.label}</span>
                          <span className="text-muted-foreground">
                            {item.count} / {item.share}%
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-secondary">
                          <div
                            className={cn(
                              "h-2 rounded-full",
                              item.key === "error"
                                ? "bg-destructive"
                                : item.key === "warning"
                                  ? "bg-warning"
                                  : "bg-success"
                            )}
                            style={{ width: `${Math.max(item.share, 4)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                    {!reportLoading && (reportData?.statusBreakdown?.length ?? 0) === 0 && (
                      <div className="text-sm text-muted-foreground">当前窗口没有可统计事件。</div>
                    )}
                  </CardContent>
                </Card>

                <Card className="bg-secondary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">高频资源</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {(reportData?.topResources ?? []).map((item) => (
                      <div key={item.key} className="flex items-center justify-between rounded-lg border border-border bg-card/70 px-3 py-2 text-sm">
                        <span className="text-foreground">{item.label}</span>
                        <span className="text-muted-foreground">
                          {item.count} 次 / {item.share}%
                        </span>
                      </div>
                    ))}
                    {!reportLoading && (reportData?.topResources?.length ?? 0) === 0 && (
                      <div className="text-sm text-muted-foreground">暂无资源热点。</div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <Card className="bg-secondary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">高频动作</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {(reportData?.topActions ?? []).map((item) => (
                      <div key={item.key} className="flex items-center justify-between rounded-lg border border-border bg-card/70 px-3 py-2 text-sm">
                        <span className="text-foreground">{item.label}</span>
                        <span className="text-muted-foreground">
                          {item.count} 次 / {item.share}%
                        </span>
                      </div>
                    ))}
                    {!reportLoading && (reportData?.topActions?.length ?? 0) === 0 && (
                      <div className="text-sm text-muted-foreground">暂无动作统计。</div>
                    )}
                  </CardContent>
                </Card>

                <Card className="bg-secondary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">规则命中 Top 5</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {(reportData?.topRules ?? []).map((item) => (
                      <div key={item.key} className="flex items-center justify-between rounded-lg border border-border bg-card/70 px-3 py-2 text-sm">
                        <span className="text-foreground">{item.label}</span>
                        <span className="text-muted-foreground">
                          {item.count.toLocaleString()} 次
                        </span>
                      </div>
                    ))}
                    {!reportLoading && (reportData?.topRules?.length ?? 0) === 0 && (
                      <div className="text-sm text-muted-foreground">暂无规则命中数据。</div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card className="bg-secondary/20">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">最近风险事件</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {(reportData?.recentIncidents ?? []).map((log) => (
                    <div key={log.id} className="rounded-lg border border-border bg-card/70 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <Badge className={cn("text-xs", statusConfig[log.status].color)}>
                            {log.status}
                          </Badge>
                          <span className="font-medium text-foreground">{log.action}</span>
                        </div>
                        <span className="text-xs text-muted-foreground">{log.timestamp}</span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">{log.details}</div>
                      <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                        <span>用户: {log.user}</span>
                        <span>资源: {log.resource}</span>
                        <span>IP: {log.ip}</span>
                      </div>
                    </div>
                  ))}
                  {!reportLoading && (reportData?.recentIncidents?.length ?? 0) === 0 && (
                    <div className="text-sm text-muted-foreground">当前窗口暂无 warning / error 事件。</div>
                  )}
                  {reportLoading && (
                    <div className="text-sm text-muted-foreground">正在生成安全报告...</div>
                  )}
                </CardContent>
              </Card>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
