"use client"

import { useMemo, useState } from "react"
import { RefreshCw, Save, Trash2 } from "lucide-react"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Checkbox } from "@/shared/ui/checkbox"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"
import { Textarea } from "@/shared/ui/textarea"
import {
  useDeleteProtocolBinding,
  useProtocolBindings,
  useUpsertProtocolBinding,
} from "@/modules/settings/hooks/use-settings"
import { toast } from "@/shared/hooks/use-toast"
import type {
  MemoryNamespaceStrategy,
  ProtocolBinding,
  ProtocolBindingDeleteRequest,
  ProtocolBindingUpsertRequest,
  RuntimeMemoryMode,
} from "@/shared/types"

type BindingDraft = {
  bindingId: string
  tenantId: string
  agentId: string
  protocolId: string
  protocolVersion: string
  targetProvider: string
  targetInstanceId: string
  targetBaseUrl: string
  runtimeMemoryMode: RuntimeMemoryMode
  memoryNamespaceStrategy: MemoryNamespaceStrategy
  enabled: boolean
  metadataText: string
}

const EMPTY_DRAFT: BindingDraft = {
  bindingId: "",
  tenantId: "",
  agentId: "",
  protocolId: "",
  protocolVersion: "v1",
  targetProvider: "hermes",
  targetInstanceId: "",
  targetBaseUrl: "",
  runtimeMemoryMode: "platform_stateless",
  memoryNamespaceStrategy: "tenant_customer",
  enabled: true,
  metadataText: "{}",
}

function toDraft(binding: ProtocolBinding): BindingDraft {
  return {
    bindingId: binding.bindingId,
    tenantId: binding.tenantId,
    agentId: binding.agentId,
    protocolId: binding.protocolId,
    protocolVersion: binding.protocolVersion,
    targetProvider: binding.targetProvider,
    targetInstanceId: binding.targetInstanceId ?? "",
    targetBaseUrl: binding.targetBaseUrl ?? "",
    runtimeMemoryMode: binding.runtimeMemoryMode,
    memoryNamespaceStrategy: binding.memoryNamespaceStrategy,
    enabled: binding.enabled,
    metadataText: JSON.stringify(binding.metadata ?? {}, null, 2),
  }
}

function parseMetadata(value: string): Record<string, unknown> {
  const raw = value.trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("metadata 必须是 JSON 对象。")
  }
  return parsed as Record<string, unknown>
}

function toUpsertPayload(draft: BindingDraft): ProtocolBindingUpsertRequest {
  return {
    bindingId: draft.bindingId.trim() || undefined,
    tenantId: draft.tenantId.trim(),
    agentId: draft.agentId.trim(),
    protocolId: draft.protocolId.trim(),
    protocolVersion: draft.protocolVersion.trim() || "v1",
    targetProvider: draft.targetProvider.trim() || "hermes",
    targetInstanceId: draft.targetInstanceId.trim() || undefined,
    targetBaseUrl: draft.targetBaseUrl.trim() || undefined,
    runtimeMemoryMode: draft.runtimeMemoryMode,
    memoryNamespaceStrategy: draft.memoryNamespaceStrategy,
    enabled: draft.enabled,
    metadata: parseMetadata(draft.metadataText),
  }
}

