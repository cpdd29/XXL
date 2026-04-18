"use client"

import { startTransition, useEffect, useMemo, useState, type KeyboardEvent, type MouseEvent } from "react"
import { Copy, Plus, Search, Sparkles, Trash2, Users } from "lucide-react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/hooks/use-auth"
import {
  useCreateUserTenant,
  useDeleteUserTenant,
  useManagedUserTenants,
  useUsers,
} from "@/hooks/use-users"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"
import type { UserPortrait, UserTenantOption, UserTenantStatus } from "@/types"

const PREVIEW_PAGE_SIZE = 5
const EMPTY_TENANT_DRAFT = {
  name: "",
  description: "",
}

const tenantStatusMeta: Record<
  string,
  {
    label: string
    className: string
  }
> = {
  active: {
    label: "启用中",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  inactive: {
    label: "停用",
    className: "border-amber-200 bg-amber-50 text-amber-700",
  },
  archived: {
    label: "归档",
    className: "border-slate-200 bg-slate-100 text-slate-700",
  },
}

const platformLabelMap: Record<string, string> = {
  telegram: "Telegram",
  wecom: "WeCom",
  feishu: "Feishu",
  dingtalk: "DingTalk",
  console: "Console",
}

function getTenantStatusMeta(status: UserTenantStatus) {
  return (
    tenantStatusMeta[status] ?? {
      label: status || "未知",
      className: "border-border bg-secondary text-secondary-foreground",
    }
  )
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "暂无记录"
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

function platformLabel(platform: string) {
  return platformLabelMap[platform] ?? platform
}

function StatusBadge({ status }: { status: UserTenantStatus }) {
  const meta = getTenantStatusMeta(status)

  return (
    <Badge variant="outline" className={cn("font-medium", meta.className)}>
      {meta.label}
    </Badge>
  )
}

function TenantListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={`tenant-skeleton-${index}`} className="rounded-xl border border-border p-4">
          <Skeleton className="h-5 w-32" />
          <div className="mt-4 flex items-center justify-between gap-3">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-20" />
          </div>
        </div>
      ))}
    </div>
  )
}

function ProfilePreviewSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div
          key={`tenant-profile-skeleton-${index}`}
          className="rounded-xl border border-border px-4 py-3"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-4 w-40" />
            </div>
            <Skeleton className="h-5 w-20" />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-5 w-14" />
          </div>
        </div>
      ))}
    </div>
  )
}

function TenantListItem({
  tenant,
  active,
  onSelect,
}: {
  tenant: UserTenantOption
  active: boolean
  onSelect: (tenantId: string) => void
}) {
  const handleCopyTenantId = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(tenant.id)
      } else {
        const textarea = document.createElement("textarea")
        textarea.value = tenant.id
        textarea.setAttribute("readonly", "true")
        textarea.style.position = "absolute"
        textarea.style.left = "-9999px"
        document.body.appendChild(textarea)
        textarea.focus()
        textarea.select()
        const copied = document.execCommand("copy")
        document.body.removeChild(textarea)
        if (!copied) {
          throw new Error("浏览器未完成复制，请手动复制")
        }
      }

      toast({
        title: "租户 ID 已复制",
        description: tenant.id,
      })
    } catch (error) {
      toast({
        title: "复制失败",
        description: error instanceof Error ? error.message : "请稍后重试",
        variant: "destructive",
      })
    }
  }

  const handleSelectKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return
    }

    event.preventDefault()
    onSelect(tenant.id)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={active}
      onClick={() => onSelect(tenant.id)}
      onKeyDown={handleSelectKeyDown}
      className={cn(
        "w-full cursor-pointer rounded-xl border px-4 py-3 text-left outline-none transition-colors focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
        active
          ? "border-primary bg-primary/5 shadow-sm"
          : "border-border bg-background hover:border-primary/40 hover:bg-secondary/40",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-foreground">{tenant.name}</div>
          <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
            {tenant.id}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <StatusBadge status={tenant.status} />
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-muted-foreground hover:text-foreground"
            title="复制租户 ID"
            aria-label={`复制租户 ID ${tenant.id}`}
            onClick={handleCopyTenantId}
            onKeyDown={(event) => event.stopPropagation()}
          >
            <Copy />
          </Button>
        </div>
      </div>
      <div className="mt-4 flex flex-col items-start gap-2 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span className="w-full truncate sm:w-auto">{tenant.description || "暂无租户说明"}</span>
        <span className="shrink-0">{tenant.profileCount} 份画像</span>
      </div>
    </div>
  )
}

