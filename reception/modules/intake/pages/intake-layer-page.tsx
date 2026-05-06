"use client"

import Link from "next/link"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Bot,
  CheckCircle2,
  ClipboardCheck,
  RefreshCw,
  ShieldAlert,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react"
import { useManagedUserTenants } from "@/modules/organization/hooks/use-users"
import { buildAuthenticatedWebSocketUrl } from "@/platform/api/auth-storage"
import { apiRequest } from "@/platform/api/client"
import { WS_BASE_URL } from "@/platform/api/config"
import { queryKeys } from "@/platform/query/query-keys"
import type {
  IntakeActiveTaskPreview,
  IntakeAdmissionEvent,
  IntakeAdmissionStatus,
  IntakeConsoleOverviewResponse,
  IntakeHermesEvent,
  IntakeKnowledgeHitPreview,
  IntakeReceptionSession,
  IntakeReceptionSessionState,
  IntakeSecurityEvent,
  IntakeTraceDetailResponse,
} from "@/shared/types"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/shared/ui/sheet"
import { Skeleton } from "@/shared/ui/skeleton"

type LiveConnectionState = "connecting" | "connected" | "disconnected" | "error"

const CHANNEL_OPTIONS = [
  { value: "all", label: "全部渠道" },
  { value: "dingtalk", label: "钉钉" },
  { value: "wecom", label: "企业微信" },
  { value: "feishu", label: "飞书" },
  { value: "telegram", label: "Telegram" },
]

function formatTimestamp(value?: string | null) {
  const normalized = String(value || "").trim()
  if (!normalized) return "--"
  const parsed = Date.parse(normalized)
  if (!Number.isFinite(parsed)) return normalized
  return new Date(parsed).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function channelLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "dingtalk") return "钉钉"
  if (normalized === "wecom") return "企业微信"
  if (normalized === "feishu") return "飞书"
  if (normalized === "telegram") return "Telegram"
  return value || "未知渠道"
}

function admissionStatusMeta(status: IntakeAdmissionStatus) {
  if (status === "passed") {
    return { label: "通过", tone: "bg-success/10 text-success" }
  }
  if (status === "pending_verification") {
    return { label: "待补充", tone: "bg-warning/10 text-warning-foreground" }
  }
  if (status === "rejected") {
    return { label: "拒绝", tone: "bg-destructive/10 text-destructive" }
  }
  return { label: "安全阻断", tone: "bg-destructive/10 text-destructive" }
}

function sessionStateMeta(state: IntakeReceptionSessionState) {
  if (state === "serving") {
    return { label: "接待中", tone: "bg-primary/10 text-primary" }
  }
  if (state === "replied") {
    return { label: "已回复", tone: "bg-success/10 text-success" }
  }
  return { label: "异常", tone: "bg-destructive/10 text-destructive" }
}

function inputSecurityMeta(status?: string | null) {
  const normalized = String(status || "").trim().toLowerCase()
  if (normalized === "passed") {
    return { label: "通过", tone: "bg-success/10 text-success" }
  }
  if (normalized === "pending_verification") {
    return { label: "待补充", tone: "bg-warning/10 text-warning-foreground" }
  }
  if (normalized === "rejected") {
    return { label: "拒绝", tone: "bg-destructive/10 text-destructive" }
  }
  if (normalized === "security_blocked") {
    return { label: "安全阻断", tone: "bg-destructive/10 text-destructive" }
  }
  return { label: "待判定", tone: "bg-muted text-muted-foreground" }
}

function outputSecurityMeta(status?: string | null) {
  const normalized = String(status || "").trim().toLowerCase()
  if (normalized === "listening") {
    return { label: "监听中", tone: "bg-primary/10 text-primary" }
  }
  if (normalized === "passed") {
    return { label: "已放行", tone: "bg-success/10 text-success" }
  }
  if (normalized === "blocked") {
    return { label: "已阻断", tone: "bg-destructive/10 text-destructive" }
  }
  if (normalized === "failed") {
    return { label: "异常", tone: "bg-destructive/10 text-destructive" }
  }
  return { label: "待判定", tone: "bg-muted text-muted-foreground" }
}

function liveConnectionMeta(state: LiveConnectionState) {
  if (state === "connected") {
    return {
      label: "实时推流已连接",
      tone: "bg-success/10 text-success",
      icon: <Wifi className="size-3.5" />,
    }
  }
  if (state === "connecting") {
    return {
      label: "实时推流连接中",
      tone: "bg-warning/10 text-warning-foreground",
      icon: <Wifi className="size-3.5" />,
    }
  }
  if (state === "error") {
    return {
      label: "实时推流异常",
      tone: "bg-destructive/10 text-destructive",
      icon: <WifiOff className="size-3.5" />,
    }
  }
  return {
    label: "实时推流未连接",
    tone: "bg-muted text-muted-foreground",
    icon: <WifiOff className="size-3.5" />,
  }
}

