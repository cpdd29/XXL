"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/hooks/use-auth"
import {
  useBlockUser,
  useUpdateUserProfile,
  useUpdateUserRole,
  useUserActivity,
  useUserProfile,
} from "@/hooks/use-users"
import { toast } from "@/hooks/use-toast"
import type {
  UpdateUserProfileRequest,
  UserActivityItem,
  UserPlatformAccount,
  UserProfile,
  UserRole,
  UserStatus,
} from "@/types"
import {
  ArrowLeft,
  BadgeCheck,
  Globe2,
  PencilLine,
  Mail,
  MessageSquareText,
  Save,
  Shield,
  ShieldAlert,
  Users,
  X,
} from "lucide-react"

const roleConfig: Record<UserRole, { label: string; color: string }> = {
  admin: { label: "管理员", color: "bg-destructive/20 text-destructive" },
  operator: { label: "运维员", color: "bg-primary/20 text-primary" },
  viewer: { label: "查看者", color: "bg-muted-foreground/20 text-muted-foreground" },
  external: { label: "外部画像", color: "bg-secondary text-secondary-foreground" },
}

const statusConfig: Record<UserStatus, { label: string; color: string }> = {
  active: { label: "活跃", color: "bg-success/20 text-success" },
  inactive: { label: "不活跃", color: "bg-warning/20 text-warning-foreground" },
  suspended: { label: "已停用", color: "bg-destructive/20 text-destructive" },
}

function LoadingView() {
  return (
    <div className="space-y-6 p-6">
      <Skeleton className="h-5 w-64" />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Skeleton className="h-[540px] rounded-xl" />
        <Skeleton className="h-[540px] rounded-xl" />
      </div>
    </div>
  )
}

const activityTypeConfig = {
  info: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/20 text-warning-foreground",
  error: "bg-destructive/15 text-destructive",
} as const

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

