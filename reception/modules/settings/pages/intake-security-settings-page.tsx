"use client"

import Link from "next/link"
import { useEffect, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  Ban,
  RefreshCw,
  Save,
  Shield,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react"
import { useAuth } from "@/modules/auth/hooks/use-auth"
import { useSecurityPolicy, useUpdateSecurityPolicy } from "@/modules/security/hooks/use-security"
import { toast } from "@/shared/hooks/use-toast"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Switch } from "@/shared/ui/switch"
import { Textarea } from "@/shared/ui/textarea"
import type { ApprovalItemLite, SecurityPolicySettings } from "@/shared/types"
import { cn } from "@/shared/utils"

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function toKeywordTextarea(value?: string[] | null) {
  return (value ?? []).join("\n")
}

function parseKeywordBlocklist(value: string) {
  const seen = new Set<string>()
  return value
    .split(/\n+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item) return false
      const lookupKey = item.toLowerCase()
      if (seen.has(lookupKey)) return false
      seen.add(lookupKey)
      return true
    })
}

type NumericPolicyKey =
  | "messageRateLimitPerMinute"
  | "messageRateLimitCooldownSeconds"
  | "messageRateLimitBanSeconds"
  | "keywordBlockThreshold"

type BooleanPolicyKey =
  | "inputMonitorEnabled"
  | "outputMonitorEnabled"
  | "dosProtectionEnabled"
  | "promptInjectionEnabled"
  | "xssEnabled"
  | "keywordBlocklistEnabled"
  | "contentRedactionEnabled"

function StatusBadge({
  enabled,
  enabledText = "已启用",
  disabledText = "已关闭",
}: {
  enabled: boolean
  enabledText?: string
  disabledText?: string
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-medium",
        enabled
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-slate-200 bg-slate-100 text-slate-600",
      )}
    >
      {enabled ? enabledText : disabledText}
    </Badge>
  )
}

