"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, Plus, RefreshCw, Save, Stethoscope, TerminalSquare, Trash2 } from "lucide-react"
import {
  useCreateExecutor,
  useDeleteExecutor,
  useInstallMissingExecutorDrivers,
  useExecutorRuntimeCapabilities,
  useExecutors,
  useUpdateExecutor,
  useValidateExecutor,
} from "@/modules/executor-config/hooks/use-executor-config"
import { ApiError } from "@/platform/api/errors"
import { toast } from "@/shared/hooks/use-toast"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select"
import { Switch } from "@/shared/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import type {
  Executor,
  ExecutorApprovalPolicy,
  ExecutorCreateRequest,
  ExecutorDriverType,
  ExecutorRunMode,
  ExecutorShellPermission,
  ExecutorWorkspacePolicy,
} from "@/shared/types"
import { cn } from "@/shared/utils"

type ExecutorDraft = {
  name: string
  driverType: ExecutorDriverType
  runMode: ExecutorRunMode
  entry: string
  workspacePolicy: ExecutorWorkspacePolicy
  shellPermission: ExecutorShellPermission
  approvalPolicy: ExecutorApprovalPolicy
  timeoutSeconds: string
  enabled: boolean
}

type LocalExecutorDriverType = Extract<ExecutorDriverType, "codex_cli" | "claude_code_cli">

const statusLabelMap: Record<string, string> = {
  unknown: "未知",
  online: "在线",
  offline: "离线",
  degraded: "降级",
}

const statusClassMap: Record<string, string> = {
  unknown: "bg-secondary text-muted-foreground",
  online: "bg-success/20 text-success",
  offline: "bg-destructive/15 text-destructive",
  degraded: "bg-warning/20 text-warning-foreground",
}

const initialDraft: ExecutorDraft = {
  name: "",
  driverType: "codex_cli",
  runMode: "local",
  entry: "codex",
  workspacePolicy: "tenant_sandbox",
  shellPermission: "limited_exec",
  approvalPolicy: "confirm_on_risk",
  timeoutSeconds: "120",
  enabled: true,
}

const localDriverTypeOrder: LocalExecutorDriverType[] = ["codex_cli", "claude_code_cli"]

const driverTypeLabelMap: Record<ExecutorDriverType, string> = {
  codex_cli: "Codex CLI（本地）",
  claude_code_cli: "Claude Code CLI（本地）",
  http_runner: "HTTP Runner（远程）",
}

const runModeLabelMap: Record<ExecutorRunMode, string> = {
  local: "本地运行",
  remote: "远程运行",
}

const workspacePolicyLabelMap: Record<ExecutorWorkspacePolicy, string> = {
  tenant_sandbox: "租户沙箱目录",
  fixed_path: "固定工作目录",
}

const shellPermissionLabelMap: Record<ExecutorShellPermission, string> = {
  read_only: "只读",
  limited_exec: "受限执行",
  full_exec: "全量执行",
}

const approvalPolicyLabelMap: Record<ExecutorApprovalPolicy, string> = {
  auto: "自动放行",
  confirm_on_risk: "风险时确认",
  always_confirm: "始终确认",
}