function personLabel(item: { personName?: string | null; platformUserId?: string | null }) {
  return item.personName || item.platformUserId || "未识别客户"
}

function hasDisplayValue(value?: string | null): value is string {
  return String(value || "").trim().length > 0
}

function displayText(value?: string | null, fallback = "--") {
  const normalized = String(value || "").trim()
  return normalized || fallback
}

function displayStatusText(value?: string | null) {
  const normalized = String(value || "").trim()
  if (!normalized) return "--"
  return normalized.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim()
}

function interactionModeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "chat") return "接待回复"
  if (normalized === "continuation") return "并入任务"
  if (normalized === "task") return "转任务"
  return displayStatusText(value)
}

function taskSignalLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "dispatch_task") return "转任务"
  if (normalized === "handoff_human") return "转任务"
  return displayStatusText(value)
}

function securityLayerLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "prompt_injection") return "Prompt 注入"
  if (normalized === "hermes_result_guard") return "Hermes 输出监听"
  if (normalized === "xss") return "XSS"
  if (normalized === "dos") return "DOS / 高频"
  if (normalized === "rate_limit") return "频率限制"
  if (normalized === "keyword_blocklist") return "关键词阻断"
  if (normalized === "auth_rbac") return "权限范围"
  return displayStatusText(value)
}

function traceSourceLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "message_ingestion") return "平台接待入口"
  if (normalized === "security_gateway") return "安全监听层"
  if (normalized === "dingtalk_stream") return "钉钉渠道接入"
  if (normalized === "channel_outbound") return "渠道输出适配"
  if (normalized === "hermes_protocol_writeback") return "Hermes 协议回写"
  return displayStatusText(value)
}

function traceTypeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "info") return "信息"
  if (normalized === "success") return "成功"
  if (normalized === "warning") return "告警"
  if (normalized === "error") return "异常"
  return displayStatusText(value)
}

function SessionInfoTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-md bg-background/70 p-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 min-w-0 text-sm text-foreground">{children}</div>
    </div>
  )
}