function ProfilePreviewItem({ profile }: { profile: UserPortrait }) {
  return (
    <div className="min-w-0 rounded-xl border border-border px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate font-medium text-foreground">{profile.name}</p>
            <Badge variant="outline" className="border-border">
              {profile.preferredLanguage === "zh" ? "中文" : "English"}
            </Badge>
          </div>
          <p className="mt-1 truncate text-sm text-muted-foreground">
            {profile.email || profile.platformAccounts[0]?.accountId || "暂无可识别账号"}
          </p>
        </div>
        <div className="text-left text-xs text-muted-foreground sm:text-right">
          <p>最近活跃</p>
          <p className="mt-1 text-foreground">{formatDateTime(profile.lastActiveAt)}</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {profile.sourceChannels.length > 0 ? (
          profile.sourceChannels.slice(0, 3).map((channel) => (
            <Badge key={`${profile.id}-${channel}`} variant="outline" className="border-border">
              {platformLabel(channel)}
            </Badge>
          ))
        ) : (
          <Badge variant="outline" className="border-dashed border-border text-muted-foreground">
            暂无渠道
          </Badge>
        )}
        {profile.tags.length > 0
          ? profile.tags.slice(0, 3).map((tag) => (
              <Badge key={`${profile.id}-${tag}`} variant="secondary">
                {tag}
              </Badge>
            ))
          : null}
      </div>
      <p className="mt-4 text-sm text-muted-foreground">
        {profile.interactionSummary?.trim() || profile.notes?.trim() || "暂无更多画像摘要。"}
      </p>
    </div>
  )
}