function formatTime(value?: string | null): string {
  if (!value) return "--"
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return value
  return new Date(timestamp).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function toDraft(executor: Executor): ExecutorDraft {
  return {
    name: executor.name,
    driverType: executor.driverType,
    runMode: executor.runMode,
    entry: executor.entry || "",
    workspacePolicy: executor.workspacePolicy,
    shellPermission: executor.shellPermission,
    approvalPolicy: executor.approvalPolicy,
    timeoutSeconds: String(executor.timeoutSeconds || 120),
    enabled: executor.enabled,
  }
}

function toCreatePayload(draft: ExecutorDraft): ExecutorCreateRequest {
  const timeout = Number.parseInt(draft.timeoutSeconds.trim(), 10)
  return {
    name: draft.name.trim(),
    driverType: draft.driverType,
    runMode: draft.runMode,
    entry: draft.entry.trim(),
    workspacePolicy: draft.workspacePolicy,
    shellPermission: draft.shellPermission,
    approvalPolicy: draft.approvalPolicy,
    blockedCommands: [],
    timeoutSeconds: Number.isFinite(timeout) && timeout > 0 ? timeout : 120,
    enabled: draft.enabled,
  }
}

function statusLabel(status: string): string {
  return statusLabelMap[status] ?? (status || "未知")
}

function statusClass(status: string): string {
  return statusClassMap[status] ?? "bg-secondary text-muted-foreground"
}

function buildDefaultEntry(driverType: ExecutorDriverType, runMode: ExecutorRunMode) {
  if (runMode === "remote") return "http://127.0.0.1:8001"
  if (driverType === "codex_cli") return "codex"
  if (driverType === "claude_code_cli") return "claude"
  return "http://127.0.0.1:8001"
}

function shouldApplyDefaultEntry(entry: string) {
  const normalized = entry.trim()
  return !normalized || normalized === "codex" || normalized === "claude" || normalized === "http://127.0.0.1:8001"
}

function normalizeLocalDriverTypes(types: ExecutorDriverType[] | undefined): LocalExecutorDriverType[] {
  if (!Array.isArray(types)) {
    return []
  }
  return localDriverTypeOrder.filter((driverType) => types.includes(driverType))
}

function normalizeDraftForSubmit(
  value: ExecutorDraft,
  availableLocalDriverTypes: LocalExecutorDriverType[],
): ExecutorDraft | null {
  if (value.runMode === "remote") {
    return {
      ...value,
      driverType: "http_runner",
      entry: value.entry.trim() || buildDefaultEntry("http_runner", "remote"),
    }
  }
  if (availableLocalDriverTypes.length === 0) {
    return null
  }
  const safeDriverType = availableLocalDriverTypes.includes(value.driverType as LocalExecutorDriverType)
    ? (value.driverType as LocalExecutorDriverType)
    : availableLocalDriverTypes[0]
  return {
    ...value,
    driverType: safeDriverType,
    entry: value.entry.trim() || buildDefaultEntry(safeDriverType, "local"),
  }
}

function resolveDriverSelectValue(
  value: ExecutorDraft,
  availableLocalDriverTypes: LocalExecutorDriverType[],
): ExecutorDriverType {
  if (value.runMode === "remote") {
    return "http_runner"
  }
  if (availableLocalDriverTypes.length === 0) {
    return value.driverType
  }
  if (availableLocalDriverTypes.includes(value.driverType as LocalExecutorDriverType)) {
    return value.driverType
  }
  return availableLocalDriverTypes[0]
}

function getRequiredErrors(value: ExecutorDraft) {
  return {
    name: !value.name.trim(),
    entry: value.runMode === "remote" && !value.entry.trim(),
  }
}

function slugifyExecutorPart(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32)
}

function buildLegacyExecutorId(draft: ExecutorDraft): string {
  const driverPartMap: Record<ExecutorDriverType, string> = {
    codex_cli: "codex",
    claude_code_cli: "claude",
    http_runner: "http",
  }
  const namePart = slugifyExecutorPart(draft.name) || "runner"
  const random = Math.random().toString(36).slice(2, 8)
  return `executor-${driverPartMap[draft.driverType]}-${namePart}-${random}`
}

function shouldRetryWithLegacyId(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 422) return false
  const detail = error.details
  if (!detail || typeof detail !== "object" || !("detail" in detail)) return false
  const details = (detail as { detail?: unknown }).detail
  if (!Array.isArray(details)) return false
  return details.some((item) => {
    if (!item || typeof item !== "object") return false
    const loc = (item as { loc?: unknown }).loc
    return Array.isArray(loc) && loc.includes("id")
  })
}