function normalizeTags(value: string) {
  const tags = value
    .split(/[\n,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)

  return Array.from(new Set(tags))
}

function buildProfileDraft(profile: UserProfile): { tagsInput: string; notes: string; preferredLanguage: "zh" | "en" } {
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

function PlatformAccountItem({ account }: { account: UserPlatformAccount }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-secondary/20 px-4 py-3">
      <div>
        <div className="text-sm font-medium text-foreground">{platformLabel(account.platform)}</div>
        <div className="mt-1 text-xs uppercase tracking-[0.12em] text-muted-foreground">
          平台账号
        </div>
      </div>
      <code className="rounded-md bg-background/80 px-2 py-1 text-xs text-foreground">
        {account.accountId}
      </code>
    </div>
  )
}

function ActivityItem({ item }: { item: UserActivityItem }) {
  return (
    <div className="rounded-xl border border-border bg-secondary/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className={activityTypeConfig[item.type]}>
            {item.type}
          </Badge>
          <span className="text-sm font-medium text-foreground">{item.title}</span>
        </div>
        <span className="text-xs text-muted-foreground">{item.timestamp}</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</p>
      <div className="mt-3 text-xs uppercase tracking-[0.12em] text-muted-foreground/80">
        {item.source}
      </div>
    </div>
  )
}

export default function UserDetailPage() {
  const { hasPermission } = useAuth()
  const params = useParams<{ userId: string }>()
  const userId = params.userId
  const { data: profile, isLoading, error } = useUserProfile(userId)
  const { data: activityData, isLoading: activityLoading } = useUserActivity(userId)
  const updateProfileMutation = useUpdateUserProfile()
  const updateRoleMutation = useUpdateUserRole()
  const blockUserMutation = useBlockUser()
  const [draft, setDraft] = useState<{ tagsInput: string; notes: string; preferredLanguage: "zh" | "en" }>({
    tagsInput: "",
    notes: "",
    preferredLanguage: "zh",
  })

  useEffect(() => {
    if (profile) {
      setDraft(buildProfileDraft(profile))
    }
  }, [profile])

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
                  <ShieldAlert className="size-5" />
                </EmptyMedia>
                <EmptyTitle>用户画像暂不可用</EmptyTitle>
                <EmptyDescription>
                  {error instanceof Error ? error.message : "没有找到该用户的资料。"}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button asChild>
                  <Link href="/users">
                    <ArrowLeft className="mr-2 size-4" />
                    返回用户列表
                  </Link>
                </Button>
              </EmptyContent>
            </Empty>
          </CardContent>
        </Card>
      </div>
    )
  }

  const role = roleConfig[profile.role]
  const status = statusConfig[profile.status]
  const activityItems = activityData?.items ?? []
  const normalizedTags = normalizeTags(draft.tagsInput)
  const savedTags = profile.tags
  const normalizedNotes = draft.notes.trim()
  const savedNotes = profile.notes.trim()
  const isProfileSaving = updateProfileMutation.isPending
  const isProfileDirty =
    draft.preferredLanguage !== profile.preferredLanguage ||
    normalizedNotes !== savedNotes ||
    !areTagsEqual(normalizedTags, savedTags)
  const canEditRoles = hasPermission("users:role:write")
  const canBlockUser = hasPermission("users:block")
  const canEditProfile = hasPermission("users:profile:write")

  const handleRoleUpdate = async (nextRole: UserRole) => {
    try {
      const result = await updateRoleMutation.mutateAsync({ userId: profile.id, role: nextRole })
      toast({
        title: "角色已更新",
        description: `${profile.name} 当前角色：${result.user.role}`,
      })
    } catch (mutationError) {
      toast({
        title: "更新角色失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleBlock = async () => {
    try {
      const result = await blockUserMutation.mutateAsync(profile.id)
      toast({
        title: "账户状态已更新",
        description: `${profile.name} 当前状态：${result.user.status}`,
      })
    } catch (mutationError) {
      toast({
        title: "停用账户失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleProfileSave = async () => {
    const payload: UpdateUserProfileRequest = {
      tags: normalizedTags,
      notes: draft.notes,
      preferredLanguage: draft.preferredLanguage,
    }

    try {
      const result = await updateProfileMutation.mutateAsync({ userId: profile.id, payload })
      const updatedProfile = result.user as UserProfile
      setDraft(buildProfileDraft(updatedProfile))
      toast({
        title: "用户画像已保存",
        description: `${profile.name} 的标签、备注和语言偏好已同步到后端。`,
      })
    } catch (mutationError) {
      toast({
        title: "保存用户画像失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const resetProfileDraft = () => {
    setDraft(buildProfileDraft(profile))
  }

  return (
    <div className="space-y-6 p-6">
      <div className="space-y-4">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link href="/users">用户管理</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{profile.name}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/15 text-xl font-semibold text-primary">
                {profile.name.slice(0, 1)}
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-2xl font-semibold text-foreground">{profile.name}</h1>
                  <Badge variant="secondary" className={role.color}>
                    {role.label}
                  </Badge>
                  <Badge variant="secondary" className={status.color}>
                    {status.label}
                  </Badge>
                </div>
                <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                  <Mail className="size-4" />
                  {profile.email}
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {canEditRoles && profile.role !== "admin" ? (
              <Button variant="outline" onClick={() => void handleRoleUpdate("admin")}>
                设为管理员
              </Button>
            ) : null}
            {canEditRoles && profile.role !== "operator" ? (
              <Button variant="outline" onClick={() => void handleRoleUpdate("operator")}>
                设为运维员
              </Button>
            ) : null}
            {canEditRoles && profile.role !== "viewer" ? (
              <Button variant="outline" onClick={() => void handleRoleUpdate("viewer")}>
                设为查看者
              </Button>
            ) : null}
            <Button
              variant="destructive"
              onClick={() => void handleBlock()}
              disabled={!canBlockUser || profile.status === "suspended"}
            >
              停用账户
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card className="bg-card">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">交互次数</div>
                <div className="mt-2 flex items-center gap-2 text-2xl font-semibold text-foreground">
                  <MessageSquareText className="size-5 text-primary" />
                  {profile.totalInteractions.toLocaleString()}
                </div>
              </CardContent>
            </Card>
            <Card className="bg-card">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">最后登录</div>
                <div className="mt-2 text-lg font-semibold text-foreground">{profile.lastLogin}</div>
              </CardContent>
            </Card>
            <Card className="bg-card">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">语言偏好</div>
                <div className="mt-2 flex items-center gap-2 text-lg font-semibold text-foreground">
                  <Globe2 className="size-5 text-primary" />
                  {profile.preferredLanguage === "zh" ? "中文" : "English"}
                </div>
              </CardContent>
            </Card>
            <Card className="bg-card">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">创建时间</div>
                <div className="mt-2 text-lg font-semibold text-foreground">{profile.createdAt}</div>
              </CardContent>
            </Card>
          </div>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-base">用户画像</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    当前可直接编辑标签、备注和语言偏好；来源渠道与账号绑定保持只读。
                  </p>
                </div>
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
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <PencilLine className="size-4 text-primary" />
                  基础 CRM 信息
                </div>
                <p className="mt-2 text-sm text-muted-foreground">
                  标签支持中英文逗号或换行分隔，保存时会自动去重。
                </p>
                <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
                  <div>
                    <div className="mb-2 text-sm font-medium text-foreground">标签</div>
                    <Input
                      value={draft.tagsInput}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, tagsInput: event.target.value }))
                      }
                      disabled={!canEditProfile || isProfileSaving}
                      placeholder="例如：重点客户，已跟进，英文偏好"
                      className="bg-secondary/30"
                    />
                  </div>
                  <div>
                    <div className="mb-2 text-sm font-medium text-foreground">语言偏好</div>
                    <Select
                      value={draft.preferredLanguage}
                      onValueChange={(value: "zh" | "en") =>
                        setDraft((current) => ({ ...current, preferredLanguage: value }))
                      }
                      disabled={!canEditProfile || isProfileSaving}
                    >
                      <SelectTrigger className="w-full bg-secondary/30">
                        <SelectValue placeholder="选择语言" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="zh">中文</SelectItem>
                        <SelectItem value="en">English</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              <div>
                <div className="text-sm font-medium text-foreground">标签预览</div>
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

              <Separator />

              <div>
                <div className="text-sm font-medium text-foreground">备注</div>
                <Textarea
                  value={draft.notes}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, notes: event.target.value }))
                  }
                  disabled={!canEditProfile || isProfileSaving}
                  placeholder="记录用户偏好、跟进结论或特殊说明。"
                  className="mt-3 min-h-28 bg-secondary/30"
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
                    <span className="text-sm text-muted-foreground">暂无已登记来源渠道</span>
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
                        key={`${account.platform}:${account.accountId}`}
                        account={account}
                      />
                    ))
                  ) : (
                    <div className="rounded-xl bg-secondary/30 p-4 text-sm text-muted-foreground">
                      暂无已登记的平台账号绑定。
                    </div>
                  )}
                </div>
              </div>

              <Separator />

              <div>
                <div className="text-sm font-medium text-foreground">备注</div>
                <p className="mt-3 rounded-xl bg-secondary/30 p-4 text-sm leading-6 text-muted-foreground">
                  {normalizedNotes || "暂无额外备注。"}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">活动轨迹</CardTitle>
                <span className="text-xs text-muted-foreground">
                  {activityLoading ? "同步中..." : `${activityItems.length} events`}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {activityItems.map((item) => (
                <ActivityItem key={item.id} item={item} />
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">账户摘要</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">用户 ID</span>
                <span className="font-medium text-foreground">{profile.id}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">当前角色</span>
                <span className="font-medium text-foreground">{role.label}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">账户状态</span>
                <span className="font-medium text-foreground">{status.label}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">来源渠道数</span>
                <span className="font-medium text-foreground">{profile.sourceChannels.length}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">绑定账号数</span>
                <span className="font-medium text-foreground">{profile.platformAccounts.length}</span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">推荐动作</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-xl bg-secondary/40 p-3 text-sm leading-6 text-muted-foreground">
                {profile.status === "suspended"
                  ? "账户已停用，建议后续补充解封、复核和更细粒度审计查看能力。"
                  : "当前已支持角色、停用与基础画像编辑，后续更适合补来源渠道和账号映射的后台管理能力。"}
              </div>
              <Button asChild variant="outline" className="w-full justify-between">
                <Link href="/users">
                  返回用户列表
                  <ArrowLeft className="size-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Users className="size-4 text-primary" />
                管理提示
              </div>
              <div className="rounded-xl border border-border bg-secondary/20 p-3 text-sm leading-6 text-muted-foreground">
                目前角色与停用动作都已可直接执行，后续可以在这里继续补权限矩阵、登录轨迹和来源平台绑定信息。
              </div>
              <div className="rounded-xl border border-border bg-secondary/20 p-3 text-sm leading-6 text-muted-foreground">
                标签、备注和语言偏好已经接到真实写接口；来源渠道和平台账号仍由消息接入链自动沉淀，暂不开放手工改写。
              </div>
              <div className="rounded-xl border border-border bg-secondary/20 p-3 text-sm leading-6 text-muted-foreground">
                <div className="flex items-center gap-2 font-medium text-foreground">
                  <BadgeCheck className="size-4 text-success" />
                  当前数据来源
                </div>
                <p className="mt-2">
                  来自后端用户列表与画像接口的真实响应，不再是前端占位 toast。
                </p>
              </div>
              <div className="rounded-xl border border-border bg-secondary/20 p-3 text-sm leading-6 text-muted-foreground">
                <div className="flex items-center gap-2 font-medium text-foreground">
                  <Shield className="size-4 text-primary" />
                  轨迹说明
                </div>
                <p className="mt-2">
                  活动流已经接上独立接口，当前展示登录、角色、渠道绑定和状态同步事件，后续可以继续扩展成完整审计时间线。
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
