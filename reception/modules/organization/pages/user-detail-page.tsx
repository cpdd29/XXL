"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams, useSearchParams } from "next/navigation"
import { Badge } from "@/shared/ui/badge"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/shared/ui/breadcrumb"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/shared/ui/empty"
import { Input } from "@/shared/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Separator } from "@/shared/ui/separator"
import { Skeleton } from "@/shared/ui/skeleton"
import { Textarea } from "@/shared/ui/textarea"
import { useAuth } from "@/modules/auth/hooks/use-auth"
import { toast } from "@/shared/hooks/use-toast"
import { useUpdateUserProfile, useUserActivity, useUserProfile } from "@/modules/organization/hooks/use-users"
import type {
  UpdateUserProfileRequest,
  UserActivityItem,
  UserPlatformAccount,
  UserPreferredLanguage,
  UserProfile,
} from "@/shared/types"
import {
  ArrowLeft,
  BadgeCheck,
  Building2,
  Clock3,
  Fingerprint,
  Globe2,
  Languages,
  MessageSquareText,
  Save,
  Tags,
  UserCircle2,
  Users,
  X,
  type LucideIcon,
} from "lucide-react"

const TENANT_STORAGE_KEY = "user-portraits:selected-tenant"

const activityTypeConfig = {
  info: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/20 text-warning-foreground",
  error: "bg-destructive/15 text-destructive",
} as const

function activityTypeClassName(type: string) {
  return activityTypeConfig[type as keyof typeof activityTypeConfig] ?? "bg-muted text-muted-foreground"
}

const platformLabelMap: Record<string, string> = {
  telegram: "Telegram",
  wecom: "WeCom",
  feishu: "Feishu",
  dingtalk: "DingTalk",
  console: "Console",
}

function platformLabel(platform: string) {
  return platformLabelMap[platform] ?? platform
}

function languageLabel(language: UserPreferredLanguage) {
  return language === "zh" ? "中文" : "English"
}

function tenantStatusLabel(status: string) {
  if (status === "active") {
    return "启用中"
  }
  if (status === "inactive") {
    return "未启用"
  }
  if (status === "archived") {
    return "已归档"
  }
  return status || "未知"
}

function padDate(value: number) {
  return String(value).padStart(2, "0")
}

