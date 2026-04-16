"use client"

import { startTransition, useDeferredValue, useState } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"
import { downloadUsers, useBlockUser, useUpdateUserRole, useUsers } from "@/hooks/use-users"
import { toast } from "@/hooks/use-toast"
import type { User, UserRole, UserStatus } from "@/types"
import { Search, Plus, MoreVertical, Filter, Download } from "lucide-react"

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

export default function UsersPage() {
  const { hasPermission } = useAuth()
  const router = useRouter()
  const [searchQuery, setSearchQuery] = useState("")
  const [showFilters, setShowFilters] = useState(false)
  const [roleFilter, setRoleFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [isExporting, setIsExporting] = useState(false)
  const deferredSearchQuery = useDeferredValue(searchQuery.trim())
  const { data: allUsersData } = useUsers()
  const { data, isLoading, error, isFetching } = useUsers({
    search: deferredSearchQuery || undefined,
    role: roleFilter,
    status: statusFilter,
  })
  const updateRoleMutation = useUpdateUserRole()
  const blockUserMutation = useBlockUser()
  const users = data?.items ?? []
  const allUserCount = allUsersData?.total ?? users.length
  const activeAdvancedFilterCount = [
    roleFilter !== "all",
    statusFilter !== "all",
  ].filter(Boolean).length
  const isSyncingSearch = deferredSearchQuery !== searchQuery.trim()
  const canExportUsers = hasPermission("users:read")
  const canEditRoles = hasPermission("users:role:write")
  const canBlockUsers = hasPermission("users:block")

  const handleRoleUpdate = async (user: User, role: UserRole) => {
    try {
      const result = await updateRoleMutation.mutateAsync({ userId: user.id, role })
      toast({
        title: "角色已更新",
        description: `${user.name} 当前角色：${result.user.role ?? role}`,
      })
    } catch (mutationError) {
      toast({
        title: "更新角色失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleBlockUser = async (user: User) => {
    try {
      const result = await blockUserMutation.mutateAsync(user.id)
      toast({
        title: "账户状态已更新",
        description: `${user.name} 当前状态：${result.user.status}`,
      })
    } catch (mutationError) {
      toast({
        title: "停用账户失败",
        description: mutationError instanceof Error ? mutationError.message : "未知错误",
      })
    }
  }

  const handleSearchChange = (value: string) => {
    startTransition(() => {
      setSearchQuery(value)
    })
  }

  const resetAdvancedFilters = () => {
    startTransition(() => {
      setRoleFilter("all")
      setStatusFilter("all")
    })
  }

  const handleExportUsers = async () => {
    try {
      setIsExporting(true)
      const { blob, filename } = await downloadUsers({
        search: deferredSearchQuery || undefined,
        role: roleFilter,
        status: statusFilter,
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
        title: "用户列表导出成功",
        description: `已按当前筛选条件导出 ${users.length} 位用户。`,
      })
    } catch (exportError) {
      toast({
        title: "用户列表导出失败",
        description: exportError instanceof Error ? exportError.message : "未知错误",
      })
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">用户管理</h1>
          <p className="text-sm text-muted-foreground">
            管理系统用户和权限
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportUsers}
            disabled={!canExportUsers || isExporting || isLoading || isFetching || isSyncingSearch}
          >
            <Download className="mr-2 size-4" />
            {isExporting ? "导出中..." : "导出"}
          </Button>
          <Button
            size="sm"
            onClick={() =>
              toast({
                title: "添加用户入口已保留",
                description: "后续会接入用户创建表单。",
              })
            }
          >
            <Plus className="mr-2 size-4" />
            添加用户
          </Button>
        </div>
      </div>

      <Card className="flex-1 bg-card">
        <CardHeader className="pb-3">
          <div className="space-y-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <CardTitle className="text-base">用户列表</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {deferredSearchQuery || activeAdvancedFilterCount > 0
                    ? `当前匹配 ${users.length} / ${allUserCount} 位用户`
                    : `当前共 ${allUserCount} 位用户`}
                  {isFetching ? "，正在同步筛选结果..." : ""}
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="搜索用户 / 渠道 / 平台账号..."
                    value={searchQuery}
                    onChange={(e) => handleSearchChange(e.target.value)}
                    className="w-full bg-secondary pl-10 sm:w-64"
                  />
                </div>
                <Button
                  variant={showFilters || activeAdvancedFilterCount > 0 ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => setShowFilters((current) => !current)}
                >
                  <Filter className="mr-2 size-4" />
                  筛选
                  {activeAdvancedFilterCount > 0 ? ` (${activeAdvancedFilterCount})` : ""}
                </Button>
              </div>
            </div>
            {showFilters ? (
              <div className="grid gap-3 rounded-xl border border-border bg-secondary/20 p-4 md:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
                <div className="md:col-span-4">
                  <div className="text-sm font-medium text-foreground">高级筛选</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    支持和搜索条件叠加，用于快速定位角色或状态范围内的用户。
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-sm font-medium text-foreground">角色</div>
                  <Select
                    value={roleFilter}
                    onValueChange={(value) =>
                      startTransition(() => {
                        setRoleFilter(value)
                      })
                    }
                  >
                    <SelectTrigger className="w-full bg-background">
                      <SelectValue placeholder="全部角色" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部角色</SelectItem>
                      <SelectItem value="admin">管理员</SelectItem>
                      <SelectItem value="operator">运维员</SelectItem>
                      <SelectItem value="viewer">查看者</SelectItem>
                      <SelectItem value="external">外部画像</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <div className="mb-2 text-sm font-medium text-foreground">状态</div>
                  <Select
                    value={statusFilter}
                    onValueChange={(value) =>
                      startTransition(() => {
                        setStatusFilter(value)
                      })
                    }
                  >
                    <SelectTrigger className="w-full bg-background">
                      <SelectValue placeholder="全部状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部状态</SelectItem>
                      <SelectItem value="active">活跃</SelectItem>
                      <SelectItem value="inactive">不活跃</SelectItem>
                      <SelectItem value="suspended">已停用</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end">
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={resetAdvancedFilters}
                    disabled={activeAdvancedFilterCount === 0}
                  >
                    清空筛选
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="mb-4 text-sm text-destructive">
              用户数据加载失败：{error instanceof Error ? error.message : "未知错误"}
            </div>
          )}

          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground">用户</TableHead>
                <TableHead className="text-muted-foreground">角色</TableHead>
                <TableHead className="text-muted-foreground">状态</TableHead>
                <TableHead className="text-muted-foreground">最后登录</TableHead>
                <TableHead className="text-muted-foreground">交互次数</TableHead>
                <TableHead className="text-muted-foreground">创建时间</TableHead>
                <TableHead className="text-right text-muted-foreground">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id} className="border-border">
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Avatar className="size-8">
                        <AvatarFallback className="bg-primary/20 text-primary text-xs">
                          {user.name.slice(0, 1)}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <div className="font-medium text-foreground">
                          {user.name}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {user.email}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={cn("text-xs", roleConfig[user.role].color)}
                    >
                      {roleConfig[user.role].label}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={cn("text-xs", statusConfig[user.status].color)}
                    >
                      {statusConfig[user.status].label}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {user.lastLogin}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {user.totalInteractions.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {user.createdAt}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="size-8">
                          <MoreVertical className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onSelect={() => router.push(`/users/${encodeURIComponent(user.id)}`)}
                        >
                          查看详情
                        </DropdownMenuItem>
                        {canEditRoles && user.role !== "admin" && (
                          <DropdownMenuItem onSelect={() => void handleRoleUpdate(user, "admin")}>
                            设为管理员
                          </DropdownMenuItem>
                        )}
                        {canEditRoles && user.role !== "operator" && (
                          <DropdownMenuItem onSelect={() => void handleRoleUpdate(user, "operator")}>
                            设为运维员
                          </DropdownMenuItem>
                        )}
                        {canEditRoles && user.role !== "viewer" && (
                          <DropdownMenuItem onSelect={() => void handleRoleUpdate(user, "viewer")}>
                            设为查看者
                          </DropdownMenuItem>
                        )}
                        {canBlockUsers ? (
                          <DropdownMenuItem
                            className="text-destructive"
                            onSelect={() => void handleBlockUser(user)}
                          >
                            停用账户
                          </DropdownMenuItem>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {isLoading && (
            <div className="flex h-40 items-center justify-center text-muted-foreground">
              正在加载用户数据...
            </div>
          )}
          {!isLoading && users.length === 0 && (
            <div className="flex h-40 items-center justify-center text-muted-foreground">
              没有找到匹配的用户
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
