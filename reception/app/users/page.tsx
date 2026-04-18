"use client"

import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { downloadUsers, useUserTenants, useUsers } from "@/hooks/use-users"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"
import type { UserPortrait } from "@/types"
import { Building2, Download, Languages, MessageSquareText, Search, Users } from "lucide-react"

const TENANT_STORAGE_KEY = "user-portraits:selected-tenant"

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

function languageLabel(language: "zh" | "en") {
  return language === "zh" ? "中文" : "English"
}

function summarizeNotes(notes: string, maxLength = 28) {
  const normalized = notes.trim()
  if (!normalized) {
    return "暂无备注"
  }
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
}

function LoadingTable() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={`user-portrait-loading-${index}`}
          className="grid gap-3 rounded-xl border border-border px-4 py-3 md:grid-cols-[1.2fr_1fr_1fr_1fr_120px_140px_120px_1fr]"
        >
          {Array.from({ length: 8 }).map((__, cellIndex) => (
            <Skeleton key={`user-portrait-loading-cell-${index}-${cellIndex}`} className="h-5 w-full" />
          ))}
        </div>
      ))}
    </div>
  )
}

function PortraitChannels({ portrait }: { portrait: UserPortrait }) {
  if (portrait.sourceChannels.length === 0) {
    return <span className="text-xs text-muted-foreground">暂无渠道</span>
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {portrait.sourceChannels.slice(0, 2).map((channel) => (
        <Badge key={`${portrait.id}-${channel}`} variant="outline" className="border-border">
          {platformLabel(channel)}
        </Badge>
      ))}
      {portrait.sourceChannels.length > 2 ? (
        <Badge variant="secondary">+{portrait.sourceChannels.length - 2}</Badge>
      ) : null}
    </div>
  )
}

function PortraitAccounts({ portrait }: { portrait: UserPortrait }) {
  if (portrait.platformAccounts.length === 0) {
    return <span className="text-xs text-muted-foreground">暂无账号</span>
  }

  return (
    <div className="space-y-1">
      {portrait.platformAccounts.slice(0, 2).map((account) => (
        <div key={`${portrait.id}-${account.platform}-${account.accountId}`} className="text-xs text-foreground">
          {platformLabel(account.platform)} / {account.accountId}
        </div>
      ))}
      {portrait.platformAccounts.length > 2 ? (
        <div className="text-xs text-muted-foreground">+{portrait.platformAccounts.length - 2} 个平台账号</div>
      ) : null}
    </div>
  )
}

function PortraitTags({ portrait }: { portrait: UserPortrait }) {
  if (portrait.tags.length === 0) {
    return <span className="text-xs text-muted-foreground">暂无标签</span>
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {portrait.tags.slice(0, 2).map((tag) => (
        <Badge key={`${portrait.id}-${tag}`} variant="secondary" className="bg-primary/10 text-primary">
          {tag}
        </Badge>
      ))}
      {portrait.tags.length > 2 ? <Badge variant="secondary">+{portrait.tags.length - 2}</Badge> : null}
    </div>
  )
}