function formatDateTime(value: string | null | undefined) {
  const normalized = String(value || "").trim()
  if (!normalized) {
    return "暂无记录"
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return `${normalized} 00:00:00`
  }

  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`
  }

  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(normalized)) {
    return normalized
  }

  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return normalized
  }

  return [
    parsed.getFullYear(),
    padDate(parsed.getMonth() + 1),
    padDate(parsed.getDate()),
  ].join("-") + ` ${padDate(parsed.getHours())}:${padDate(parsed.getMinutes())}:${padDate(parsed.getSeconds())}`
}

function normalizeTags(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[\n,，]/)
        .map((tag) => tag.trim())
        .filter(Boolean),
    ),
  )
}

function buildPortraitDraft(profile: UserProfile) {
  return {
    tagsInput: profile.tags.join(", "),
    notes: profile.notes ?? "",
    preferredLanguage: profile.preferredLanguage,
  }
}

function areTagsEqual(left: string[], right: string[]) {
  if (left.length !== right.length) {
    return false
  }

  return left.every((value, index) => value === right[index])
}

function LoadingView() {
  return (
    <div className="space-y-6 p-6">
      <Skeleton className="h-5 w-64" />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Skeleton className="h-[680px] rounded-xl" />
        <Skeleton className="h-[680px] rounded-xl" />
      </div>
    </div>
  )
}

function ActivityItem({ item }: { item: UserActivityItem }) {
  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className={activityTypeClassName(item.type)}>
            {item.type}
          </Badge>
          <span className="text-sm font-medium text-foreground">{item.title}</span>
        </div>
        <span className="text-xs text-muted-foreground">{formatDateTime(item.timestamp)}</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</p>
      <div className="mt-3 text-xs uppercase tracking-[0.12em] text-muted-foreground/80">{item.source}</div>
    </div>
  )
}

function PlatformAccountItem({ account }: { account: UserPlatformAccount }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-secondary/20 px-4 py-3">
      <div>
        <div className="text-sm font-medium text-foreground">{platformLabel(account.platform)}</div>
        <div className="mt-1 text-xs uppercase tracking-[0.12em] text-muted-foreground">平台账号</div>
      </div>
      <code className="rounded-md bg-background/80 px-2 py-1 text-xs text-foreground">{account.accountId}</code>
    </div>
  )
}

function DetailItem({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string
  icon: LucideIcon
}) {
  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.12em] text-muted-foreground">
        <Icon className="size-4" />
        {label}
      </div>
      <div className="mt-3 text-sm font-medium text-foreground">{value}</div>
    </div>
  )
}

export default function UserDetailPage() {
  const { hasPermission } = useAuth()
  const params = useParams<{ userId: string }>()
  const searchParams = useSearchParams()
  const userId = params.userId
  const { data: profile, isLoading, error } = useUserProfile(userId)
  const { data: activityData, isLoading: activityLoading } = useUserActivity(userId)
  const updateProfileMutation = useUpdateUserProfile()
  const [draft, setDraft] = useState<{ tagsInput: string; notes: string; preferredLanguage: UserPreferredLanguage }>({
    tagsInput: "",
    notes: "",
    preferredLanguage: "zh",
  })
  const [tenantContextId, setTenantContextId] = useState("")

  useEffect(() => {
    if (profile) {
      setDraft(buildPortraitDraft(profile))
    }
  }, [profile])

  useEffect(() => {
    const tenantFromQuery = searchParams.get("tenant") ?? ""
    if (tenantFromQuery) {
      setTenantContextId(tenantFromQuery)
      window.localStorage.setItem(TENANT_STORAGE_KEY, tenantFromQuery)
      return
    }

    const storedTenant = window.localStorage.getItem(TENANT_STORAGE_KEY)
    if (storedTenant) {
      setTenantContextId(storedTenant)
    }
  }, [searchParams])

  const canEditProfile = hasPermission("users:profile:write")

  if (isLoading) {
    return <LoadingView />
  }

  if (error || !profile) {
    return (
      <div className="p-6">
        <Card className="bg-card">
          <CardContent className="p-8">
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Users className="size-5" />
                </EmptyMedia>
                <EmptyTitle>人员画像暂不可用</EmptyTitle>
                <EmptyDescription>
                  {error instanceof Error ? error.message : "没有找到该人员画像。"}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button asChild>
                  <Link href="/users">
                    <ArrowLeft className="mr-2 size-4" />
                    返回画像列表
                  </Link>
                </Button>
              </EmptyContent>
            </Empty>
          </CardContent>
        </Card>
      </div>
    )
  }

  const activityItems = activityData?.items ?? []
  const normalizedTags = normalizeTags(draft.tagsInput)
  const isProfileSaving = updateProfileMutation.isPending
  const isProfileDirty =
    draft.preferredLanguage !== profile.preferredLanguage ||
    draft.notes.trim() !== profile.notes.trim() ||
    !areTagsEqual(normalizedTags, profile.tags)
  const backToListHref = tenantContextId
    ? `/users?tenant=${encodeURIComponent(tenantContextId)}`
    : `/users?tenant=${encodeURIComponent(profile.tenantId)}`

  const behaviorSummary = [
    {
      label: "最近活跃",
      value: formatDateTime(profile.lastActiveAt),
      icon: Clock3,
    },
    {
      label: "累计交互次数",
      value: `${profile.totalInteractions.toLocaleString()} 次`,
      icon: MessageSquareText,
    },
    {
      label: "来源渠道数",
      value: `${profile.sourceChannels.length} 个`,
      icon: Globe2,
    },
    {
      label: "平台账号数",
      value: `${profile.platformAccounts.length} 个`,
      icon: BadgeCheck,
    },
  ]

  const handleProfileSave = async () => {
    const payload: UpdateUserProfileRequest = {
      tags: normalizedTags,
      notes: draft.notes,
      preferredLanguage: draft.preferredLanguage,
    }

    try {
      const result = await updateProfileMutation.mutateAsync({ userId: profile.id, payload })
      setDraft(buildPortraitDraft(result.profile))
      toast({
        title: "人员画像已保存",
        description: `${profile.name} 的标签、备注和语言偏好已同步。`,
      })
    } catch (mutationError) {
      toast({
        title: "保存画像失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const resetProfileDraft = () => {
    setDraft(buildPortraitDraft(profile))
  }

  return (
    <div className="space-y-6 p-6">
      <div className="space-y-4">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link href={backToListHref}>人员画像</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>画像详情</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/15 text-xl font-semibold text-primary">
                {(profile.name || profile.id).slice(0, 1)}
              </div>
              <div>
                <h1 className="text-2xl font-semibold text-foreground">{profile.name}</h1>
                <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                  <Fingerprint className="size-4" />
                  画像 ID: {profile.id}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary" className="bg-primary/10 text-primary">
                {profile.tenantName}
              </Badge>
              <Badge variant="outline" className="border-border">
                租户状态：{tenantStatusLabel(profile.tenantStatus)}
              </Badge>
              <Badge variant="outline" className="border-border">
                最近活跃：{formatDateTime(profile.lastActiveAt)}
              </Badge>
              <Badge variant="outline" className="border-border">
                累计交互：{profile.totalInteractions.toLocaleString()}
              </Badge>
            </div>
          </div>

          <Button asChild variant="outline">
            <Link href={backToListHref}>
              <ArrowLeft className="mr-2 size-4" />
              返回画像列表
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">画像基础信息区</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <DetailItem label="所属租户" value={profile.tenantName} icon={Building2} />
                <DetailItem label="语言偏好" value={languageLabel(profile.preferredLanguage)} icon={Languages} />
                <DetailItem label="租户状态" value={tenantStatusLabel(profile.tenantStatus)} icon={Building2} />
                <DetailItem label="画像编号" value={profile.id} icon={UserCircle2} />
              </div>
              <div className="rounded-xl border border-border bg-secondary/20 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.12em] text-muted-foreground">
                  <MessageSquareText className="size-4" />
                  交互摘要
                </div>
                <p className="mt-3 text-sm leading-6 text-foreground">{profile.interactionSummary}</p>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">身份映射区</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <DetailItem label="映射状态" value={profile.identityMappingStatus || "unmapped"} icon={BadgeCheck} />
                <DetailItem label="映射来源" value={profile.identityMappingSource || "unknown"} icon={Building2} />
                <DetailItem
                  label="映射置信度"
                  value={`${Math.round((profile.identityMappingConfidence || 0) * 100)}%`}
                  icon={BadgeCheck}
                />
                <DetailItem
                  label="最近同步时间"
                  value={formatDateTime(profile.lastIdentitySyncAt)}
                  icon={Clock3}
                />
              </div>
              <Separator />
              <div>
                <div className="text-sm font-medium text-foreground">来源渠道</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {profile.sourceChannels.length > 0 ? (
                    profile.sourceChannels.map((channel) => (
                      <Badge key={channel} variant="outline" className="border-border">
                        {platformLabel(channel)}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">暂无来源渠道记录</span>
                  )}
                </div>
              </div>
              <Separator />
              <div>
                <div className="text-sm font-medium text-foreground">平台账号绑定</div>
                <div className="mt-3 space-y-3">
                  {profile.platformAccounts.length > 0 ? (
                    profile.platformAccounts.map((account) => (
                      <PlatformAccountItem
                        key={`${account.platform}-${account.accountId}`}
                        account={account}
                      />
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">暂无平台账号绑定记录</span>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">行为概览区</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {behaviorSummary.map((item) => (
                <DetailItem key={item.label} label={item.label} value={item.value} icon={item.icon} />
              ))}
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">活动时间线区</CardTitle>
            </CardHeader>
            <CardContent>
              {activityLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <Skeleton key={`activity-skeleton-${index}`} className="h-24 w-full rounded-xl" />
                  ))}
                </div>
              ) : activityItems.length > 0 ? (
                <div className="space-y-3">
                  {activityItems.map((item) => (
                    <ActivityItem key={item.id} item={item} />
                  ))}
                </div>
              ) : (
                <Empty className="border-border">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <Clock3 className="size-5" />
                    </EmptyMedia>
                    <EmptyTitle>暂无活动时间线</EmptyTitle>
                    <EmptyDescription>
                      当前还没有可展示的活动轨迹，后续交互和审计事件会汇聚到这里。
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit bg-card">
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base">画像编辑</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  仅维护标签、备注和语言偏好，其余来源、平台映射和活动轨迹保持只读。
                </p>
              </div>
              <Badge variant="outline" className="border-border">
                {profile.tenantName}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                <Tags className="size-4 text-primary" />
                标签
              </div>
              <Input
                value={draft.tagsInput}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, tagsInput: event.target.value }))
                }
                disabled={!canEditProfile || isProfileSaving}
                placeholder="例如：重点客户，已跟进，偏好中文"
                className="bg-secondary/30"
              />
              <div className="mt-3 flex flex-wrap gap-2">
                {normalizedTags.length > 0 ? (
                  normalizedTags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="bg-primary/10 text-primary">
                      {tag}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">暂无标签</span>
                )}
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                <Languages className="size-4 text-primary" />
                语言偏好
              </div>
              <Select
                value={draft.preferredLanguage}
                onValueChange={(value: UserPreferredLanguage) =>
                  setDraft((current) => ({ ...current, preferredLanguage: value }))
                }
                disabled={!canEditProfile || isProfileSaving}
              >
                <SelectTrigger className="w-full bg-secondary/30">
                  <SelectValue placeholder="选择语言偏好" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="zh">中文</SelectItem>
                  <SelectItem value="en">English</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <div className="mb-2 text-sm font-medium text-foreground">备注</div>
              <Textarea
                value={draft.notes}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, notes: event.target.value }))
                }
                disabled={!canEditProfile || isProfileSaving}
                placeholder="记录人员偏好、跟进结论或最接近的解决办法。"
                className="min-h-36 bg-secondary/30"
              />
            </div>

            <Separator />

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={resetProfileDraft}
                disabled={!canEditProfile || !isProfileDirty || isProfileSaving}
              >
                <X className="mr-2 size-4" />
                撤销修改
              </Button>
              <Button
                onClick={() => void handleProfileSave()}
                disabled={!canEditProfile || !isProfileDirty || isProfileSaving}
              >
                <Save className="mr-2 size-4" />
                {isProfileSaving ? "保存中..." : "保存画像"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
