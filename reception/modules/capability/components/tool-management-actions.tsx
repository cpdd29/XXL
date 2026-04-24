"use client"

import { useState } from "react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/ui/alert-dialog"
import { Button } from "@/shared/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog"
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
import { Textarea } from "@/shared/ui/textarea"
import {
  useDeleteManagedTool,
  useUpdateToolMcp,
  useUpdateToolSkill,
  type RegisterMcpPayload,
  type RegisterSkillPayload,
} from "@/modules/capability/hooks/use-tool-sources"
import { toast } from "@/shared/hooks/use-toast"
import type { Tool } from "@/shared/types"

const HTTP_METHOD_OPTIONS = ["POST", "GET", "PUT", "PATCH", "DELETE"] as const

function getConfigString(config: Record<string, unknown> | null, keys: string[], fallback = "") {
  if (!config) return fallback
  for (const key of keys) {
    const value = config[key]
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return fallback
}

function getConfigNumber(config: Record<string, unknown> | null, keys: string[], fallback: number) {
  if (!config) return fallback
  for (const key of keys) {
    const value = config[key]
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return fallback
}

function parseCommaSeparated(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function buildSkillPayload(tool: Tool): RegisterSkillPayload {
  return {
    name: tool.name,
    description: tool.description,
    skillFamily: getConfigString(tool.configDetail, ["skill_family", "skillFamily"], tool.name),
    version: getConfigString(tool.configDetail, ["version"], "1.0.0"),
    baseUrl: getConfigString(tool.configDetail, ["base_url", "baseUrl"]),
    invokePath: getConfigString(tool.configDetail, ["invoke_path", "invokePath"], "/invoke"),
    healthPath: getConfigString(tool.configDetail, ["health_path", "healthPath"], "/health"),
    method: getConfigString(tool.configDetail, ["http_method", "httpMethod"], "POST"),
    protocol: getConfigString(tool.configDetail, ["protocol"], "http"),
    provider: typeof tool.configDetail?.provider === "string" ? tool.configDetail.provider : tool.providerSummary,
    enabled: tool.enabled,
    timeoutSeconds: getConfigNumber(tool.configDetail, ["timeout_seconds", "timeoutSeconds"], 8),
    tags: tool.tags,
    capabilities: tool.requiredCapabilities,
    sourceId: tool.sourceId ?? undefined,
    sourceName: tool.sourceName,
  }
}

function buildMcpPayload(tool: Tool): RegisterMcpPayload {
  return {
    name: tool.name,
    description: tool.description,
    baseUrl: getConfigString(tool.configDetail, ["base_url", "baseUrl"]),
    invokePath: getConfigString(tool.configDetail, ["invoke_path", "invokePath"], "/invoke"),
    method: getConfigString(tool.configDetail, ["http_method", "httpMethod"], "POST"),
    provider: typeof tool.configDetail?.provider === "string" ? tool.configDetail.provider : tool.providerSummary,
    enabled: tool.enabled,
    timeoutSeconds: getConfigNumber(tool.configDetail, ["timeout_seconds", "timeoutSeconds"], 10),
    requiresPermission: tool.permissions.requiresPermission,
    approvalRequired: tool.permissions.approvalRequired,
    tags: tool.tags,
    scopes: tool.permissions.scopes,
    roles: tool.permissions.roles,
    sourceId: tool.sourceId ?? undefined,
    sourceName: tool.sourceName,
  }
}

function managedRegistrationKind(tool: Tool) {
  return getConfigString(tool.configDetail, ["registration_kind", "registrationKind"])
}

export function isControlPlaneManagedTool(tool: Tool) {
  const registrationKind = managedRegistrationKind(tool)
  return registrationKind === "control_plane_skill" || registrationKind === "control_plane_mcp"
}

export function ToolManagementActions({
  tool,
  onDeleted,
}: {
  tool: Tool
  onDeleted?: (toolId: string) => void
}) {
  const registrationKind = managedRegistrationKind(tool)
  const managedType =
    registrationKind === "control_plane_skill"
      ? "skill"
      : registrationKind === "control_plane_mcp"
        ? "mcp"
        : null
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [errorMessage, setErrorMessage] = useState("")
  const [skillForm, setSkillForm] = useState<RegisterSkillPayload>(buildSkillPayload(tool))
  const [mcpForm, setMcpForm] = useState<RegisterMcpPayload>(buildMcpPayload(tool))
  const [skillTagsInput, setSkillTagsInput] = useState(tool.tags.join(", "))
  const [skillCapabilitiesInput, setSkillCapabilitiesInput] = useState(tool.requiredCapabilities.join(", "))
  const [mcpTagsInput, setMcpTagsInput] = useState(tool.tags.join(", "))

  const updateSkill = useUpdateToolSkill()
  const updateMcp = useUpdateToolMcp()
  const deleteManagedTool = useDeleteManagedTool()

  if (!managedType) return null

  const isPending = updateSkill.isPending || updateMcp.isPending || deleteManagedTool.isPending

  const resetState = () => {
    setErrorMessage("")
    setSkillForm(buildSkillPayload(tool))
    setMcpForm(buildMcpPayload(tool))
    setSkillTagsInput(tool.tags.join(", "))
    setSkillCapabilitiesInput(tool.requiredCapabilities.join(", "))
    setMcpTagsInput(tool.tags.join(", "))
  }

  const handleOpenEdit = () => {
    resetState()
    setEditOpen(true)
  }

  const handleSubmitSkill = async () => {
    const payload: RegisterSkillPayload = {
      ...skillForm,
      name: skillForm.name?.trim() ?? "",
      description: skillForm.description?.trim() || undefined,
      skillFamily: skillForm.skillFamily?.trim() || undefined,
      version: skillForm.version?.trim() || "1.0.0",
      baseUrl: skillForm.baseUrl?.trim() ?? "",
      invokePath: skillForm.invokePath?.trim() || "/invoke",
      healthPath: skillForm.healthPath?.trim() || "/health",
      method: skillForm.method?.trim().toUpperCase() || "POST",
      protocol: skillForm.protocol?.trim() || "http",
      provider: skillForm.provider?.trim() || undefined,
      timeoutSeconds: Number(skillForm.timeoutSeconds || 8),
      tags: parseCommaSeparated(skillTagsInput),
      capabilities: parseCommaSeparated(skillCapabilitiesInput),
      sourceId: tool.sourceId ?? undefined,
      sourceName: tool.sourceName,
    }

    if (!payload.name || !payload.baseUrl) {
      setErrorMessage("请填写 Skill 名称和服务地址。")
      return
    }

    try {
      const response = await updateSkill.mutateAsync({ toolId: tool.id, payload })
      toast({
        title: "Skill 已更新",
        description: response.message,
      })
      setEditOpen(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Skill 更新失败"
      setErrorMessage(message)
      toast({
        title: "Skill 更新失败",
        description: message,
        variant: "destructive",
      })
    }
  }

  const handleSubmitMcp = async () => {
    const payload: RegisterMcpPayload = {
      ...mcpForm,
      name: mcpForm.name?.trim() ?? "",
      description: mcpForm.description?.trim() || undefined,
      baseUrl: mcpForm.baseUrl?.trim() ?? "",
      invokePath: mcpForm.invokePath?.trim() || "/invoke",
      method: mcpForm.method?.trim().toUpperCase() || "POST",
      provider: mcpForm.provider?.trim() || undefined,
      timeoutSeconds: Number(mcpForm.timeoutSeconds || 10),
      tags: parseCommaSeparated(mcpTagsInput),
      approvalRequired: mcpForm.requiresPermission ? Boolean(mcpForm.approvalRequired) : false,
      sourceId: tool.sourceId ?? undefined,
      sourceName: tool.sourceName,
    }

    if (!payload.name || !payload.baseUrl) {
      setErrorMessage("请填写 MCP 名称和服务地址。")
      return
    }

    try {
      const response = await updateMcp.mutateAsync({ toolId: tool.id, payload })
      toast({
        title: "MCP 已更新",
        description: response.message,
      })
      setEditOpen(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : "MCP 更新失败"
      setErrorMessage(message)
      toast({
        title: "MCP 更新失败",
        description: message,
        variant: "destructive",
      })
    }
  }

  const handleDelete = async () => {
    try {
      const response = await deleteManagedTool.mutateAsync(tool.id)
      toast({
        title: "能力已删除",
        description: response.message,
      })
      setDeleteOpen(false)
      onDeleted?.(tool.id)
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除失败"
      toast({
        title: "删除失败",
        description: message,
        variant: "destructive",
      })
    }
  }

  return (
    <>
      <div className="flex items-center gap-1">
        <Button variant="secondary" size="sm" className="h-7 px-2 text-xs" onClick={handleOpenEdit}>
          编辑
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs text-destructive hover:text-destructive"
          onClick={() => setDeleteOpen(true)}
        >
          删除
        </Button>
      </div>

      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          if (isPending) return
          setEditOpen(open)
          if (open) {
            resetState()
          } else {
            setErrorMessage("")
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{managedType === "skill" ? "编辑 Skill" : "编辑 MCP"}</DialogTitle>
            <DialogDescription>更新当前能力的接入信息与启用状态。</DialogDescription>
          </DialogHeader>

          {managedType === "skill" ? (
            <div className="grid gap-4 py-2 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`skill-tool-id-${tool.id}`}>能力 ID</Label>
                <Input id={`skill-tool-id-${tool.id}`} value={tool.id} disabled />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-name-${tool.id}`}>Skill 名称</Label>
                <Input
                  id={`skill-name-${tool.id}`}
                  value={skillForm.name ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, name: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-base-url-${tool.id}`}>服务地址</Label>
                <Input
                  id={`skill-base-url-${tool.id}`}
                  value={skillForm.baseUrl ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, baseUrl: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-version-${tool.id}`}>版本</Label>
                <Input
                  id={`skill-version-${tool.id}`}
                  value={skillForm.version ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, version: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-invoke-path-${tool.id}`}>调用路径</Label>
                <Input
                  id={`skill-invoke-path-${tool.id}`}
                  value={skillForm.invokePath ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, invokePath: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-health-path-${tool.id}`}>健康检查路径</Label>
                <Input
                  id={`skill-health-path-${tool.id}`}
                  value={skillForm.healthPath ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, healthPath: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>调用方法</Label>
                <Select
                  value={skillForm.method ?? "POST"}
                  onValueChange={(value) => setSkillForm((current) => ({ ...current, method: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择方法" />
                  </SelectTrigger>
                  <SelectContent>
                    {HTTP_METHOD_OPTIONS.map((method) => (
                      <SelectItem key={method} value={method}>
                        {method}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-timeout-${tool.id}`}>超时时间（秒）</Label>
                <Input
                  id={`skill-timeout-${tool.id}`}
                  type="number"
                  min="1"
                  step="1"
                  value={skillForm.timeoutSeconds ?? 8}
                  onChange={(event) =>
                    setSkillForm((current) => ({
                      ...current,
                      timeoutSeconds: Number(event.target.value || 8),
                    }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-family-${tool.id}`}>Skill 族</Label>
                <Input
                  id={`skill-family-${tool.id}`}
                  value={skillForm.skillFamily ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, skillFamily: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-provider-${tool.id}`}>接入标识</Label>
                <Input
                  id={`skill-provider-${tool.id}`}
                  value={skillForm.provider ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, provider: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-tags-${tool.id}`}>标签</Label>
                <Input
                  id={`skill-tags-${tool.id}`}
                  value={skillTagsInput}
                  onChange={(event) => setSkillTagsInput(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`skill-capabilities-${tool.id}`}>能力点</Label>
                <Input
                  id={`skill-capabilities-${tool.id}`}
                  value={skillCapabilitiesInput}
                  onChange={(event) => setSkillCapabilitiesInput(event.target.value)}
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor={`skill-description-${tool.id}`}>说明</Label>
                <Textarea
                  id={`skill-description-${tool.id}`}
                  value={skillForm.description ?? ""}
                  onChange={(event) => setSkillForm((current) => ({ ...current, description: event.target.value }))}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 sm:col-span-2">
                <div>
                  <div className="text-sm font-medium text-foreground">保持启用</div>
                  <div className="text-xs text-muted-foreground">关闭后仍保留接入记录，但不会参与调度。</div>
                </div>
                <Switch
                  checked={Boolean(skillForm.enabled)}
                  onCheckedChange={(checked) => setSkillForm((current) => ({ ...current, enabled: checked }))}
                />
              </div>
            </div>
          ) : (
            <div className="grid gap-4 py-2 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`mcp-tool-id-${tool.id}`}>能力 ID</Label>
                <Input id={`mcp-tool-id-${tool.id}`} value={tool.id} disabled />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`mcp-name-${tool.id}`}>MCP 名称</Label>
                <Input
                  id={`mcp-name-${tool.id}`}
                  value={mcpForm.name ?? ""}
                  onChange={(event) => setMcpForm((current) => ({ ...current, name: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`mcp-base-url-${tool.id}`}>服务地址</Label>
                <Input
                  id={`mcp-base-url-${tool.id}`}
                  value={mcpForm.baseUrl ?? ""}
                  onChange={(event) => setMcpForm((current) => ({ ...current, baseUrl: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`mcp-provider-${tool.id}`}>接入标识</Label>
                <Input
                  id={`mcp-provider-${tool.id}`}
                  value={mcpForm.provider ?? ""}
                  onChange={(event) => setMcpForm((current) => ({ ...current, provider: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`mcp-invoke-path-${tool.id}`}>调用路径</Label>
                <Input
                  id={`mcp-invoke-path-${tool.id}`}
                  value={mcpForm.invokePath ?? ""}
                  onChange={(event) => setMcpForm((current) => ({ ...current, invokePath: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>调用方法</Label>
                <Select
                  value={mcpForm.method ?? "POST"}
                  onValueChange={(value) => setMcpForm((current) => ({ ...current, method: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择方法" />
                  </SelectTrigger>
                  <SelectContent>
                    {HTTP_METHOD_OPTIONS.map((method) => (
                      <SelectItem key={method} value={method}>
                        {method}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor={`mcp-timeout-${tool.id}`}>超时时间（秒）</Label>
                <Input
                  id={`mcp-timeout-${tool.id}`}
                  type="number"
                  min="1"
                  step="1"
                  value={mcpForm.timeoutSeconds ?? 10}
                  onChange={(event) =>
                    setMcpForm((current) => ({
                      ...current,
                      timeoutSeconds: Number(event.target.value || 10),
                    }))
                  }
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor={`mcp-tags-${tool.id}`}>标签</Label>
                <Input
                  id={`mcp-tags-${tool.id}`}
                  value={mcpTagsInput}
                  onChange={(event) => setMcpTagsInput(event.target.value)}
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor={`mcp-description-${tool.id}`}>说明</Label>
                <Textarea
                  id={`mcp-description-${tool.id}`}
                  value={mcpForm.description ?? ""}
                  onChange={(event) => setMcpForm((current) => ({ ...current, description: event.target.value }))}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                <div>
                  <div className="text-sm font-medium text-foreground">保持启用</div>
                  <div className="text-xs text-muted-foreground">关闭后仍保留接入记录，但不会参与调度。</div>
                </div>
                <Switch
                  checked={Boolean(mcpForm.enabled)}
                  onCheckedChange={(checked) => setMcpForm((current) => ({ ...current, enabled: checked }))}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                <div>
                  <div className="text-sm font-medium text-foreground">需要权限控制</div>
                  <div className="text-xs text-muted-foreground">敏感接口建议开启。</div>
                </div>
                <Switch
                  checked={Boolean(mcpForm.requiresPermission)}
                  onCheckedChange={(checked) =>
                    setMcpForm((current) => ({
                      ...current,
                      requiresPermission: checked,
                      approvalRequired: checked ? current.approvalRequired : false,
                    }))
                  }
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 sm:col-span-2">
                <div>
                  <div className="text-sm font-medium text-foreground">需要人工审批</div>
                  <div className="text-xs text-muted-foreground">仅在开启权限控制时生效。</div>
                </div>
                <Switch
                  checked={Boolean(mcpForm.approvalRequired)}
                  onCheckedChange={(checked) => setMcpForm((current) => ({ ...current, approvalRequired: checked }))}
                  disabled={!mcpForm.requiresPermission}
                />
              </div>
            </div>
          )}

          {errorMessage ? <div className="text-sm text-destructive">{errorMessage}</div> : null}

          <DialogFooter>
            <Button variant="outline" disabled={isPending} onClick={() => setEditOpen(false)}>
              取消
            </Button>
            <Button disabled={isPending} onClick={() => void (managedType === "skill" ? handleSubmitSkill() : handleSubmitMcp())}>
              {isPending ? "保存中..." : "保存修改"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteOpen} onOpenChange={(open) => !deleteManagedTool.isPending && setDeleteOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除这个能力？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后，这个 {managedType === "skill" ? "Skill" : "MCP"} 会从外部触手目录中移除，
              当前页面刷新后将不再展示。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteManagedTool.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={deleteManagedTool.isPending}
              onClick={(event) => {
                event.preventDefault()
                void handleDelete()
              }}
            >
              {deleteManagedTool.isPending ? "删除中..." : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