export default function TenantManagementPage() {
  const { hasPermission } = useAuth()
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedTenantId, setSelectedTenantId] = useState("")
  const [previewPage, setPreviewPage] = useState(1)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [tenantDraft, setTenantDraft] = useState(EMPTY_TENANT_DRAFT)
  const { data, isLoading, error } = useManagedUserTenants()
  const createTenant = useCreateUserTenant()
  const deleteTenant = useDeleteUserTenant()

  const tenants = data?.items ?? []
  const canManageTenants = hasPermission("users:profile:write")

  const filteredTenants = useMemo(() => {
    const keyword = searchQuery.trim().toLowerCase()
    if (!keyword) {
      return tenants
    }

    return tenants.filter((tenant) => {
      const searchableText = [tenant.name, tenant.id, tenant.description, tenant.status]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()

      return searchableText.includes(keyword)
    })
  }, [searchQuery, tenants])

  useEffect(() => {
    if (!tenants.length) {
      if (selectedTenantId) {
        setSelectedTenantId("")
      }
      return
    }

    const hasSelectedTenant = tenants.some((tenant) => tenant.id === selectedTenantId)
    if (hasSelectedTenant) {
      return
    }

    const nextTenantId =
      (data?.defaultTenantId && tenants.some((tenant) => tenant.id === data.defaultTenantId)
        ? data.defaultTenantId
        : null) ?? tenants[0]?.id ?? ""

    if (nextTenantId && nextTenantId !== selectedTenantId) {
      setSelectedTenantId(nextTenantId)
    }
  }, [data?.defaultTenantId, selectedTenantId, tenants])

  const selectedTenant =
    tenants.find((tenant) => tenant.id === selectedTenantId) ?? filteredTenants[0] ?? null

  const {
    data: profileData,
    isLoading: isProfileLoading,
    error: profileError,
    isFetching: isProfileFetching,
  } = useUsers({
    tenantId: selectedTenant?.id,
    enabled: Boolean(selectedTenant?.id),
    management: true,
  })

  const previewAllProfiles = profileData?.items ?? []
  const previewCount = profileData
    ? profileData.total ?? previewAllProfiles.length
    : selectedTenant?.profileCount ?? 0
  const previewPageCount = Math.max(1, Math.ceil(previewCount / PREVIEW_PAGE_SIZE))
  const canDeleteSelectedTenant = canManageTenants && Boolean(selectedTenant)

  useEffect(() => {
    setPreviewPage(1)
  }, [selectedTenant?.id])

  useEffect(() => {
    if (previewPage > previewPageCount) {
      setPreviewPage(previewPageCount)
    }
  }, [previewPage, previewPageCount])

  const previewProfiles = useMemo(() => {
    const startIndex = (previewPage - 1) * PREVIEW_PAGE_SIZE
    return previewAllProfiles.slice(startIndex, startIndex + PREVIEW_PAGE_SIZE)
  }, [previewAllProfiles, previewPage])

  const previewRangeStart = previewCount === 0 ? 0 : (previewPage - 1) * PREVIEW_PAGE_SIZE + 1
  const previewRangeEnd = Math.min(previewPage * PREVIEW_PAGE_SIZE, previewCount)

  const handleSelectTenant = (tenantId: string) => {
    startTransition(() => {
      setSelectedTenantId(tenantId)
    })
  }

  const handleSearchChange = (value: string) => {
    startTransition(() => {
      setSearchQuery(value)
    })
  }

  const handleCreateTenant = async () => {
    const nextTenantName = tenantDraft.name.trim()
    const nextTenantDescription = tenantDraft.description.trim()

    if (!nextTenantName) {
      toast({
        title: "租户信息不完整",
        description: "请填写租户名称。",
      })
      return
    }

    try {
      const response = await createTenant.mutateAsync({
        name: nextTenantName,
        description: nextTenantDescription,
      })
      setCreateDialogOpen(false)
      setTenantDraft(EMPTY_TENANT_DRAFT)
      if (response.tenant?.id) {
        setSelectedTenantId(response.tenant.id)
      }
      toast({
        title: "租户已新增",
        description: `已创建租户 ${response.tenant?.name ?? nextTenantName}。`,
      })
    } catch (createError) {
      toast({
        title: "新增租户失败",
        description: createError instanceof Error ? createError.message : "未知错误",
      })
    }
  }

  const handleDeleteTenant = async () => {
    if (!selectedTenant) {
      return
    }

    try {
      await deleteTenant.mutateAsync({ tenantId: selectedTenant.id })
      setDeleteDialogOpen(false)
      setSelectedTenantId("")
      toast({
        title: "租户已删除",
        description: `${selectedTenant.name} 及其关联画像数据已删除。`,
      })
    } catch (deleteError) {
      toast({
        title: "删除租户失败",
        description: deleteError instanceof Error ? deleteError.message : "未知错误",
      })
    }
  }

  return (
    <>
      <div className="flex min-h-full flex-col gap-4 p-4 md:gap-6 md:p-6 lg:h-full lg:overflow-hidden">
        <div className="grid min-w-0 gap-4 md:gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)] 2xl:grid-cols-[minmax(320px,400px)_minmax(0,1fr)]">
          <Card className="min-w-0 bg-card lg:flex lg:min-h-0 lg:max-h-full lg:flex-col">
            <CardHeader className="space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <CardTitle className="text-base">租户列表</CardTitle>
                {canManageTenants ? (
                  <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap">
                    <Button
                      type="button"
                      size="sm"
                      className="w-full sm:w-auto"
                      onClick={() => setCreateDialogOpen(true)}
                    >
                      <Plus className="size-4" />
                      新增租户
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      className="w-full sm:w-auto"
                      disabled={!canDeleteSelectedTenant || deleteTenant.isPending}
                      onClick={() => setDeleteDialogOpen(true)}
                    >
                      <Trash2 className="size-4" />
                      删除租户
                    </Button>
                  </div>
                ) : null}
              </div>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(event) => handleSearchChange(event.target.value)}
                  placeholder="搜索租户名称 / 说明"
                  className="bg-secondary pl-10"
                />
              </div>
            </CardHeader>
            <CardContent className="min-h-0 lg:flex-1 lg:overflow-y-auto">
              {error ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                  租户列表加载失败：{error instanceof Error ? error.message : "未知错误"}
                </div>
              ) : isLoading ? (
                <TenantListSkeleton />
              ) : filteredTenants.length === 0 ? (
                <Empty className="border border-dashed border-border bg-secondary/20">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <Search className="size-5" />
                    </EmptyMedia>
                    <EmptyTitle>未匹配到租户</EmptyTitle>
                    <EmptyDescription>
                      调整搜索关键词后再试，或者清空搜索查看全部租户。
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : (
                <div className="space-y-3">
                  {filteredTenants.map((tenant) => (
                    <TenantListItem
                      key={tenant.id}
                      tenant={tenant}
                      active={tenant.id === selectedTenant?.id}
                      onSelect={handleSelectTenant}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="min-w-0 lg:min-h-0 lg:h-full">
            <Card className="min-w-0 bg-card lg:flex lg:h-full lg:min-h-0 lg:max-h-full lg:flex-col">
              <CardHeader className="shrink-0">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <CardTitle className="text-base">画像预览</CardTitle>
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedTenant ? (
                      <Badge variant="secondary">{selectedTenant.name}</Badge>
                    ) : null}
                    <Badge variant="outline" className="border-border">
                      {selectedTenant
                        ? isProfileFetching
                          ? "同步中..."
                          : `${previewCount} 份画像`
                        : "未选择租户"}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="min-h-[320px] lg:flex lg:h-full lg:min-h-0 lg:flex-1 lg:flex-col">
                {!selectedTenant ? (
                  <Empty className="h-full border border-dashed border-border bg-secondary/20">
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <Users className="size-5" />
                      </EmptyMedia>
                      <EmptyTitle>请选择租户</EmptyTitle>
                      <EmptyDescription>
                        选择左侧租户后，这里会展示该租户下的画像预览。
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                ) : profileError ? (
                  <div className="flex h-full items-center rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                    画像预览加载失败：{profileError instanceof Error ? profileError.message : "未知错误"}
                  </div>
                ) : isProfileLoading ? (
                  <div className="flex h-full flex-col justify-center">
                    <ProfilePreviewSkeleton />
                  </div>
                ) : previewProfiles.length === 0 ? (
                  <Empty className="h-full border border-dashed border-border bg-secondary/20">
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <Sparkles className="size-5" />
                      </EmptyMedia>
                      <EmptyTitle>该租户暂无画像</EmptyTitle>
                      <EmptyDescription>
                        当前租户还没有沉淀人员画像，接入真实用户后会在这里显示。
                      </EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent className="text-muted-foreground">
                      可先从 Telegram、DingTalk、WeCom、Feishu 等渠道采集真实用户互动数据。
                    </EmptyContent>
                  </Empty>
                ) : (
                  <div className="flex h-full min-h-0 flex-col gap-4 lg:flex-1">
                    <div className="space-y-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
                      {previewProfiles.map((profile) => (
                        <ProfilePreviewItem key={profile.id} profile={profile} />
                      ))}
                    </div>
                    <div className="flex shrink-0 flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-sm text-muted-foreground">
                        显示 {previewRangeStart}-{previewRangeEnd} / {previewCount}
                      </p>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={previewPage <= 1}
                          onClick={() => setPreviewPage((current) => Math.max(1, current - 1))}
                        >
                          上一页
                        </Button>
                        <span className="text-sm text-muted-foreground">
                          第 {previewPage} / {previewPageCount} 页
                        </span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={previewPage >= previewPageCount}
                          onClick={() =>
                            setPreviewPage((current) => Math.min(previewPageCount, current + 1))
                          }
                        >
                          下一页
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          if (createTenant.isPending) {
            return
          }
          setCreateDialogOpen(open)
          if (!open) {
            setTenantDraft(EMPTY_TENANT_DRAFT)
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新增租户</DialogTitle>
            <DialogDescription>填写租户名称和说明后创建新的租户目录，租户 ID 将由后端自动生成。</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="tenant-name">租户名称</Label>
              <Input
                id="tenant-name"
                value={tenantDraft.name}
                onChange={(event) =>
                  setTenantDraft((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="例如：Alpha Corp"
                disabled={createTenant.isPending}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tenant-description">租户说明</Label>
              <Textarea
                id="tenant-description"
                value={tenantDraft.description}
                onChange={(event) =>
                  setTenantDraft((current) => ({ ...current, description: event.target.value }))
                }
                placeholder="例如：用于承接华东区客户服务团队的人员画像与消息接入。"
                disabled={createTenant.isPending}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={createTenant.isPending}
              onClick={() => {
                setCreateDialogOpen(false)
                setTenantDraft(EMPTY_TENANT_DRAFT)
              }}
            >
              取消
            </Button>
            <Button
              type="button"
              disabled={createTenant.isPending}
              onClick={() => void handleCreateTenant()}
            >
              {createTenant.isPending ? "创建中..." : "创建租户"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          if (deleteTenant.isPending) {
            return
          }
          setDeleteDialogOpen(open)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除这个租户？</AlertDialogTitle>
            <AlertDialogDescription>
              将删除租户目录项“{selectedTenant?.name ?? "-"}”，并一并删除该租户下的画像及相关数据。此操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteTenant.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={deleteTenant.isPending}
              onClick={(event) => {
                event.preventDefault()
                void handleDeleteTenant()
              }}
            >
              {deleteTenant.isPending ? "删除中..." : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