export default function ExecutorSettingsPage() {
  const executorsQuery = useExecutors()
  const runtimeCapabilitiesQuery = useExecutorRuntimeCapabilities()
  const createExecutorMutation = useCreateExecutor()
  const updateExecutorMutation = useUpdateExecutor()
  const deleteExecutorMutation = useDeleteExecutor()
  const validateExecutorMutation = useValidateExecutor()
  const installMissingDriversMutation = useInstallMissingExecutorDrivers()

  const [selectedExecutorId, setSelectedExecutorId] = useState<string | null>(null)
  const [draft, setDraft] = useState<ExecutorDraft>(initialDraft)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createDraft, setCreateDraft] = useState<ExecutorDraft>(initialDraft)

  const executors = useMemo(() => {
    const items = executorsQuery.data?.items ?? []
    return [...items].sort((left, right) => {
      if (left.enabled !== right.enabled) {
        return left.enabled ? -1 : 1
      }
      if (left.status !== right.status) {
        if (left.status === "online") return -1
        if (right.status === "online") return 1
      }
      return left.name.localeCompare(right.name, "zh-CN")
    })
  }, [executorsQuery.data?.items])

  const availableLocalDriverTypes = useMemo(
    () => normalizeLocalDriverTypes(runtimeCapabilitiesQuery.data?.availableLocalDriverTypes),
    [runtimeCapabilitiesQuery.data?.availableLocalDriverTypes],
  )

  const missingLocalDrivers = useMemo(() => {
    const localDrivers = runtimeCapabilitiesQuery.data?.localDrivers ?? []
    return localDrivers.filter((driver) => !driver.installed)
  }, [runtimeCapabilitiesQuery.data?.localDrivers])

  const missingLocalDriverTypes = useMemo(
    () => normalizeLocalDriverTypes(runtimeCapabilitiesQuery.data?.missingLocalDriverTypes),
    [runtimeCapabilitiesQuery.data?.missingLocalDriverTypes],
  )
  const runtimeProbeHasAnyLocalDriver = availableLocalDriverTypes.length > 0

  const selectedExecutor = useMemo(
    () => executors.find((item) => item.id === selectedExecutorId) ?? null,
    [executors, selectedExecutorId],
  )

  useEffect(() => {
    if (selectedExecutorId && !executors.some((item) => item.id === selectedExecutorId)) {
      setSelectedExecutorId(null)
    }
  }, [executors, selectedExecutorId])

  useEffect(() => {
    if (selectedExecutor) {
      setDraft(toDraft(selectedExecutor))
    }
  }, [selectedExecutor])

  const summary = useMemo(() => {
    return {
      total: executors.length,
      enabled: executors.filter((item) => item.enabled).length,
      online: executors.filter((item) => item.status === "online").length,
      offline: executors.filter((item) => item.status === "offline" || item.status === "unknown").length,
    }
  }, [executors])

  const isCreating = createExecutorMutation.isPending
  const isUpdating = updateExecutorMutation.isPending
  const requiredErrors = useMemo(() => getRequiredErrors(draft), [draft])
  const createRequiredErrors = useMemo(() => getRequiredErrors(createDraft), [createDraft])
  const hasLocalDriverAvailable = runtimeProbeHasAnyLocalDriver

  const setField = <TKey extends keyof ExecutorDraft>(field: TKey, value: ExecutorDraft[TKey]) => {
    setDraft((current) => ({
      ...current,
      [field]: value,
    }))
  }

  const setCreateField = <TKey extends keyof ExecutorDraft>(field: TKey, value: ExecutorDraft[TKey]) => {
    setCreateDraft((current) => ({
      ...current,
      [field]: value,
    }))
  }

  const resetToNewDraft = () => {
    setSelectedExecutorId(null)
    setDraft(initialDraft)
  }

  const openCreateDialog = () => {
    const defaultRunMode: ExecutorRunMode = hasLocalDriverAvailable ? "local" : "remote"
    const defaultDriverType: ExecutorDriverType =
      defaultRunMode === "local" ? availableLocalDriverTypes[0] : "http_runner"
    setCreateDraft({
      ...initialDraft,
      runMode: defaultRunMode,
      driverType: defaultDriverType,
      entry: buildDefaultEntry(defaultDriverType, defaultRunMode),
    })
    setCreateDialogOpen(true)
  }

  const saveNewExecutor = async () => {
    const normalizedDraft = normalizeDraftForSubmit(createDraft, availableLocalDriverTypes)
    if (!normalizedDraft) {
      toast({
        title: "本地驱动未安装",
        description: "未检测到可用的本地 CLI，请先安装后再使用本地运行，或切换到远程运行。",
        variant: "destructive",
      })
      return
    }
    const payload = toCreatePayload(normalizedDraft)
    if (createRequiredErrors.name || createRequiredErrors.entry) {
      const reasons: string[] = []
      if (createRequiredErrors.name) reasons.push("执行器名称")
      if (createRequiredErrors.entry) reasons.push("入口（命令或URL）")
      toast({
        title: "缺少必填项",
        description: `请先填写：${reasons.join("、")}`,
        variant: "destructive",
      })
      return
    }

    try {
      const response = await createExecutorMutation.mutateAsync(payload)
      setSelectedExecutorId(response.executor.id)
      setCreateDialogOpen(false)
      toast({ title: "执行器已创建", description: response.message })
    } catch (error) {
      if (shouldRetryWithLegacyId(error)) {
        try {
          const response = await createExecutorMutation.mutateAsync({
            ...payload,
            id: buildLegacyExecutorId(normalizedDraft),
          })
          setSelectedExecutorId(response.executor.id)
          setCreateDialogOpen(false)
          toast({ title: "执行器已创建", description: response.message })
          return
        } catch (retryError) {
          toast({
            title: "新建失败",
            description: retryError instanceof Error ? retryError.message : "执行器新建失败",
            variant: "destructive",
          })
          return
        }
      }
      toast({
        title: "新建失败",
        description: error instanceof Error ? error.message : "执行器新建失败",
        variant: "destructive",
      })
    }
  }

  const updateExecutorConfig = async () => {
    if (!selectedExecutor) {
      toast({
        title: "未选择执行器",
        description: "请先在左侧选择一个执行器后再更新。",
        variant: "destructive",
      })
      return
    }

    const normalizedDraft = normalizeDraftForSubmit(draft, availableLocalDriverTypes)
    if (!normalizedDraft) {
      toast({
        title: "本地驱动未安装",
        description: "未检测到可用的本地 CLI，请先安装后再保存本地运行配置，或切换到远程运行。",
        variant: "destructive",
      })
      return
    }
    const payload = toCreatePayload(normalizedDraft)
    if (requiredErrors.name || requiredErrors.entry) {
      const reasons: string[] = []
      if (requiredErrors.name) reasons.push("执行器名称")
      if (requiredErrors.entry) reasons.push("入口（命令或URL）")
      toast({
        title: "缺少必填项",
        description: `请先填写：${reasons.join("、")}`,
        variant: "destructive",
      })
      return
    }

    try {
      const response = await updateExecutorMutation.mutateAsync({
        executorId: selectedExecutor.id,
        payload,
      })
      setSelectedExecutorId(response.executor.id)
      toast({ title: "执行器已更新", description: response.message })
    } catch (error) {
      toast({
        title: "更新失败",
        description: error instanceof Error ? error.message : "执行器更新失败",
        variant: "destructive",
      })
    }
  }

  const validateSelectedExecutor = async () => {
    if (!selectedExecutor) return
    try {
      const response = await validateExecutorMutation.mutateAsync(selectedExecutor.id)
      toast({
        title: response.ok ? "校验通过" : "校验失败",
        description: response.message,
        variant: response.ok ? "default" : "destructive",
      })
    } catch (error) {
      toast({
        title: "校验失败",
        description: error instanceof Error ? error.message : "执行器校验失败",
        variant: "destructive",
      })
    }
  }

  const deleteSelectedExecutor = async () => {
    if (!selectedExecutor) return
    if (!window.confirm(`确认删除执行器 ${selectedExecutor.name}？`)) {
      return
    }
    try {
      const response = await deleteExecutorMutation.mutateAsync(selectedExecutor.id)
      toast({ title: "执行器已删除", description: response.message })
      resetToNewDraft()
    } catch (error) {
      toast({
        title: "删除失败",
        description: error instanceof Error ? error.message : "执行器删除失败",
        variant: "destructive",
      })
    }
  }

  const installMissingDrivers = async () => {
    if (missingLocalDriverTypes.length === 0) {
      toast({ title: "无需安装", description: "当前没有缺失的本地执行器 CLI。" })
      return
    }

    try {
      const response = await installMissingDriversMutation.mutateAsync({
        targets: missingLocalDriverTypes,
      })
      const failedItems = response.results.filter((item) => !item.installed)
      if (failedItems.length > 0) {
        toast({
          title: "安装部分失败",
          description: failedItems.map((item) => driverTypeLabelMap[item.driverType]).join("、"),
          variant: "destructive",
        })
      } else {
        toast({
          title: "安装完成",
          description: response.message,
        })
      }
      void runtimeCapabilitiesQuery.refetch()
    } catch (error) {
      toast({
        title: "安装失败",
        description: error instanceof Error ? error.message : "安装缺失 CLI 失败",
        variant: "destructive",
      })
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-6">
      <Card className="bg-card">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-lg">
                <TerminalSquare className="size-5" />
                执行器接入（内部）
              </CardTitle>
              <div className="mt-1 text-sm text-muted-foreground">
                执行器是内部 Agent 的动作执行层，不是外接 Agent 注册。
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  void executorsQuery.refetch()
                  void runtimeCapabilitiesQuery.refetch()
                }}
                disabled={executorsQuery.isFetching || runtimeCapabilitiesQuery.isFetching}
              >
                <RefreshCw className="mr-2 size-4" />
                刷新
              </Button>
              <Button variant="outline" onClick={openCreateDialog}>
                <Plus className="mr-2 size-4" />
                新建
              </Button>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="secondary">总数：{summary.total}</Badge>
            <Badge variant="secondary" className="bg-success/20 text-success">
              已启用：{summary.enabled}
            </Badge>
            <Badge variant="secondary" className="bg-success/20 text-success">
              在线：{summary.online}
            </Badge>
            <Badge variant="secondary">离线/未知：{summary.offline}</Badge>
          </div>
        </CardHeader>
      </Card>

      {executorsQuery.error ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            执行器列表加载失败：{executorsQuery.error instanceof Error ? executorsQuery.error.message : "未知错误"}
          </CardContent>
        </Card>
      ) : null}

      {runtimeCapabilitiesQuery.error ? (
        <Card className="border-destructive/40 bg-card">
          <CardContent className="p-4 text-sm text-destructive">
            运行环境探测失败：
            {runtimeCapabilitiesQuery.error instanceof Error
              ? runtimeCapabilitiesQuery.error.message
              : "无法获取本地/远程驱动能力"}
          </CardContent>
        </Card>
      ) : null}

      {missingLocalDrivers.length > 0 ? (
        <Card className="border-warning/40 bg-card">
          <CardContent className="p-4 text-sm text-foreground">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 size-4 text-warning-foreground" />
                <div className="space-y-1">
                  <div className="font-medium">
                    {runtimeProbeHasAnyLocalDriver ? "本地执行器未完全安装" : "本地执行器未安装"}
                  </div>
                  <div className="text-muted-foreground">
                    缺少命令：
                    {missingLocalDrivers.map((driver) => driver.command).join("、")}。安装后点击“刷新”重新探测。
                  </div>
                  <div className="text-xs text-muted-foreground">
                    可用性检查命令：{missingLocalDrivers.map((driver) => `${driver.command} --version`).join(" / ")}
                  </div>
                </div>
              </div>
              <Button
                variant="outline"
                onClick={installMissingDrivers}
                disabled={installMissingDriversMutation.isPending || missingLocalDriverTypes.length === 0}
              >
                {installMissingDriversMutation.isPending ? <RefreshCw className="mr-2 size-4 animate-spin" /> : null}
                安装缺失 CLI
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="flex min-h-0 flex-col bg-card">
          <CardHeader className={cn("pb-3", !selectedExecutor && "hidden")}>
            <CardTitle className="text-base">执行器列表</CardTitle>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
            {executors.length === 0 && !executorsQuery.isLoading ? (
              <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
                还没有执行器，先在右侧新建一个内部执行器。
              </div>
            ) : null}

            {executors.map((executor) => (
              <button
                key={executor.id}
                type="button"
                onClick={() => setSelectedExecutorId(executor.id)}
                className={cn(
                  "w-full rounded-xl border p-4 text-left transition-colors",
                  selectedExecutorId === executor.id
                    ? "border-primary bg-primary/5"
                    : "border-border bg-secondary/20 hover:border-primary/30",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="font-medium text-foreground">{executor.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {driverTypeLabelMap[executor.driverType]} · {runModeLabelMap[executor.runMode]}
                    </div>
                  </div>
                  <Badge variant="secondary" className={cn("text-xs", statusClass(executor.status))}>
                    {statusLabel(executor.status)}
                  </Badge>
                </div>
                <div className="mt-3 grid gap-1 text-xs text-muted-foreground">
                  <div>{executor.enabled ? "已启用" : "已停用"}</div>
                  <div>最近校验：{formatTime(executor.lastValidatedAt)}</div>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="flex min-h-0 flex-col bg-card">
          <CardHeader className={cn("pb-3", !selectedExecutor && "hidden")}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs
                value={draft.runMode}
                onValueChange={(value) => {
                  const runMode = value as ExecutorRunMode
                  if (runMode === draft.runMode) return
                  if (runMode === "local" && !hasLocalDriverAvailable) {
                    toast({
                      title: "本地驱动未安装",
                      description: "未检测到可用的本地 CLI，请先安装后再切换到本地运行。",
                      variant: "destructive",
                    })
                    return
                  }
                  setField("runMode", runMode)
                  if (runMode === "remote") {
                    setField("driverType", "http_runner")
                    if (shouldApplyDefaultEntry(draft.entry)) {
                      setField("entry", buildDefaultEntry("http_runner", "remote"))
                    }
                    return
                  }
                  const nextDriverType = availableLocalDriverTypes.includes(draft.driverType as LocalExecutorDriverType)
                    ? (draft.driverType as LocalExecutorDriverType)
                    : availableLocalDriverTypes[0]
                  setField("driverType", nextDriverType)
                  if (shouldApplyDefaultEntry(draft.entry)) {
                    setField("entry", buildDefaultEntry(nextDriverType, "local"))
                  }
                }}
              >
                <TabsList className="bg-secondary">
                  <TabsTrigger value="local">{runModeLabelMap.local}</TabsTrigger>
                  <TabsTrigger value="remote">{runModeLabelMap.remote}</TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="flex items-center gap-3 px-3 py-2">
                <div className="text-sm text-muted-foreground">启用状态</div>
                <Switch checked={draft.enabled} onCheckedChange={(checked) => setField("enabled", checked)} />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={updateExecutorConfig} disabled={!selectedExecutor || isUpdating}>
                  <Save className="mr-2 size-4" />
                  更新
                </Button>
                <Button
                  variant="outline"
                  onClick={validateSelectedExecutor}
                  disabled={!selectedExecutor || validateExecutorMutation.isPending}
                >
                  <Stethoscope className="mr-2 size-4" />
                  校验接入
                </Button>
                <Button
                  variant="destructive"
                  onClick={deleteSelectedExecutor}
                  disabled={!selectedExecutor || deleteExecutorMutation.isPending}
                >
                  <Trash2 className="mr-2 size-4" />
                  删除
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-y-auto pr-1">
            {!selectedExecutor ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                请先在左侧选择一个执行器
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-1">
              <div className="space-y-2">
                <Label htmlFor="executor-name">
                  执行器名称 <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="executor-name"
                  placeholder="Codex Local Runner"
                  value={draft.name}
                  onChange={(event) => setField("name", event.target.value)}
                  className={requiredErrors.name ? "border-destructive focus-visible:ring-destructive" : ""}
                />
                {requiredErrors.name ? (
                  <div className="text-xs text-destructive">执行器名称为必填项。</div>
                ) : null}
              </div>
                </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>
                  驱动类型 <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={resolveDriverSelectValue(draft, availableLocalDriverTypes)}
                  onValueChange={(value) => {
                    const driverType = value as ExecutorDriverType
                    setField("driverType", driverType)
                    if (
                      shouldApplyDefaultEntry(draft.entry)
                    ) {
                      setField("entry", buildDefaultEntry(driverType, draft.runMode))
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {draft.runMode === "remote" ? (
                      <SelectItem value="http_runner">{driverTypeLabelMap.http_runner}</SelectItem>
                    ) : (
                      availableLocalDriverTypes.map((driverType) => (
                        <SelectItem key={driverType} value={driverType}>
                          {driverTypeLabelMap[driverType]}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
                {draft.runMode === "local" && availableLocalDriverTypes.length === 0 ? (
                  <div className="text-xs text-destructive">当前环境未检测到本地驱动，请先安装 codex 或 claude 命令。</div>
                ) : null}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="executor-entry">
                {draft.runMode === "remote" ? "远程入口 URL" : "本地入口命令"}
                {draft.runMode === "remote" ? <span className="text-destructive"> *</span> : null}
              </Label>
              <Input
                id="executor-entry"
                placeholder={draft.runMode === "remote" ? "http://127.0.0.1:8001" : "codex"}
                value={draft.entry}
                onChange={(event) => setField("entry", event.target.value)}
                className={requiredErrors.entry ? "border-destructive focus-visible:ring-destructive" : ""}
              />
              {draft.runMode === "local" ? (
                <div className="text-xs text-muted-foreground">本地模式可留空，系统会按驱动类型自动填充默认命令。</div>
              ) : null}
              {requiredErrors.entry ? (
                <div className="text-xs text-destructive">远程模式下入口为必填项。</div>
              ) : null}
            </div>

            {draft.runMode === "local" ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>工作目录策略</Label>
                  <Select
                    value={draft.workspacePolicy}
                    onValueChange={(value) => setField("workspacePolicy", value as ExecutorWorkspacePolicy)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="tenant_sandbox">{workspacePolicyLabelMap.tenant_sandbox}</SelectItem>
                      <SelectItem value="fixed_path">{workspacePolicyLabelMap.fixed_path}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Shell 权限</Label>
                  <Select
                    value={draft.shellPermission}
                    onValueChange={(value) => setField("shellPermission", value as ExecutorShellPermission)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="read_only">{shellPermissionLabelMap.read_only}</SelectItem>
                      <SelectItem value="limited_exec">{shellPermissionLabelMap.limited_exec}</SelectItem>
                      <SelectItem value="full_exec">{shellPermissionLabelMap.full_exec}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ) : null}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>审批策略</Label>
                <Select
                  value={draft.approvalPolicy}
                  onValueChange={(value) => setField("approvalPolicy", value as ExecutorApprovalPolicy)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{approvalPolicyLabelMap.auto}</SelectItem>
                    <SelectItem value="confirm_on_risk">{approvalPolicyLabelMap.confirm_on_risk}</SelectItem>
                    <SelectItem value="always_confirm">{approvalPolicyLabelMap.always_confirm}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="executor-timeout">超时（秒）</Label>
                <Input
                  id="executor-timeout"
                  type="number"
                  min={10}
                  value={draft.timeoutSeconds}
                  onChange={(event) => setField("timeoutSeconds", event.target.value)}
                />
              </div>
            </div>

                <div className="rounded-xl border border-border bg-secondary/20 p-4 text-sm">
                  <div className="mb-2 font-medium text-foreground">观测状态</div>
                  <div className="grid gap-1 text-muted-foreground">
                    <div>状态：{statusLabel(selectedExecutor.status)}</div>
                    <div>最近校验：{formatTime(selectedExecutor.lastValidatedAt)}</div>
                    <div>校验信息：{selectedExecutor.validationMessage || "--"}</div>
                    <div>版本信息：{selectedExecutor.versionInfo || "--"}</div>
                    <div>最近错误：{selectedExecutor.lastError || "--"}</div>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>新建执行器</DialogTitle>
          </DialogHeader>

          <div className="space-y-6 py-1">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs
                value={createDraft.runMode}
                onValueChange={(value) => {
                  const runMode = value as ExecutorRunMode
                  if (runMode === createDraft.runMode) return
                  if (runMode === "local" && !hasLocalDriverAvailable) {
                    toast({
                      title: "本地驱动未安装",
                      description: "未检测到可用的本地 CLI，请先安装后再切换到本地运行。",
                      variant: "destructive",
                    })
                    return
                  }
                  setCreateField("runMode", runMode)
                  if (runMode === "remote") {
                    setCreateField("driverType", "http_runner")
                    if (shouldApplyDefaultEntry(createDraft.entry)) {
                      setCreateField("entry", buildDefaultEntry("http_runner", "remote"))
                    }
                    return
                  }
                  const nextDriverType = availableLocalDriverTypes.includes(
                    createDraft.driverType as LocalExecutorDriverType,
                  )
                    ? (createDraft.driverType as LocalExecutorDriverType)
                    : availableLocalDriverTypes[0]
                  setCreateField("driverType", nextDriverType)
                  if (shouldApplyDefaultEntry(createDraft.entry)) {
                    setCreateField("entry", buildDefaultEntry(nextDriverType, "local"))
                  }
                }}
              >
                <TabsList className="bg-secondary">
                  <TabsTrigger value="local">{runModeLabelMap.local}</TabsTrigger>
                  <TabsTrigger value="remote">{runModeLabelMap.remote}</TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="flex items-center gap-3 px-3 py-2">
                <div className="text-sm text-muted-foreground">启用状态</div>
                <Switch checked={createDraft.enabled} onCheckedChange={(checked) => setCreateField("enabled", checked)} />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-1">
              <div className="space-y-2">
                <Label htmlFor="create-executor-name">
                  执行器名称 <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="create-executor-name"
                  placeholder="Codex Local Runner"
                  value={createDraft.name}
                  onChange={(event) => setCreateField("name", event.target.value)}
                  className={createRequiredErrors.name ? "border-destructive focus-visible:ring-destructive" : ""}
                />
                {createRequiredErrors.name ? (
                  <div className="text-xs text-destructive">执行器名称为必填项。</div>
                ) : null}
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>
                  驱动类型 <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={resolveDriverSelectValue(createDraft, availableLocalDriverTypes)}
                  onValueChange={(value) => {
                    const driverType = value as ExecutorDriverType
                    setCreateField("driverType", driverType)
                    if (
                      shouldApplyDefaultEntry(createDraft.entry)
                    ) {
                      setCreateField("entry", buildDefaultEntry(driverType, createDraft.runMode))
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {createDraft.runMode === "remote" ? (
                      <SelectItem value="http_runner">{driverTypeLabelMap.http_runner}</SelectItem>
                    ) : (
                      availableLocalDriverTypes.map((driverType) => (
                        <SelectItem key={driverType} value={driverType}>
                          {driverTypeLabelMap[driverType]}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
                {createDraft.runMode === "local" && availableLocalDriverTypes.length === 0 ? (
                  <div className="text-xs text-destructive">当前环境未检测到本地驱动，请先安装 codex 或 claude 命令。</div>
                ) : null}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="create-executor-entry">
                {createDraft.runMode === "remote" ? "远程入口 URL" : "本地入口命令"}
                {createDraft.runMode === "remote" ? <span className="text-destructive"> *</span> : null}
              </Label>
              <Input
                id="create-executor-entry"
                placeholder={createDraft.runMode === "remote" ? "http://127.0.0.1:8001" : "codex"}
                value={createDraft.entry}
                onChange={(event) => setCreateField("entry", event.target.value)}
                className={createRequiredErrors.entry ? "border-destructive focus-visible:ring-destructive" : ""}
              />
              {createDraft.runMode === "local" ? (
                <div className="text-xs text-muted-foreground">本地模式可留空，系统会按驱动类型自动填充默认命令。</div>
              ) : null}
              {createRequiredErrors.entry ? (
                <div className="text-xs text-destructive">远程模式下入口为必填项。</div>
              ) : null}
            </div>

            {createDraft.runMode === "local" ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>工作目录策略</Label>
                  <Select
                    value={createDraft.workspacePolicy}
                    onValueChange={(value) => setCreateField("workspacePolicy", value as ExecutorWorkspacePolicy)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="tenant_sandbox">{workspacePolicyLabelMap.tenant_sandbox}</SelectItem>
                      <SelectItem value="fixed_path">{workspacePolicyLabelMap.fixed_path}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Shell 权限</Label>
                  <Select
                    value={createDraft.shellPermission}
                    onValueChange={(value) => setCreateField("shellPermission", value as ExecutorShellPermission)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="read_only">{shellPermissionLabelMap.read_only}</SelectItem>
                      <SelectItem value="limited_exec">{shellPermissionLabelMap.limited_exec}</SelectItem>
                      <SelectItem value="full_exec">{shellPermissionLabelMap.full_exec}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ) : null}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>审批策略</Label>
                <Select
                  value={createDraft.approvalPolicy}
                  onValueChange={(value) => setCreateField("approvalPolicy", value as ExecutorApprovalPolicy)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{approvalPolicyLabelMap.auto}</SelectItem>
                    <SelectItem value="confirm_on_risk">{approvalPolicyLabelMap.confirm_on_risk}</SelectItem>
                    <SelectItem value="always_confirm">{approvalPolicyLabelMap.always_confirm}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-executor-timeout">超时（秒）</Label>
                <Input
                  id="create-executor-timeout"
                  type="number"
                  min={10}
                  value={createDraft.timeoutSeconds}
                  onChange={(event) => setCreateField("timeoutSeconds", event.target.value)}
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)} disabled={isCreating}>
              取消
            </Button>
            <Button onClick={saveNewExecutor} disabled={isCreating}>
              <Save className="mr-2 size-4" />
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