export default function TenantProtocolBindingsPage() {
  const [filters, setFilters] = useState({ tenantId: "", agentId: "" })
  const [draft, setDraft] = useState<BindingDraft>(EMPTY_DRAFT)
  const [activeBindingId, setActiveBindingId] = useState("")

  const bindingsQuery = useProtocolBindings(filters)
  const upsertMutation = useUpsertProtocolBinding(filters)
  const deleteMutation = useDeleteProtocolBinding(filters)
  const rows = bindingsQuery.data?.items ?? []

  const preview = useMemo(() => {
    return `${draft.tenantId || "-"} -> ${draft.targetProvider || "-"}:${draft.targetInstanceId || "-"} (${draft.agentId || "-"} / ${draft.protocolId || "-"}@${draft.protocolVersion || "-"})`
  }, [draft])

  const selectBinding = (binding: ProtocolBinding) => {
    setActiveBindingId(binding.bindingId)
    setDraft(toDraft(binding))
  }

  const resetDraft = () => {
    setActiveBindingId("")
    setDraft(EMPTY_DRAFT)
  }

  const saveBinding = async () => {
    try {
      if (!draft.tenantId.trim() || !draft.agentId.trim() || !draft.protocolId.trim()) {
        throw new Error("tenant_id、agent_id、protocol_id 为必填项。")
      }
      const payload = toUpsertPayload(draft)
      const response = await upsertMutation.mutateAsync(payload)
      const saved = response.binding
      setActiveBindingId(saved.bindingId)
      setDraft(toDraft(saved))
      toast({
        title: "协议绑定已保存",
        description: response.message,
      })
      await bindingsQuery.refetch()
    } catch (error) {
      toast({
        title: "保存失败",
        description: error instanceof Error ? error.message : "协议绑定更新失败。",
        variant: "destructive",
      })
    }
  }

  const deleteBindingBySelector = async (
    payload: ProtocolBindingDeleteRequest,
    resetBindingId?: string,
  ) => {
    const response = await deleteMutation.mutateAsync(payload)
    const deletedBindingId = response.binding.bindingId
    if (
      (resetBindingId && resetBindingId === deletedBindingId) ||
      activeBindingId === deletedBindingId
    ) {
      resetDraft()
    }
    toast({
      title: "协议绑定已删除",
      description: response.message,
    })
    await bindingsQuery.refetch()
  }

  const deleteBinding = async () => {
    const resolvedBindingId = activeBindingId.trim() || undefined
    const resolvedTenantId = draft.tenantId.trim() || undefined
    const resolvedAgentId = draft.agentId.trim() || undefined
    if (!resolvedBindingId && !(resolvedTenantId && resolvedAgentId)) {
      toast({
        title: "删除失败",
        description: "请先选择要删除的绑定，或填写 tenant_id 与 agent_id。",
        variant: "destructive",
      })
      return
    }

    try {
      await deleteBindingBySelector(
        {
          bindingId: resolvedBindingId,
          tenantId: resolvedTenantId,
          agentId: resolvedAgentId,
        },
        resolvedBindingId,
      )
    } catch (error) {
      toast({
        title: "删除失败",
        description: error instanceof Error ? error.message : "协议绑定删除失败。",
        variant: "destructive",
      })
    }
  }

  return (
    <div className="p-6">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle>租户协议绑定配置</CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" type="button" onClick={resetDraft}>
                  新建
                </Button>
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => bindingsQuery.refetch()}
                  disabled={bindingsQuery.isFetching}
                >
                  <RefreshCw className="mr-2 size-4" />
                  刷新
                </Button>
                <Button type="button" onClick={saveBinding} disabled={upsertMutation.isPending}>
                  <Save className="mr-2 size-4" />
                  保存
                </Button>
                <Button
                  variant="destructive"
                  type="button"
                  onClick={deleteBinding}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="mr-2 size-4" />
                  删除
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {bindingsQuery.error ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                协议绑定列表加载失败：
                {bindingsQuery.error instanceof Error ? bindingsQuery.error.message : "未知错误"}
              </div>
            ) : null}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="binding-tenant-id">tenant_id</Label>
                <Input
                  id="binding-tenant-id"
                  value={draft.tenantId}
                  onChange={(event) => setDraft((current) => ({ ...current, tenantId: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="binding-agent-id">agent_id</Label>
                <Input
                  id="binding-agent-id"
                  value={draft.agentId}
                  onChange={(event) => setDraft((current) => ({ ...current, agentId: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="binding-protocol-id">protocol_id</Label>
                <Input
                  id="binding-protocol-id"
                  value={draft.protocolId}
                  onChange={(event) => setDraft((current) => ({ ...current, protocolId: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="binding-protocol-version">protocol_version</Label>
                <Input
                  id="binding-protocol-version"
                  value={draft.protocolVersion}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, protocolVersion: event.target.value }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="binding-target-provider">target_provider</Label>
                <Input
                  id="binding-target-provider"
                  value={draft.targetProvider}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, targetProvider: event.target.value }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="binding-target-instance">target_instance_id</Label>
                <Input
                  id="binding-target-instance"
                  value={draft.targetInstanceId}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, targetInstanceId: event.target.value }))
                  }
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="binding-target-url">target_base_url</Label>
                <Input
                  id="binding-target-url"
                  value={draft.targetBaseUrl}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, targetBaseUrl: event.target.value }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>runtime_memory_mode</Label>
                <Select
                  value={draft.runtimeMemoryMode}
                  onValueChange={(value) =>
                    setDraft((current) => ({ ...current, runtimeMemoryMode: value as RuntimeMemoryMode }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="platform_stateless">platform_stateless</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>memory_namespace_strategy</Label>
                <Select
                  value={draft.memoryNamespaceStrategy}
                  onValueChange={(value) =>
                    setDraft((current) => ({
                      ...current,
                      memoryNamespaceStrategy: value as MemoryNamespaceStrategy,
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tenant_customer">tenant_customer</SelectItem>
                    <SelectItem value="tenant">tenant</SelectItem>
                    <SelectItem value="tenant_session">tenant_session</SelectItem>
                    <SelectItem value="tenant_task">tenant_task</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end gap-2">
                <Checkbox
                  id="binding-enabled"
                  checked={draft.enabled}
                  onCheckedChange={(checked) => setDraft((current) => ({ ...current, enabled: Boolean(checked) }))}
                />
                <Label htmlFor="binding-enabled">enabled</Label>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="binding-metadata">metadata（JSON 对象）</Label>
                <Textarea
                  id="binding-metadata"
                  value={draft.metadataText}
                  onChange={(event) => setDraft((current) => ({ ...current, metadataText: event.target.value }))}
                  className="min-h-28 font-mono text-xs"
                />
              </div>
            </div>

            <div className="rounded-lg border border-border bg-secondary/20 p-3 text-sm">
              <div className="font-medium text-foreground">绑定预览</div>
              <div className="mt-1 text-muted-foreground">{preview}</div>
              <div className="mt-1 text-muted-foreground">
                当前编辑：{activeBindingId ? activeBindingId : "新建绑定"}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle>已绑定租户</CardTitle>
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  value={filters.tenantId}
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, tenantId: event.target.value }))
                  }
                  placeholder="按 tenantId 过滤"
                />
                <Input
                  value={filters.agentId}
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, agentId: event.target.value }))
                  }
                  placeholder="按 agentId 过滤"
                />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>binding_id</TableHead>
                  <TableHead>tenant_id</TableHead>
                  <TableHead>agent_id</TableHead>
                  <TableHead>协议</TableHead>
                  <TableHead>目标</TableHead>
                  <TableHead>记忆策略</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.bindingId}
                    className="cursor-pointer"
                    data-state={activeBindingId === row.bindingId ? "selected" : undefined}
                    onClick={() => selectBinding(row)}
                  >
                    <TableCell className="font-mono text-xs">{row.bindingId}</TableCell>
                    <TableCell>{row.tenantId}</TableCell>
                    <TableCell>{row.agentId}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {row.protocolId}@{row.protocolVersion}
                      </Badge>
                    </TableCell>
                    <TableCell>{row.targetInstanceId || row.targetProvider}</TableCell>
                    <TableCell>{row.memoryNamespaceStrategy}</TableCell>
                    <TableCell>{row.enabled ? "enabled" : "disabled"}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        className="h-7 px-2 text-destructive hover:text-destructive"
                        onClick={(event) => {
                          event.stopPropagation()
                          setActiveBindingId(row.bindingId)
                          setDraft(toDraft(row))
                          void deleteBindingBySelector(
                            { bindingId: row.bindingId, tenantId: row.tenantId, agentId: row.agentId },
                            row.bindingId,
                          ).catch((error) => {
                            toast({
                              title: "删除失败",
                              description: error instanceof Error ? error.message : "协议绑定删除失败。",
                              variant: "destructive",
                            })
                          })
                        }}
                        disabled={deleteMutation.isPending}
                      >
                        删除
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-sm text-muted-foreground">
                      暂无绑定记录
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