function KnowledgeHitsPreviewBlock({
  title = "知识命中",
  count,
  tenantHits,
  sharedHits,
  items,
}: {
  title?: string
  count: number
  tenantHits: number
  sharedHits: number
  items: IntakeKnowledgeHitPreview[]
}) {
  if (count <= 0) {
    return null
  }

  return (
    <div className="mt-2 rounded-md bg-background/60 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-[11px] text-muted-foreground">{title}</div>
        <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
          共 {count} 条
        </Badge>
        <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
          租户 {tenantHits}
        </Badge>
        <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
          通用 {sharedHits}
        </Badge>
      </div>
      {items.length > 0 ? (
        <div className="mt-2 space-y-2">
          {items.map((item, index) => (
            <div key={`${item.title}-${index}`} className="rounded-md border border-border/70 bg-background/70 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-medium text-foreground">{item.title}</div>
                {item.scope ? (
                  <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                    {item.scope === "tenant" ? "租户" : item.scope === "shared" ? "通用" : item.scope}
                  </Badge>
                ) : null}
              </div>
              {item.source ? <div className="mt-1 break-all text-xs text-muted-foreground">{item.source}</div> : null}
              {item.summary ? (
                <div className="mt-1 whitespace-pre-wrap break-words text-sm text-foreground">{item.summary}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function PlatformContextBlock({
  activeTask,
  knowledgeCount,
  knowledgeTenantHits,
  knowledgeSharedHits,
  knowledgeItems,
}: {
  activeTask?: IntakeActiveTaskPreview | null
  knowledgeCount: number
  knowledgeTenantHits: number
  knowledgeSharedHits: number
  knowledgeItems: IntakeKnowledgeHitPreview[]
}) {
  if (!activeTask && knowledgeCount <= 0) {
    return null
  }

  return (
    <div className="mt-2 rounded-md bg-background/60 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">平台注入上下文</div>

      {activeTask ? (
        <div className="mt-2 rounded-md border border-border/70 bg-background/70 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-medium text-foreground">{activeTask.title || activeTask.taskId}</div>
            {activeTask.status ? (
              <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                {displayStatusText(activeTask.status)}
              </Badge>
            ) : null}
          </div>
          <div className="mt-1 break-all text-xs text-muted-foreground">活跃任务：{activeTask.taskId}</div>
          {activeTask.summary ? (
            <div className="mt-1 whitespace-pre-wrap break-words text-sm text-foreground">{activeTask.summary}</div>
          ) : null}
          {activeTask.updatedAt ? (
            <div className="mt-2 text-xs text-muted-foreground">最近同步：{formatTimestamp(activeTask.updatedAt)}</div>
          ) : null}
        </div>
      ) : null}

      <KnowledgeHitsPreviewBlock
        title="知识注入"
        count={knowledgeCount}
        tenantHits={knowledgeTenantHits}
        sharedHits={knowledgeSharedHits}
        items={knowledgeItems}
      />
    </div>
  )
}

function extractKnowledgeHitsPreview(metadata?: Record<string, unknown> | null) {
  const rawItems = metadata?.knowledge_hits_preview ?? metadata?.knowledgeHitsPreview
  if (!Array.isArray(rawItems)) {
    return []
  }
  return rawItems
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => ({
      title: String(item.title || "").trim(),
      source: String(item.source || "").trim() || null,
      summary: String(item.summary || "").trim() || null,
      scope: String(item.scope || "").trim() || null,
      score:
        typeof item.score === "number"
          ? item.score
          : typeof item.score === "string" && item.score.trim()
            ? Number(item.score)
            : null,
    }))
    .filter((item) => item.title)
}

function extractActiveTaskPreview(metadata?: Record<string, unknown> | null): IntakeActiveTaskPreview | null {
  if (!metadata) {
    return null
  }

  const rawContext = metadata.active_task_context ?? metadata.activeTaskContext
  if (typeof rawContext === "object" && rawContext !== null) {
    const taskId = String((rawContext as Record<string, unknown>).task_id || (rawContext as Record<string, unknown>).taskId || "").trim()
    if (taskId) {
      return {
        taskId,
        title: String((rawContext as Record<string, unknown>).title || "").trim() || null,
        status: String((rawContext as Record<string, unknown>).status || "").trim() || null,
        summary: String((rawContext as Record<string, unknown>).summary || "").trim() || null,
        updatedAt:
          String((rawContext as Record<string, unknown>).updated_at || (rawContext as Record<string, unknown>).updatedAt || "").trim() ||
          null,
      }
    }
  }

  const taskId = String(metadata.active_task_id || metadata.activeTaskId || "").trim()
  return taskId ? { taskId } : null
}

function StatCard({
  title,
  value,
  hint,
  toneClass,
  icon,
}: {
  title: string
  value: number
  hint: string
  toneClass: string
  icon: ReactNode
}) {
  return (
    <Card className="bg-card">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs text-muted-foreground">{title}</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
            <div className="mt-2 text-xs text-muted-foreground">{hint}</div>
          </div>
          <div className={`rounded-xl p-2 ${toneClass}`}>{icon}</div>
        </div>
      </CardContent>
    </Card>
  )
}

function ReceptionSessionList({
  items,
  loading,
}: {
  items: IntakeReceptionSession[]
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={`intake-session-skeleton-${index}`} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
        当前没有 Hermes 服务中的客户会话。
      </div>
    )
  }

  return (
    <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
      {items.map((item) => {
        const meta = sessionStateMeta(item.state)
        const inputMeta = inputSecurityMeta(item.lastInputSecurityStatus)
        const outputMeta = outputSecurityMeta(item.lastOutputSecurityStatus)
        const tenantLabel = item.tenantName || item.tenantId || "未绑定租户"
        const customerLabel = personLabel(item)
        const sessionContextBadges: Array<{ label: string; value: string; tone: string }> = []

        if (hasDisplayValue(item.lastInteractionMode)) {
          sessionContextBadges.push({
            label: "交互模式",
            value: interactionModeLabel(item.lastInteractionMode),
            tone: "bg-secondary text-secondary-foreground",
          })
        }
        if (hasDisplayValue(item.protocolMode)) {
          sessionContextBadges.push({
            label: "协议",
            value: displayStatusText(item.protocolMode),
            tone: "bg-secondary text-secondary-foreground",
          })
        }
        if (hasDisplayValue(item.lastTaskSignal)) {
          sessionContextBadges.push({
            label: "分流动作",
            value: taskSignalLabel(item.lastTaskSignal),
            tone: "bg-secondary text-secondary-foreground",
          })
        }

        return (
          <div key={item.sessionKey} className="rounded-lg border border-border bg-secondary/20 px-3 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="break-words text-sm font-medium text-foreground">{customerLabel}</div>
                <div className="mt-1 break-all text-xs text-muted-foreground">
                  会话：{item.sessionId || item.sessionKey}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap justify-end gap-2">
                <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                  {channelLabel(item.channel)}
                </Badge>
                <Badge variant="secondary" className={meta.tone}>
                  {meta.label}
                </Badge>
              </div>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <SessionInfoTile label="租户">
                <div className="break-words font-medium text-foreground">{tenantLabel}</div>
              </SessionInfoTile>
              <SessionInfoTile label="客户">
                <div className="break-words font-medium text-foreground">{customerLabel}</div>
              </SessionInfoTile>
              <SessionInfoTile label="当前阶段">
                <div className="break-words font-medium text-foreground">
                  {displayText(item.currentStage || meta.label)}
                </div>
              </SessionInfoTile>
              <SessionInfoTile label="输入安全">
                <Badge
                  variant="secondary"
                  className={`${inputMeta.tone} max-w-full whitespace-normal break-all px-2 py-1 leading-4`}
                >
                  {inputMeta.label}
                </Badge>
              </SessionInfoTile>
              <SessionInfoTile label="输出安全">
                <Badge
                  variant="secondary"
                  className={`${outputMeta.tone} max-w-full whitespace-normal break-all px-2 py-1 leading-4`}
                >
                  {outputMeta.label}
                </Badge>
              </SessionInfoTile>
            </div>

            {sessionContextBadges.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {sessionContextBadges.map((badge) => (
                  <Badge
                    key={`${item.sessionKey}-${badge.label}`}
                    variant="secondary"
                    className={`${badge.tone} max-w-full whitespace-normal break-all px-2 py-1 text-[11px] leading-4`}
                  >
                    {badge.label}: {badge.value}
                  </Badge>
                ))}
              </div>
            ) : null}

            <div className="mt-3 rounded-md bg-background/60 px-3 py-2">
              <div className="text-[11px] text-muted-foreground">最近消息</div>
              <div className="mt-1 max-h-20 overflow-y-auto whitespace-pre-wrap break-words text-sm text-foreground">
                {displayText(item.latestMessage)}
              </div>
            </div>

            {hasDisplayValue(item.replyPreview) ? (
              <div className="mt-2 rounded-md bg-background/60 px-3 py-2">
                <div className="text-[11px] text-muted-foreground">回复摘要</div>
                <div className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-words text-sm text-foreground">
                  {displayText(item.replyPreview)}
                </div>
              </div>
            ) : null}

            <PlatformContextBlock
              activeTask={item.activeTask}
              knowledgeCount={item.knowledgeHitCount}
              knowledgeTenantHits={item.knowledgeTenantHits}
              knowledgeSharedHits={item.knowledgeSharedHits}
              knowledgeItems={item.knowledgeHitsPreview}
            />

            {hasDisplayValue(item.outputBlockReason) ? (
              <div className="mt-2 rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-[11px] text-destructive">阻断原因</div>
                  {hasDisplayValue(item.outputBlockLayer) ? (
                    <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                      {securityLayerLabel(item.outputBlockLayer)}
                    </Badge>
                  ) : null}
                  {hasDisplayValue(item.outputBlockRuleName) ? (
                    <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                      {displayText(item.outputBlockRuleName)}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-1 max-h-20 overflow-y-auto whitespace-pre-wrap break-words text-sm text-foreground">
                  {displayText(item.outputBlockReason)}
                </div>
              </div>
            ) : null}

            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="break-all">服务识别码：{item.serviceCode || "--"}</span>
              <span className="break-all">更新时间：{formatTimestamp(item.updatedAt)}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AdmissionEventFeed({
  items,
  loading,
  selectedTraceId,
  onSelect,
}: {
  items: IntakeAdmissionEvent[]
  loading: boolean
  selectedTraceId: string | null
  onSelect: (event: IntakeAdmissionEvent) => void
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={`intake-event-skeleton-${index}`} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
        暂无准入事件。
      </div>
    )
  }

  return (
    <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
      {items.map((item) => {
        const meta = admissionStatusMeta(item.status)
        const active = Boolean(selectedTraceId) && item.traceId === selectedTraceId
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item)}
            className={`w-full rounded-lg border px-3 py-3 text-left transition ${
              active
                ? "border-primary bg-primary/5"
                : "border-border bg-secondary/20 hover:border-primary/40 hover:bg-secondary/40"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{item.message}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {item.agent} · {formatTimestamp(item.timestamp)}
                </div>
              </div>
              <Badge variant="secondary" className={meta.tone}>
                {meta.label}
              </Badge>
            </div>
            <div className="mt-3 text-sm text-foreground">
              {item.tenantName || item.tenantId || "未绑定租户"} · {personLabel(item)} · {channelLabel(item.channel)}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              服务识别码：{item.serviceCode || "--"}
              {item.missingFields.length > 0 ? ` · 缺少字段：${item.missingFields.join(" / ")}` : ""}
              {item.reason ? ` · 原因：${item.reason}` : ""}
              {item.traceId ? ` · Trace：${item.traceId}` : ""}
            </div>
          </button>
        )
      })}
    </div>
  )
}

function SecurityEventFeed({
  items,
  loading,
  selectedTraceId,
  onSelect,
}: {
  items: IntakeSecurityEvent[]
  loading: boolean
  selectedTraceId: string | null
  onSelect: (traceId: string | null) => void
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={`intake-security-event-skeleton-${index}`} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
        暂无安全阻断事件。
      </div>
    )
  }

  return (
    <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
      {items.map((item) => {
        const meta = admissionStatusMeta(item.status)
        const active = Boolean(selectedTraceId) && item.traceId === selectedTraceId
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.traceId || null)}
            className={`w-full rounded-lg border px-3 py-3 text-left transition ${
              active
                ? "border-primary bg-primary/5"
                : "border-border bg-secondary/20 hover:border-primary/40 hover:bg-secondary/40"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{item.message}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {item.agent} · {formatTimestamp(item.timestamp)}
                </div>
              </div>
              <Badge variant="secondary" className={meta.tone}>
                {meta.label}
              </Badge>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                {item.blockStage || "安全监听"}
              </Badge>
              {item.securityLayer ? (
                <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                  {securityLayerLabel(item.securityLayer)}
                </Badge>
              ) : null}
              {item.securityRuleName ? (
                <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                  {displayText(item.securityRuleName)}
                </Badge>
              ) : null}
              <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                {channelLabel(item.channel)}
              </Badge>
            </div>
            <div className="mt-3 text-sm text-foreground">
              {item.tenantName || item.tenantId || "未绑定租户"} · {personLabel(item)} 
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              服务识别码：{item.serviceCode || "--"}
              {item.reason ? ` · 原因：${item.reason}` : ""}
              {item.traceId ? ` · Trace：${item.traceId}` : ""}
            </div>
          </button>
        )
      })}
    </div>
  )
}

function HermesEventFeed({
  items,
  loading,
  selectedTraceId,
  onSelect,
}: {
  items: IntakeHermesEvent[]
  loading: boolean
  selectedTraceId: string | null
  onSelect: (traceId: string | null) => void
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={`intake-hermes-event-skeleton-${index}`} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-secondary/20 p-4 text-sm text-muted-foreground">
        暂无 Hermes 回传事件。
      </div>
    )
  }

  return (
    <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
      {items.map((item) => {
        const stateMeta = sessionStateMeta(item.state)
        const outputMeta = outputSecurityMeta(item.outputSecurityStatus)
        const active = Boolean(selectedTraceId) && item.traceId === selectedTraceId
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.traceId || null)}
            className={`w-full rounded-lg border px-3 py-3 text-left transition ${
              active
                ? "border-primary bg-primary/5"
                : "border-border bg-secondary/20 hover:border-primary/40 hover:bg-secondary/40"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{item.message}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {item.agent} · {formatTimestamp(item.timestamp)}
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Badge variant="secondary" className={stateMeta.tone}>
                  {stateMeta.label}
                </Badge>
                <Badge variant="secondary" className={outputMeta.tone}>
                  {outputMeta.label}
                </Badge>
              </div>
            </div>
            <div className="mt-3 text-sm text-foreground">
              {item.tenantName || item.tenantId || "未绑定租户"} · {personLabel(item)} ·{" "}
              {item.currentStage || "--"}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                {channelLabel(item.channel)}
              </Badge>
              {item.interactionMode ? (
                <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                  {interactionModeLabel(item.interactionMode)}
                </Badge>
              ) : null}
              {item.taskSignal ? (
                <Badge variant="secondary" className="bg-secondary text-secondary-foreground">
                  {taskSignalLabel(item.taskSignal)}
                </Badge>
              ) : null}
              {item.outputBlockLayer ? (
                <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                  {securityLayerLabel(item.outputBlockLayer)}
                </Badge>
              ) : null}
              {item.outputBlockRuleName ? (
                <Badge variant="secondary" className="bg-destructive/10 text-destructive">
                  {displayText(item.outputBlockRuleName)}
                </Badge>
              ) : null}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              {item.activeTask?.taskId
                ? `活跃任务：${item.activeTask.taskId}`
                : item.activeTaskId
                  ? `活跃任务：${item.activeTaskId}`
                  : `服务识别码：${item.serviceCode || "--"}`}
              {item.replyPreview ? ` · 回复摘要：${item.replyPreview}` : ""}
              {item.reason ? ` · 原因：${item.reason}` : ""}
            </div>
            <PlatformContextBlock
              activeTask={item.activeTask}
              knowledgeCount={item.knowledgeHitCount}
              knowledgeTenantHits={item.knowledgeTenantHits}
              knowledgeSharedHits={item.knowledgeSharedHits}
              knowledgeItems={item.knowledgeHitsPreview}
            />
          </button>
        )
      })}
    </div>
  )
}

function TraceDetailSheet({
  traceId,
  open,
  onOpenChange,
}: {
  traceId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const traceQuery = useQuery({
    queryKey: queryKeys.intake.trace(traceId),
    queryFn: () => apiRequest<IntakeTraceDetailResponse>(`/api/intake/traces/${encodeURIComponent(traceId ?? "")}`),
    enabled: open && Boolean(traceId),
  })

  const detail = traceQuery.data

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>接入 Trace 详情</SheetTitle>
          <SheetDescription>查看当前准入事件对应的原始执行链路、结构化 metadata 与 trace 轨迹。</SheetDescription>
        </SheetHeader>
        <div className="space-y-4 px-4 pb-6">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg bg-secondary/30 p-3">
              <div className="text-xs text-muted-foreground">Trace</div>
              <div className="mt-1 break-all font-medium text-foreground">{detail?.traceId || traceId || "--"}</div>
            </div>
            <div className="rounded-lg bg-secondary/30 p-3">
              <div className="text-xs text-muted-foreground">客户</div>
              <div className="mt-1 font-medium text-foreground">{personLabel(detail ?? {})}</div>
            </div>
            <div className="rounded-lg bg-secondary/30 p-3">
              <div className="text-xs text-muted-foreground">租户</div>
              <div className="mt-1 font-medium text-foreground">{detail?.tenantName || detail?.tenantId || "--"}</div>
            </div>
            <div className="rounded-lg bg-secondary/30 p-3">
              <div className="text-xs text-muted-foreground">渠道</div>
              <div className="mt-1 font-medium text-foreground">{channelLabel(detail?.channel)}</div>
            </div>
            <div className="rounded-lg bg-secondary/30 p-3">
              <div className="text-xs text-muted-foreground">服务识别码</div>
              <div className="mt-1 font-medium text-foreground">{detail?.serviceCode || "--"}</div>
            </div>
            <div className="rounded-lg bg-secondary/30 p-3">
              <div className="text-xs text-muted-foreground">会话</div>
              <div className="mt-1 break-all font-medium text-foreground">{detail?.sessionId || "--"}</div>
            </div>
          </div>

          {traceQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={`trace-detail-skeleton-${index}`} className="h-24 w-full" />
              ))}
            </div>
          ) : traceQuery.isError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              Trace 加载失败：{traceQuery.error instanceof Error ? traceQuery.error.message : "未知错误"}
            </div>
          ) : (
            <div className="space-y-3">
              {(detail?.items ?? []).map((item) => {
                const previewItems = extractKnowledgeHitsPreview(item.metadata)
                const activeTask = extractActiveTaskPreview(item.metadata)
                const totalRaw = item.metadata?.knowledge_hit_count ?? item.metadata?.knowledgeHitCount
                const tenantRaw = item.metadata?.knowledge_tenant_hits ?? item.metadata?.knowledgeTenantHits
                const sharedRaw = item.metadata?.knowledge_shared_hits ?? item.metadata?.knowledgeSharedHits
                const total =
                  typeof totalRaw === "number"
                    ? totalRaw
                    : typeof totalRaw === "string" && totalRaw.trim()
                      ? Number(totalRaw)
                      : previewItems.length
                const tenantHits =
                  typeof tenantRaw === "number"
                    ? tenantRaw
                    : typeof tenantRaw === "string" && tenantRaw.trim()
                      ? Number(tenantRaw)
                      : 0
                const sharedHits =
                  typeof sharedRaw === "number"
                    ? sharedRaw
                    : typeof sharedRaw === "string" && sharedRaw.trim()
                      ? Number(sharedRaw)
                      : 0

                return (
                  <div key={item.id} className="rounded-lg border border-border bg-secondary/20 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">{item.agent}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {formatTimestamp(item.timestamp)} · {traceSourceLabel(item.source)} · {traceTypeLabel(item.type)}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 whitespace-pre-wrap text-sm text-foreground">{item.message}</div>
                  <PlatformContextBlock
                    activeTask={activeTask}
                    knowledgeCount={Number.isFinite(total) ? total : previewItems.length}
                    knowledgeTenantHits={Number.isFinite(tenantHits) ? tenantHits : 0}
                    knowledgeSharedHits={Number.isFinite(sharedHits) ? sharedHits : 0}
                    knowledgeItems={previewItems}
                  />
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <div className="rounded-lg bg-background/70 p-3">
                      <div className="text-xs text-muted-foreground">Task / Run</div>
                      <div className="mt-1 text-xs leading-5 text-foreground">
                        Task：{item.taskId || "--"}
                        <br />
                        Run：{item.workflowRunId || "--"}
                      </div>
                    </div>
                    <div className="rounded-lg bg-background/70 p-3">
                      <div className="text-xs text-muted-foreground">Metadata</div>
                      <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-foreground">
                        {item.metadata ? JSON.stringify(item.metadata, null, 2) : "无结构化 metadata"}
                      </pre>
                    </div>
                  </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default function IntakeLayerPage() {
  const tenantsQuery = useManagedUserTenants()
  const [selectedTenantId, setSelectedTenantId] = useState("all")
  const [selectedChannel, setSelectedChannel] = useState("all")
  const [liveOverview, setLiveOverview] = useState<IntakeConsoleOverviewResponse | null>(null)
  const [liveState, setLiveState] = useState<LiveConnectionState>("connecting")
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)

  const tenantIdParam = selectedTenantId === "all" ? undefined : selectedTenantId
  const channelParam = selectedChannel === "all" ? undefined : selectedChannel

  const overviewQuery = useQuery({
    queryKey: queryKeys.intake.filteredOverview({ tenantId: tenantIdParam, channel: channelParam }),
    queryFn: () => {
      const params = new URLSearchParams()
      if (tenantIdParam) params.set("tenantId", tenantIdParam)
      if (channelParam) params.set("channel", channelParam)
      const queryString = params.toString()
      return apiRequest<IntakeConsoleOverviewResponse>(
        queryString ? `/api/intake/overview?${queryString}` : "/api/intake/overview",
      )
    },
  })

  useEffect(() => {
    setLiveOverview(null)
    setSelectedTraceId(null)
  }, [selectedTenantId, selectedChannel])

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const wsUrl = buildAuthenticatedWebSocketUrl("/api/intake/realtime", WS_BASE_URL)
      if (!wsUrl) {
        setLiveState("error")
        return
      }

      const url = new URL(wsUrl)
      if (tenantIdParam) {
        url.searchParams.set("tenantId", tenantIdParam)
      }
      if (channelParam) {
        url.searchParams.set("channel", channelParam)
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
          const payload = JSON.parse(event.data) as IntakeConsoleOverviewResponse
          setLiveOverview(payload)
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
  }, [tenantIdParam, channelParam])

  const overview = liveOverview ?? overviewQuery.data
  const summary = overview?.summary
  const receptionSessions = overview?.receptionSessions ?? []
  const admissionEvents = overview?.admissionEvents ?? []
  const securityEvents = overview?.securityEvents ?? []
  const hermesEvents = overview?.hermesEvents ?? []
  const liveMeta = liveConnectionMeta(liveState)
  const tenantOptions = useMemo(
    () => [
      { id: "all", name: "全部租户" },
      ...((tenantsQuery.data?.items ?? []).map((item) => ({
        id: item.id,
        name: item.name,
      })) || []),
    ],
    [tenantsQuery.data?.items],
  )

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">接入层运营台</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              直接观察客户准入结果、Hermes 当前服务对象，以及平台实际注入给 Hermes 的上下文。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className={liveMeta.tone}>
              <span className="mr-1">{liveMeta.icon}</span>
              {liveMeta.label}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void overviewQuery.refetch()}
              disabled={overviewQuery.isFetching}
            >
              <RefreshCw className="mr-2 size-4" />
              刷新状态
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/settings/admission-template">客户准入配置</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/settings/intake-security">安全监听配置</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/settings/channel-integration">渠道接入配置</Link>
            </Button>
          </div>
        </div>

        <Card className="bg-card">
          <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-col gap-3 md:flex-row md:items-center">
              <div className="flex items-center gap-2">
                <div className="w-20 text-sm text-muted-foreground">租户筛选</div>
                <Select value={selectedTenantId} onValueChange={setSelectedTenantId}>
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="选择租户" />
                  </SelectTrigger>
                  <SelectContent>
                    {tenantOptions.map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-20 text-sm text-muted-foreground">渠道筛选</div>
                <Select value={selectedChannel} onValueChange={setSelectedChannel}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="选择渠道" />
                  </SelectTrigger>
                  <SelectContent>
                    {CHANNEL_OPTIONS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="text-sm text-muted-foreground">
              当前范围：{tenantOptions.find((item) => item.id === selectedTenantId)?.name ?? "全部租户"} ·{" "}
              {CHANNEL_OPTIONS.find((item) => item.value === selectedChannel)?.label ?? "全部渠道"}
            </div>
          </CardContent>
        </Card>
      </div>

      {overviewQuery.isError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          接入层数据加载失败：{overviewQuery.error instanceof Error ? overviewQuery.error.message : "未知错误"}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="通过"
          value={summary?.passed ?? 0}
          hint="已通过准入并进入接待"
          toneClass="bg-success/10 text-success"
          icon={<CheckCircle2 className="size-4" />}
        />
        <StatCard
          title="待补充"
          value={summary?.pendingVerification ?? 0}
          hint="客户信息还未补齐"
          toneClass="bg-warning/10 text-warning-foreground"
          icon={<ClipboardCheck className="size-4" />}
        />
        <StatCard
          title="拒绝"
          value={summary?.rejected ?? 0}
          hint="准入未通过或租户未命中"
          toneClass="bg-destructive/10 text-destructive"
          icon={<XCircle className="size-4" />}
        />
        <StatCard
          title="安全阻断"
          value={summary?.securityBlocked ?? 0}
          hint="消息在进入接待前被拦截"
          toneClass="bg-destructive/10 text-destructive"
          icon={<ShieldAlert className="size-4" />}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card className="bg-card">
          <CardHeader>
            <CardTitle className="text-base">实时准入事件流</CardTitle>
            <CardDescription>展示通过、待补充、拒绝、安全阻断四类准入结果。点击事件可查看原始 trace。</CardDescription>
          </CardHeader>
          <CardContent>
            <AdmissionEventFeed
              items={admissionEvents}
              loading={overviewQuery.isLoading && !overview}
              selectedTraceId={selectedTraceId}
              onSelect={(event) => setSelectedTraceId(event.traceId || null)}
            />
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bot className="size-4" />
              Hermes 当前服务对象
            </CardTitle>
            <CardDescription>
              活跃会话 {overview?.activeSessionCount ?? 0} 个，展示当前或最近一批接待中的租户、客户与平台注入上下文。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ReceptionSessionList items={receptionSessions} loading={overviewQuery.isLoading && !overview} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="bg-card">
          <CardHeader>
            <CardTitle className="text-base">安全阻断事件流</CardTitle>
            <CardDescription>展示渠道输入拦截与 Hermes 输出阻断，直接定位当前风险发生在哪一段。</CardDescription>
          </CardHeader>
          <CardContent>
            <SecurityEventFeed
              items={securityEvents}
              loading={overviewQuery.isLoading && !overview}
              selectedTraceId={selectedTraceId}
              onSelect={setSelectedTraceId}
            />
          </CardContent>
        </Card>

        <Card className="bg-card">
          <CardHeader>
            <CardTitle className="text-base">Hermes 回传结果流</CardTitle>
            <CardDescription>展示 Hermes 最近一批接待回传、分流动作与输出监听结果。</CardDescription>
          </CardHeader>
          <CardContent>
            <HermesEventFeed
              items={hermesEvents}
              loading={overviewQuery.isLoading && !overview}
              selectedTraceId={selectedTraceId}
              onSelect={setSelectedTraceId}
            />
          </CardContent>
        </Card>
      </div>

      <Card className="bg-card">
        <CardHeader>
          <CardTitle className="text-base">运营说明</CardTitle>
          <CardDescription>这一页展示的是接待链路实时态，不是租户画像总表。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-lg border border-border bg-secondary/20 px-3 py-3 text-sm text-muted-foreground">
            准入事件只统计接入层真实执行结果，来源于安全监听与客户准入节点。
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 px-3 py-3 text-sm text-muted-foreground">
            Hermes 服务对象按会话维度聚合，自动展示租户、客户、渠道与最近状态。
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 px-3 py-3 text-sm text-muted-foreground">
            安全阻断流会区分“渠道输入”与“Hermes 输出”，方便判断风险发生在接待前还是回传前。
          </div>
          <div className="rounded-lg border border-border bg-secondary/20 px-3 py-3 text-sm text-muted-foreground">
            最近更新时间：{formatTimestamp(overview?.updatedAt)}
            {overviewQuery.isFetching ? " · 刷新中" : ""}
          </div>
        </CardContent>
      </Card>

      <TraceDetailSheet
        traceId={selectedTraceId}
        open={Boolean(selectedTraceId)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedTraceId(null)
          }
        }}
      />
    </div>
  )
}