export default function UsersPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedTenant, setSelectedTenant] = useState("")
  const [hasTenantHydrated, setHasTenantHydrated] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const deferredSearchQuery = useDeferredValue(searchQuery.trim())
  const { data: tenantOptionsData, isLoading: tenantOptionsLoading, error: tenantOptionsError } = useUserTenants()
  const canViewAllTenants = tenantOptionsData?.canViewAllTenants ?? false
  const defaultTenantId = tenantOptionsData?.defaultTenantId ?? ""
  const {
    data: tenantPortraitsData,
    isLoading: tenantPortraitsLoading,
    error: tenantPortraitsError,
  } = useUsers({
    tenantId: selectedTenant || undefined,
    enabled: Boolean(selectedTenant),
  })
  const { data, isLoading, error, isFetching } = useUsers({
    tenantId: selectedTenant || undefined,
    search: deferredSearchQuery || undefined,
    enabled: Boolean(selectedTenant),
  })

  useEffect(() => {
    const tenantFromQuery = searchParams.get("tenant")
    if (tenantFromQuery) {
      setSelectedTenant(tenantFromQuery)
      setHasTenantHydrated(true)
      return
    }

    const storedTenant = window.localStorage.getItem(TENANT_STORAGE_KEY)
    if (storedTenant) {
      setSelectedTenant(storedTenant)
    }
    setHasTenantHydrated(true)
  }, [searchParams])

  useEffect(() => {
    if (!hasTenantHydrated || selectedTenant || !defaultTenantId) {
      return
    }
    setSelectedTenant(defaultTenantId)
  }, [defaultTenantId, hasTenantHydrated, selectedTenant])

  useEffect(() => {
    if (!hasTenantHydrated || !tenantOptionsData || !selectedTenant) {
      return
    }

    const availableTenantIds = new Set(tenantOptionsData.items.map((tenant) => tenant.id))
    if (selectedTenant === "all" && canViewAllTenants) {
      return
    }

    if (!availableTenantIds.has(selectedTenant)) {
      setSelectedTenant(defaultTenantId || "")
    }
  }, [canViewAllTenants, defaultTenantId, hasTenantHydrated, selectedTenant, tenantOptionsData])

  useEffect(() => {
    if (!hasTenantHydrated) {
      return
    }
    if (!selectedTenant) {
      window.localStorage.removeItem(TENANT_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(TENANT_STORAGE_KEY, selectedTenant)
  }, [hasTenantHydrated, selectedTenant])

  const tenantOptions = tenantOptionsData?.items ?? []
  const tenantPortraits = tenantPortraitsData?.items ?? []
  const portraits = data?.items ?? []
  const selectedTenantMeta = selectedTenant === "all"
    ? {
        id: "all",
        name: "全部租户",
        status: "active",
        profileCount: tenantPortraits.length,
        description: "跨租户查看所有人员画像。",
      }
    : tenantOptions.find((tenant) => tenant.id === selectedTenant) ?? null
  const isSyncingSearch = deferredSearchQuery !== searchQuery.trim()

  const handleSearchChange = (value: string) => {
    startTransition(() => {
      setSearchQuery(value)
    })
  }

  const handleTenantChange = (value: string) => {
    startTransition(() => {
      setSelectedTenant(value)
    })
  }

  const openPortrait = (portrait: UserPortrait) => {
    router.push(`/users/${portrait.id}?tenant=${encodeURIComponent(portrait.tenantId)}`)
  }

  const summaryText = useMemo(() => {
    if (!selectedTenantMeta) {
      return "请先选择租户，再查看对应的人员画像。"
    }

      return `${selectedTenantMeta.name} 共 ${tenantPortraits.length} 份画像${isFetching ? "，正在同步..." : ""}`
    }, [isFetching, selectedTenantMeta, tenantPortraits.length])

  const handleExport = async () => {
    if (!selectedTenant) {
      return
    }

    try {
      setIsExporting(true)
      const { blob, filename } = await downloadUsers({
        tenantId: selectedTenant === "all" ? undefined : selectedTenant,
        search: deferredSearchQuery || undefined,
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
        title: "画像导出成功",
        description: `已导出 ${selectedTenantMeta?.name ?? selectedTenant} 的当前筛选结果。`,
      })
    } catch (exportError) {
      toast({
        title: "画像导出失败",
        description: exportError instanceof Error ? exportError.message : "未知错误",
      })
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 space-y-2">
        <h1 className="text-2xl font-bold text-foreground">人员画像</h1>
        <p className="text-sm text-muted-foreground">按真实租户上下文查看人员来源、平台映射、语言偏好和互动画像。</p>
      </div>

      <Card className="flex-1 bg-card">
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <CardTitle className="text-base">画像列表</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">{summaryText}</p>
            </div>
            <div className="flex flex-col gap-2 md:flex-row md:items-center">
              <Select value={selectedTenant} onValueChange={handleTenantChange}>
                <SelectTrigger className="w-full bg-secondary md:w-64">
                  <SelectValue placeholder="选择租户" />
                </SelectTrigger>
                <SelectContent>
                  {canViewAllTenants ? <SelectItem value="all">全部租户</SelectItem> : null}
                  {tenantOptions.map((tenant) => (
                    <SelectItem key={tenant.id} value={tenant.id}>
                      {tenant.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="搜索姓名 / 渠道 / 平台账号 / 标签"
                  value={searchQuery}
                  onChange={(event) => handleSearchChange(event.target.value)}
                  className="w-full bg-secondary pl-10 md:w-72"
                  disabled={!selectedTenant}
                />
              </div>
              <Button
                variant="outline"
                onClick={() => void handleExport()}
                disabled={!selectedTenant || selectedTenant === "all" || isExporting || tenantPortraits.length === 0}
              >
                <Download className="mr-2 size-4" />
                {isExporting ? "导出中..." : "导出画像"}
              </Button>
            </div>
          </div>
          {selectedTenantMeta ? (
            <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{selectedTenantMeta.name}</span>
              <span className="ml-2">{selectedTenantMeta.description}</span>
            </div>
          ) : null}
        </CardHeader>
        <CardContent className="h-full">
          {tenantOptionsError || tenantPortraitsError || error ? (
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Users className="size-5" />
                </EmptyMedia>
                <EmptyTitle>人员画像加载失败</EmptyTitle>
                <EmptyDescription>
                  {(error instanceof Error ? error.message : null) ??
                    (tenantPortraitsError instanceof Error ? tenantPortraitsError.message : null) ??
                    (tenantOptionsError instanceof Error ? tenantOptionsError.message : "请稍后重试。")}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : tenantOptionsLoading || (selectedTenant && (tenantPortraitsLoading || isLoading)) ? (
            <LoadingTable />
          ) : !selectedTenant ? (
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Building2 className="size-5" />
                </EmptyMedia>
                <EmptyTitle>未选择租户</EmptyTitle>
                <EmptyDescription>
                  先选择一个租户，再查看该租户下的人员画像列表与可导出结果。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : tenantPortraits.length === 0 ? (
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Users className="size-5" />
                </EmptyMedia>
                <EmptyTitle>当前租户无画像</EmptyTitle>
                <EmptyDescription>
                  该租户下还没有可展示的人员画像，后续接入新渠道或补齐画像后会出现在这里。
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button variant="outline" onClick={() => setSelectedTenant("")}>
                  重新选择租户
                </Button>
              </EmptyContent>
            </Empty>
          ) : portraits.length === 0 ? (
            <Empty className="border-border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Search className="size-5" />
                </EmptyMedia>
                <EmptyTitle>搜索无结果</EmptyTitle>
                <EmptyDescription>
                  当前租户下没有匹配“{deferredSearchQuery}”的人员画像，请调整搜索词后再试。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="overflow-hidden rounded-xl border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>人员名称</TableHead>
                    <TableHead>来源渠道</TableHead>
                    <TableHead>平台账号</TableHead>
                    <TableHead>标签</TableHead>
                    <TableHead>语言偏好</TableHead>
                    <TableHead>最近活跃</TableHead>
                    <TableHead>累计交互次数</TableHead>
                    <TableHead>备注</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {portraits.map((portrait) => (
                    <TableRow
                      key={portrait.id}
                      className={cn("cursor-pointer", isSyncingSearch ? "opacity-70" : "")}
                      onClick={() => openPortrait(portrait)}
                    >
                      <TableCell>
                        <div className="space-y-1">
                          <div className="font-medium text-foreground">{portrait.name}</div>
                          <div className="text-xs text-muted-foreground">{portrait.interactionSummary || portrait.tenantName}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <PortraitChannels portrait={portrait} />
                      </TableCell>
                      <TableCell>
                        <PortraitAccounts portrait={portrait} />
                      </TableCell>
                      <TableCell>
                        <PortraitTags portrait={portrait} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 text-sm text-foreground">
                          <Languages className="size-4 text-primary" />
                          {languageLabel(portrait.preferredLanguage)}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-foreground">{portrait.lastActiveAt}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                          <MessageSquareText className="size-4 text-primary" />
                          {portrait.totalInteractions.toLocaleString()}
                        </div>
                      </TableCell>
                      <TableCell className="max-w-64 text-sm text-muted-foreground">{summarizeNotes(portrait.notes)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          <div className="mt-4 text-xs text-muted-foreground">
            {selectedTenant ? `当前展示 ${portraits.length} / ${tenantPortraits.length} 份画像` : "租户上下文未选择"}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
