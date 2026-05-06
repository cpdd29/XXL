"use client"

import { useDeferredValue, useMemo, useState } from "react"
import { Badge } from "@/shared/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"
import { useUserTenants } from "@/modules/organization/hooks/use-users"
import { useLongTermMemories } from "@/modules/organization/hooks/use-memory"

const memoryTypeOptions = [
  { value: "all", label: "全部类型" },
  { value: "tenant_soul", label: "tenant_soul" },
  { value: "customer_preference", label: "customer_preference" },
  { value: "business_fact", label: "business_fact" },
  { value: "task_result", label: "task_result" },
  { value: "service_policy", label: "service_policy" },
]

const memoryScopeOptions = [
  { value: "all", label: "全部作用域" },
  { value: "tenant", label: "tenant" },
  { value: "global", label: "global" },
]

const subjectTypeOptions = [
  { value: "all", label: "全部主体" },
  { value: "tenant", label: "tenant" },
  { value: "customer", label: "customer" },
  { value: "task_summary", label: "task_summary" },
]

function formatDateTime(value: string | null | undefined) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function memoryTypeBadgeClass(memoryType: string) {
  if (memoryType === "tenant_soul") return "bg-primary/10 text-primary"
  if (memoryType === "customer_preference") return "bg-success/15 text-success"
  if (memoryType === "task_result") return "bg-warning/15 text-warning-foreground"
  return "bg-secondary text-secondary-foreground"
}

export default function TenantMemoryPage() {
  const [tenantId, setTenantId] = useState("")
  const [memoryType, setMemoryType] = useState("all")
  const [memoryScope, setMemoryScope] = useState("tenant")
  const [subjectType, setSubjectType] = useState("all")
  const [subjectId, setSubjectId] = useState("")
  const [query, setQuery] = useState("")
  const deferredQuery = useDeferredValue(query.trim())

  const { data: tenantOptionsData } = useUserTenants()
  const tenantOptions = tenantOptionsData?.items ?? []

  const { data, isLoading, error, isFetching } = useLongTermMemories({
    tenantId: tenantId || undefined,
    subjectType: subjectType === "all" ? undefined : subjectType,
    subjectId: subjectId.trim() || undefined,
    memoryType: memoryType === "all" ? undefined : memoryType,
    query: deferredQuery || undefined,
    memoryScope: memoryScope === "all" ? undefined : memoryScope,
    limit: 50,
  })

  const items = useMemo(() => {
    const sourceItems = data?.items ?? []
    if (subjectType === "all") return sourceItems
    return sourceItems.filter((item) => item.subjectType === subjectType)
  }, [data?.items, subjectType])
  const summary = useMemo(() => {
    const scopeBreakdown = items.reduce(
      (result, item) => {
        if (item.memoryScope === "tenant") result.tenant += 1
        if (item.memoryScope === "global") result.global += 1
        return result
      },
      { tenant: 0, global: 0 },
    )
    return {
      total: items.length,
      tenant: scopeBreakdown.tenant,
      global: scopeBreakdown.global,
    }
  }, [items])

  return (
    <div className="p-6">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>平台长期记忆</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
              <div className="space-y-2">
                <Label>租户</Label>
                <Select value={tenantId || "all"} onValueChange={(value) => setTenantId(value === "all" ? "" : value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择租户" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部租户</SelectItem>
                    {tenantOptions.map((tenant) => (
                      <SelectItem key={tenant.id} value={tenant.id}>
                        {tenant.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>记忆类型</Label>
                <Select value={memoryType} onValueChange={setMemoryType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {memoryTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>作用域</Label>
                <Select value={memoryScope} onValueChange={setMemoryScope}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {memoryScopeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>主体类型</Label>
                <Select value={subjectType} onValueChange={setSubjectType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {subjectTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>主体 ID</Label>
                <Input value={subjectId} onChange={(event) => setSubjectId(event.target.value)} placeholder="customer_xxx / tenant_xxx" />
              </div>
              <div className="space-y-2">
                <Label>检索词</Label>
                <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 tenant_soul / 偏好 / 事实" />
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-border p-3">
                <div className="text-sm text-muted-foreground">记忆总数</div>
                <div className="mt-1 text-2xl font-semibold text-foreground">{summary.total}</div>
              </div>
              <div className="rounded-xl border border-border p-3">
                <div className="text-sm text-muted-foreground">tenant 作用域</div>
                <div className="mt-1 text-2xl font-semibold text-foreground">{summary.tenant}</div>
              </div>
              <div className="rounded-xl border border-border p-3">
                <div className="text-sm text-muted-foreground">global 作用域</div>
                <div className="mt-1 text-2xl font-semibold text-foreground">{summary.global}</div>
              </div>
            </div>

            {error ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                长期记忆加载失败：{error instanceof Error ? error.message : "未知错误"}
              </div>
            ) : null}

            <div className="rounded-lg border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>类型</TableHead>
                    <TableHead>主体</TableHead>
                    <TableHead>摘要</TableHead>
                    <TableHead>作用域</TableHead>
                    <TableHead>来源</TableHead>
                    <TableHead>更新时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <Badge variant="secondary" className={memoryTypeBadgeClass(item.memoryType)}>
                          {item.memoryType}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="text-sm font-medium text-foreground">{item.subjectType || "--"}</div>
                          <div className="text-xs text-muted-foreground">{item.subjectId || "--"}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="max-w-[420px] space-y-1">
                          <div className="text-sm text-foreground">{item.summary || item.memoryText}</div>
                          {item.title ? <div className="text-xs text-muted-foreground">{item.title}</div> : null}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="text-sm text-foreground">{item.memoryScope}</div>
                          <div className="text-xs text-muted-foreground">{item.tenantId}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="text-sm text-foreground">{item.writeSource}</div>
                          <div className="text-xs text-muted-foreground">{item.source || "--"}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="text-sm text-foreground">{formatDateTime(item.updatedAt || item.createdAt)}</div>
                          <div className="text-xs text-muted-foreground">{item.reviewStatus}</div>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!isLoading && items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                        当前筛选条件下暂无长期记忆记录
                      </TableCell>
                    </TableRow>
                  ) : null}
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                        正在加载长期记忆...
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>

            <div className="text-xs text-muted-foreground">
              {isFetching ? "正在同步最新结果..." : "这里只展示平台长期记忆，不展示会话短期上下文。"}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