function SectionCard({
  icon: Icon,
  title,
  description,
  status,
  dimmed = false,
  children,
}: {
  icon: LucideIcon
  title: string
  description: string
  status?: ReactNode
  dimmed?: boolean
  children: ReactNode
}) {
  return (
    <Card
      className={cn(
        "border-border/80 bg-background/70 transition-opacity",
        dimmed && "opacity-70",
      )}
    >
      <CardHeader className="pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2 text-base">
              <Icon className="size-4 text-muted-foreground" />
              {title}
            </CardTitle>
            <CardDescription className="mt-1">{description}</CardDescription>
          </div>
          {status}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function ToggleRow({
  title,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  title: string
  description: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card/70 px-4 py-3">
      <div className="min-w-0">
        <div className="font-medium text-foreground">{title}</div>
        <div className="text-xs text-muted-foreground">{description}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
    </div>
  )
}

function NumberField({
  label,
  value,
  min,
  max,
  disabled,
  onChange,
  hint,
}: {
  label: string
  value: number | string
  min: number
  max: number
  disabled?: boolean
  onChange: (value: string) => void
  hint?: string
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

export default function IntakeSecuritySettingsPage() {
  const { hasPermission } = useAuth()
  const policyQuery = useSecurityPolicy()
  const updatePolicyMutation = useUpdateSecurityPolicy()
  const [draft, setDraft] = useState<SecurityPolicySettings | null>(null)
  const [keywordTextarea, setKeywordTextarea] = useState("")
  const [pendingApproval, setPendingApproval] = useState<ApprovalItemLite | null>(null)
  const [saveFeedback, setSaveFeedback] = useState<string | null>(null)

  const canManage = hasPermission("settings:security-policy:write")
  const editable = canManage && Boolean(draft)
  const keywordCount = parseKeywordBlocklist(keywordTextarea).length

  useEffect(() => {
    if (!policyQuery.data?.settings) return
    setDraft(policyQuery.data.settings)
    setKeywordTextarea(toKeywordTextarea(policyQuery.data.settings.keywordBlocklist))
  }, [policyQuery.data?.settings])

  const handleNumberChange = (key: NumericPolicyKey, value: string) => {
    setDraft((current) => {
      if (!current) return current
      const normalized = Number(value)
      return {
        ...current,
        [key]: Number.isFinite(normalized) ? normalized : 0,
      }
    })
  }

  const handleToggle = (key: BooleanPolicyKey, value: boolean) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const handleSave = async () => {
    if (!draft) return
    try {
      const response = await updatePolicyMutation.mutateAsync({
        ...draft,
        keywordBlocklist: parseKeywordBlocklist(keywordTextarea),
      })
      if ("approvalRequired" in response && response.approvalRequired) {
        setPendingApproval(response.approval)
        setSaveFeedback(response.message || "本次安全策略修改已进入审批队列。")
        toast({
          title: "已提交审批",
          description: response.message,
        })
        return
      }
      if (!("settings" in response)) {
        throw new Error("安全策略保存返回异常")
      }
      setPendingApproval(null)
      setSaveFeedback("安全监听配置已直接生效。")
      setDraft(response.settings)
      setKeywordTextarea(toKeywordTextarea(response.settings.keywordBlocklist))
      toast({
        title: "安全监听配置已保存",
        description: "接入层输入监听、Hermes 输出监听与阻断策略已更新。",
      })
    } catch (error) {
      toast({
        title: "保存失败",
        description: error instanceof Error ? error.message : "安全监听配置更新失败。",
        variant: "destructive",
      })
    }
  }

  return (
    <div className="flex min-h-full flex-col gap-4 p-4 md:p-6 lg:h-full lg:overflow-hidden">
      <Card className="flex min-h-0 flex-1 flex-col bg-card">
        <CardHeader className="pb-4">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>接入层安全监听配置</CardTitle>
                  <StatusBadge enabled={canManage} enabledText="可编辑" disabledText="只读" />
                </div>
                <CardDescription>
                  平台负责渠道输入监听与 Hermes 输出监听。安全模块只监听、阻断、脱敏和审计，不直接参与回复。
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  onClick={() => policyQuery.refetch()}
                  disabled={policyQuery.isFetching}
                >
                  <RefreshCw className={cn("mr-2 size-4", policyQuery.isFetching && "animate-spin")} />
                  刷新
                </Button>
                <Button asChild variant="outline">
                  <Link href="/security">
                    <ShieldAlert className="mr-2 size-4" />
                    查看风险报告
                  </Link>
                </Button>
                <Button
                  onClick={() => void handleSave()}
                  disabled={!editable || updatePolicyMutation.isPending || policyQuery.isLoading}
                >
                  <Save className="mr-2 size-4" />
                  {updatePolicyMutation.isPending ? "保存中..." : "保存配置"}
                </Button>
              </div>
            </div>

            {saveFeedback ? (
              <div
                className={cn(
                  "rounded-xl border px-4 py-3 text-sm",
                  pendingApproval
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-emerald-200 bg-emerald-50 text-emerald-800",
                )}
              >
                <div className="font-medium">
                  {pendingApproval ? "本次修改已提交审批" : "本次修改已生效"}
                </div>
                <div className="mt-1">{saveFeedback}</div>
                {pendingApproval ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="outline" className="border-amber-200 bg-white/70 text-amber-700">
                      审批单号：{pendingApproval.id}
                    </Badge>
                    <Badge variant="outline" className="border-amber-200 bg-white/70 text-amber-700">
                      状态：{pendingApproval.status}
                    </Badge>
                    <Badge variant="outline" className="border-amber-200 bg-white/70 text-amber-700">
                      {pendingApproval.title}
                    </Badge>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-border bg-background/70 px-4 py-3">
                <div className="text-xs text-muted-foreground">监听状态</div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge enabled={Boolean(draft?.inputMonitorEnabled)} enabledText="输入开启" disabledText="输入关闭" />
                  <StatusBadge enabled={Boolean(draft?.outputMonitorEnabled)} enabledText="输出开启" disabledText="输出关闭" />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  输入监听覆盖渠道进入平台前段，输出监听覆盖 Hermes 回传平台后段。
                </div>
              </div>
              <div className="rounded-xl border border-border bg-background/70 px-4 py-3">
                <div className="text-xs text-muted-foreground">内容处置</div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge enabled={Boolean(draft?.contentRedactionEnabled)} enabledText="脱敏开启" disabledText="脱敏关闭" />
                  <StatusBadge enabled={true} enabledText="审计托管开启" />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  最近更新时间：{formatTimestamp(policyQuery.data?.updatedAt)}
                </div>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardContent className="min-h-0 flex flex-1 flex-col overflow-hidden pt-0">
          {policyQuery.error ? (
            <div className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              安全监听配置加载失败：
              {policyQuery.error instanceof Error ? policyQuery.error.message : "未知错误"}
            </div>
          ) : null}

          <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
              <SectionCard
                icon={Shield}
                title="监听开关"
                description="只配置接待链路里哪里需要实时监听。"
              >
                <div className="grid gap-3 md:grid-cols-2">
                  <ToggleRow
                    title="输入安全监听"
                    description="渠道消息进入平台后，在客户准入与 Hermes 接待前进行检测。"
                    checked={Boolean(draft?.inputMonitorEnabled)}
                    disabled={!editable}
                    onCheckedChange={(checked) => handleToggle("inputMonitorEnabled", checked)}
                  />
                  <ToggleRow
                    title="Hermes 输出监听"
                    description="Hermes 回传结果进入平台后、回写渠道前再次检测。"
                    checked={Boolean(draft?.outputMonitorEnabled)}
                    disabled={!editable}
                    onCheckedChange={(checked) => handleToggle("outputMonitorEnabled", checked)}
                  />
                </div>
              </SectionCard>

              <SectionCard
                icon={Ban}
                title="高频防护"
                description="控制刷屏、频繁触发和临时封禁。"
                dimmed={!draft?.dosProtectionEnabled}
                status={<StatusBadge enabled={Boolean(draft?.dosProtectionEnabled)} enabledText="DOS 防护开启" disabledText="DOS 防护关闭" />}
              >
                <div className="space-y-4">
                  <ToggleRow
                    title="启用 DOS / 高频攻击检测"
                    description="超频消息会进入冷却或封禁逻辑，并持续记录风险窗口。"
                    checked={Boolean(draft?.dosProtectionEnabled)}
                    disabled={!editable}
                    onCheckedChange={(checked) => handleToggle("dosProtectionEnabled", checked)}
                  />

                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <NumberField
                      label="每分钟消息上限"
                      value={draft?.messageRateLimitPerMinute ?? ""}
                      min={1}
                      max={500}
                      disabled={!editable || !draft?.dosProtectionEnabled}
                      onChange={(value) => handleNumberChange("messageRateLimitPerMinute", value)}
                    />
                    <NumberField
                      label="冷却时长（秒）"
                      value={draft?.messageRateLimitCooldownSeconds ?? ""}
                      min={1}
                      max={3600}
                      disabled={!editable || !draft?.dosProtectionEnabled}
                      onChange={(value) => handleNumberChange("messageRateLimitCooldownSeconds", value)}
                    />
                    <NumberField
                      label="封禁时长（秒）"
                      value={draft?.messageRateLimitBanSeconds ?? ""}
                      min={1}
                      max={86400}
                      disabled={!editable || !draft?.dosProtectionEnabled}
                      onChange={(value) => handleNumberChange("messageRateLimitBanSeconds", value)}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    升级封禁阈值与风险聚合窗口使用系统内置参数，当前页面不再单独配置。
                  </p>
                </div>
              </SectionCard>

              <SectionCard
                icon={ShieldAlert}
                title="风险检测"
                description="开启需要的检测规则，命中后立即阻断。"
                status={<StatusBadge enabled={Boolean(draft?.promptInjectionEnabled || draft?.xssEnabled)} enabledText="检测开启" disabledText="检测关闭" />}
              >
                <div className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <ToggleRow
                      title="Prompt 注入检测"
                      description="检测覆盖系统指令、提取隐藏提示词、越狱绕过等风险。"
                      checked={Boolean(draft?.promptInjectionEnabled)}
                      disabled={!editable}
                      onCheckedChange={(checked) => handleToggle("promptInjectionEnabled", checked)}
                    />
                    <ToggleRow
                      title="XSS 检测"
                      description="拦截脚本、事件处理器、javascript: 等注入片段。"
                      checked={Boolean(draft?.xssEnabled)}
                      disabled={!editable}
                      onCheckedChange={(checked) => handleToggle("xssEnabled", checked)}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Prompt 注入的判定阈值由系统内置，不在运营侧单独暴露。
                  </p>
                </div>
              </SectionCard>

              <SectionCard
                icon={AlertTriangle}
                title="关键词与处置"
                description="补充业务侧敏感词，并配置命中后的默认处置方式。"
                dimmed={!draft?.keywordBlocklistEnabled}
                status={<StatusBadge enabled={Boolean(draft?.keywordBlocklistEnabled)} enabledText="关键词阻断开启" disabledText="关键词阻断关闭" />}
              >
                <div className="space-y-4">
                  <ToggleRow
                    title="启用关键词阻断"
                    description="对租户场景中的敏感表达做补充拦截，不替代其他安全检测。"
                    checked={Boolean(draft?.keywordBlocklistEnabled)}
                    disabled={!editable}
                    onCheckedChange={(checked) => handleToggle("keywordBlocklistEnabled", checked)}
                  />

                  <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
                    <NumberField
                      label="命中阈值"
                      value={draft?.keywordBlockThreshold ?? ""}
                      min={1}
                      max={20}
                      disabled={!editable || !draft?.keywordBlocklistEnabled}
                      onChange={(value) => handleNumberChange("keywordBlockThreshold", value)}
                      hint="命中达到阈值后阻断当前消息。"
                    />
                    <div className="space-y-2">
                      <Label>风险关键词</Label>
                      <Textarea
                        value={keywordTextarea}
                        onChange={(event) => setKeywordTextarea(event.target.value)}
                        className="min-h-40"
                        placeholder={"例如：\n机密资料\n内部定价\n未公开方案"}
                        disabled={!editable || !draft?.keywordBlocklistEnabled}
                      />
                      <p className="text-xs text-muted-foreground">
                        每行一个关键词，当前去重后共 {keywordCount} 条。
                      </p>
                    </div>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <ToggleRow
                      title="敏感信息脱敏"
                      description="对手机号、证件号、凭证等内容进行改写后继续放行。"
                      checked={Boolean(draft?.contentRedactionEnabled)}
                      disabled={!editable}
                      onCheckedChange={(checked) => handleToggle("contentRedactionEnabled", checked)}
                    />
                    <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card/70 px-4 py-3">
                      <div className="min-w-0">
                        <div className="font-medium text-foreground">运行时审计</div>
                        <div className="text-xs text-muted-foreground">系统默认开启，记录阻断、改写、放行与风险命中轨迹。</div>
                      </div>
                      <StatusBadge enabled={true} enabledText="系统托管" />
                    </div>
                  </div>
                </div>
              </SectionCard>
            </div>

            <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
              <Card className="border-border/80 bg-background/70">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">当前生效概览</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="rounded-xl border border-border bg-card/60 px-3 py-3">
                    <div className="text-xs text-muted-foreground">监听范围</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge enabled={Boolean(draft?.inputMonitorEnabled)} enabledText="输入开启" disabledText="输入关闭" />
                      <StatusBadge enabled={Boolean(draft?.outputMonitorEnabled)} enabledText="输出开启" disabledText="输出关闭" />
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-card/60 px-3 py-3">
                    <div className="text-xs text-muted-foreground">高频防护</div>
                    <div className="mt-1 text-sm text-foreground">
                      {draft?.dosProtectionEnabled
                        ? `每分钟 ${draft?.messageRateLimitPerMinute ?? "--"} 条，冷却 ${draft?.messageRateLimitCooldownSeconds ?? "--"} 秒，封禁 ${draft?.messageRateLimitBanSeconds ?? "--"} 秒`
                        : "当前关闭"}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-card/60 px-3 py-3">
                    <div className="text-xs text-muted-foreground">风险检测</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge enabled={Boolean(draft?.promptInjectionEnabled)} enabledText="Prompt 开启" disabledText="Prompt 关闭" />
                      <StatusBadge enabled={Boolean(draft?.xssEnabled)} enabledText="XSS 开启" disabledText="XSS 关闭" />
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-card/60 px-3 py-3">
                    <div className="text-xs text-muted-foreground">关键词与处置</div>
                    <div className="mt-1 text-sm text-foreground">
                      {draft?.keywordBlocklistEnabled ? `关键词 ${keywordCount} 条，命中阈值 ${draft?.keywordBlockThreshold ?? "--"}` : "关键词阻断关闭"}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <StatusBadge enabled={Boolean(draft?.contentRedactionEnabled)} enabledText="脱敏开启" disabledText="脱敏关闭" />
                      <StatusBadge enabled={true} enabledText="审计托管" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
