"use client"

import { useMemo, useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import {
  useRegisterToolMcp,
  useRegisterToolSkill,
  type RegisterMcpPayload,
  type RegisterSkillPayload,
} from "@/hooks/use-tool-sources"
import { toast } from "@/hooks/use-toast"

const HTTP_METHOD_OPTIONS = ["POST", "GET", "PUT", "PATCH", "DELETE"] as const

const initialSkillForm: RegisterSkillPayload = {
  name: "",
  description: "",
  version: "1.0.0",
  baseUrl: "",
  invokePath: "/invoke",
  healthPath: "/health",
  method: "POST",
  protocol: "http",
  enabled: true,
  timeoutSeconds: 8,
  tags: [],
  capabilities: [],
}

const initialMcpForm: RegisterMcpPayload = {
  name: "",
  description: "",
  baseUrl: "",
  invokePath: "/invoke",
  method: "POST",
  enabled: true,
  timeoutSeconds: 10,
  requiresPermission: false,
  approvalRequired: false,
  tags: [],
}

function parseCommaSeparated(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function normalizePath(value: string, fallback: string) {
  const trimmed = value.trim() || fallback
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`
}

function skillSubmitPayload(
  form: RegisterSkillPayload,
  tagsInput: string,
  capabilitiesInput: string,
): RegisterSkillPayload {
  return {
    ...form,
    name: form.name.trim(),
    id: form.id?.trim() || undefined,
    description: form.description?.trim() || undefined,
    skillFamily: form.skillFamily?.trim() || undefined,
    version: form.version?.trim() || "1.0.0",
    baseUrl: form.baseUrl.trim(),
    invokePath: normalizePath(form.invokePath || "", "/invoke"),
    healthPath: normalizePath(form.healthPath || "", "/health"),
    method: form.method?.trim().toUpperCase() || "POST",
    protocol: form.protocol?.trim() || "http",
    provider: form.provider?.trim() || undefined,
    timeoutSeconds: Number(form.timeoutSeconds || 8),
    tags: parseCommaSeparated(tagsInput),
    capabilities: parseCommaSeparated(capabilitiesInput),
  }
}

function mcpSubmitPayload(form: RegisterMcpPayload, tagsInput: string): RegisterMcpPayload {
  return {
    ...form,
    name: form.name.trim(),
    id: form.id?.trim() || undefined,
    description: form.description?.trim() || undefined,
    baseUrl: form.baseUrl.trim(),
    invokePath: normalizePath(form.invokePath || "", "/invoke"),
    method: form.method?.trim().toUpperCase() || "POST",
    provider: form.provider?.trim() || undefined,
    timeoutSeconds: Number(form.timeoutSeconds || 10),
    tags: parseCommaSeparated(tagsInput),
    approvalRequired: form.requiresPermission ? Boolean(form.approvalRequired) : false,
  }
}

export function ToolRegistrationActions() {
  const [skillDialogOpen, setSkillDialogOpen] = useState(false)
  const [mcpDialogOpen, setMcpDialogOpen] = useState(false)
  const [skillForm, setSkillForm] = useState<RegisterSkillPayload>(initialSkillForm)
  const [mcpForm, setMcpForm] = useState<RegisterMcpPayload>(initialMcpForm)
  const [skillTagsInput, setSkillTagsInput] = useState("")
  const [skillCapabilitiesInput, setSkillCapabilitiesInput] = useState("")
  const [mcpTagsInput, setMcpTagsInput] = useState("")
  const [skillError, setSkillError] = useState("")
  const [mcpError, setMcpError] = useState("")

  const registerSkill = useRegisterToolSkill()
  const registerMcp = useRegisterToolMcp()

  const skillPending = registerSkill.isPending
  const mcpPending = registerMcp.isPending
  const skillPreview = useMemo(
    () => skillSubmitPayload(skillForm, skillTagsInput, skillCapabilitiesInput),
    [skillCapabilitiesInput, skillForm, skillTagsInput],
  )
  const mcpPreview = useMemo(() => mcpSubmitPayload(mcpForm, mcpTagsInput), [mcpForm, mcpTagsInput])

  const resetSkillForm = () => {
    setSkillForm(initialSkillForm)
    setSkillTagsInput("")
    setSkillCapabilitiesInput("")
    setSkillError("")
  }

  const resetMcpForm = () => {
    setMcpForm(initialMcpForm)
    setMcpTagsInput("")
    setMcpError("")
  }

  const handleSubmitSkill = async () => {
    if (!skillPreview.name || !skillPreview.baseUrl) {
      setSkillError("请填写 Skill 名称和服务地址。")
      return
    }

    try {
      const response = await registerSkill.mutateAsync(skillPreview)
      toast({
        title: "Skill 已新增",
        description: response.message,
      })
      setSkillDialogOpen(false)
      resetSkillForm()
    } catch (error) {
      const message = error instanceof Error ? error.message : "Skill 新增失败"
      setSkillError(message)
      toast({
        title: "Skill 新增失败",
        description: message,
        variant: "destructive",
      })
    }
  }

  const handleSubmitMcp = async () => {
    if (!mcpPreview.name || !mcpPreview.baseUrl) {
      setMcpError("请填写 MCP 名称和服务地址。")
      return
    }

    try {
      const response = await registerMcp.mutateAsync(mcpPreview)
      toast({
        title: "MCP 已新增",
        description: response.message,
      })
      setMcpDialogOpen(false)
      resetMcpForm()
    } catch (error) {
      const message = error instanceof Error ? error.message : "MCP 新增失败"
      setMcpError(message)
      toast({
        title: "MCP 新增失败",
        description: message,
        variant: "destructive",
      })
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => {
            setSkillError("")
            setSkillDialogOpen(true)
          }}
        >
          <Plus className="mr-2 size-4" />
          新增 Skill
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => {
            setMcpError("")
            setMcpDialogOpen(true)
          }}
        >
          <Plus className="mr-2 size-4" />
          新增 MCP
        </Button>
      </div>

      <Dialog
        open={skillDialogOpen}
        onOpenChange={(open) => {
          if (skillPending) return
          setSkillDialogOpen(open)
          if (!open) {
            resetSkillForm()
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>新增 Skill</DialogTitle>
            <DialogDescription>将新的外接 Skill 接入到外部触手目录。</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="skill-name">Skill 名称</Label>
              <Input
                id="skill-name"
                value={skillForm.name ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="例如：合同审查"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-id">Skill ID</Label>
              <Input
                id="skill-id"
                value={skillForm.id ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, id: event.target.value }))}
                placeholder="留空自动生成"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-base-url">服务地址</Label>
              <Input
                id="skill-base-url"
                value={skillForm.baseUrl ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, baseUrl: event.target.value }))}
                placeholder="https://skills.example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-version">版本</Label>
              <Input
                id="skill-version"
                value={skillForm.version ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, version: event.target.value }))}
                placeholder="1.0.0"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-invoke-path">调用路径</Label>
              <Input
                id="skill-invoke-path"
                value={skillForm.invokePath ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, invokePath: event.target.value }))}
                placeholder="/invoke"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-health-path">健康检查路径</Label>
              <Input
                id="skill-health-path"
                value={skillForm.healthPath ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, healthPath: event.target.value }))}
                placeholder="/health"
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
              <Label htmlFor="skill-timeout">超时时间（秒）</Label>
              <Input
                id="skill-timeout"
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
              <Label htmlFor="skill-family">Skill 族</Label>
              <Input
                id="skill-family"
                value={skillForm.skillFamily ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, skillFamily: event.target.value }))}
                placeholder="留空默认使用名称"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-provider">接入标识</Label>
              <Input
                id="skill-provider"
                value={skillForm.provider ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, provider: event.target.value }))}
                placeholder="external-skill-http"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-tags">标签</Label>
              <Input
                id="skill-tags"
                value={skillTagsInput}
                onChange={(event) => setSkillTagsInput(event.target.value)}
                placeholder="legal, review"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-capabilities">能力点</Label>
              <Input
                id="skill-capabilities"
                value={skillCapabilitiesInput}
                onChange={(event) => setSkillCapabilitiesInput(event.target.value)}
                placeholder="contract_review, risk_scan"
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="skill-description">说明</Label>
              <Textarea
                id="skill-description"
                value={skillForm.description ?? ""}
                onChange={(event) => setSkillForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="说明这个 Skill 主要负责什么。"
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 sm:col-span-2">
              <div>
                <div className="text-sm font-medium text-foreground">新增后立即启用</div>
                <div className="text-xs text-muted-foreground">关闭后会写入目录，但默认不参与调度。</div>
              </div>
              <Switch
                checked={Boolean(skillForm.enabled)}
                onCheckedChange={(checked) => setSkillForm((current) => ({ ...current, enabled: checked }))}
              />
            </div>
          </div>

          {skillError ? <div className="text-sm text-destructive">{skillError}</div> : null}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setSkillDialogOpen(false)
                resetSkillForm()
              }}
              disabled={skillPending}
            >
              取消
            </Button>
            <Button onClick={() => void handleSubmitSkill()} disabled={skillPending}>
              {skillPending ? "新增中..." : "确认新增"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={mcpDialogOpen}
        onOpenChange={(open) => {
          if (mcpPending) return
          setMcpDialogOpen(open)
          if (!open) {
            resetMcpForm()
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>新增 MCP</DialogTitle>
            <DialogDescription>将新的 MCP 服务能力接入到外部触手目录。</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="mcp-name">MCP 名称</Label>
              <Input
                id="mcp-name"
                value={mcpForm.name ?? ""}
                onChange={(event) => setMcpForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="例如：crm_lookup"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-id">MCP ID</Label>
              <Input
                id="mcp-id"
                value={mcpForm.id ?? ""}
                onChange={(event) => setMcpForm((current) => ({ ...current, id: event.target.value }))}
                placeholder="留空自动生成"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-base-url">服务地址</Label>
              <Input
                id="mcp-base-url"
                value={mcpForm.baseUrl ?? ""}
                onChange={(event) => setMcpForm((current) => ({ ...current, baseUrl: event.target.value }))}
                placeholder="https://mcp.example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-provider">接入标识</Label>
              <Input
                id="mcp-provider"
                value={mcpForm.provider ?? ""}
                onChange={(event) => setMcpForm((current) => ({ ...current, provider: event.target.value }))}
                placeholder="mcp-http"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-invoke-path">调用路径</Label>
              <Input
                id="mcp-invoke-path"
                value={mcpForm.invokePath ?? ""}
                onChange={(event) => setMcpForm((current) => ({ ...current, invokePath: event.target.value }))}
                placeholder="/invoke"
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
              <Label htmlFor="mcp-timeout">超时时间（秒）</Label>
              <Input
                id="mcp-timeout"
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
            <div className="space-y-2">
              <Label htmlFor="mcp-tags">标签</Label>
              <Input
                id="mcp-tags"
                value={mcpTagsInput}
                onChange={(event) => setMcpTagsInput(event.target.value)}
                placeholder="crm, lookup"
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="mcp-description">说明</Label>
              <Textarea
                id="mcp-description"
                value={mcpForm.description ?? ""}
                onChange={(event) => setMcpForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="说明这个 MCP 能处理什么请求。"
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <div>
                <div className="text-sm font-medium text-foreground">新增后立即启用</div>
                <div className="text-xs text-muted-foreground">关闭后会写入目录，但默认不参与调度。</div>
              </div>
              <Switch
                checked={Boolean(mcpForm.enabled)}
                onCheckedChange={(checked) => setMcpForm((current) => ({ ...current, enabled: checked }))}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <div>
                <div className="text-sm font-medium text-foreground">需要权限控制</div>
                <div className="text-xs text-muted-foreground">敏感接口建议开启，便于后续纳入审批流。</div>
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

          {mcpError ? <div className="text-sm text-destructive">{mcpError}</div> : null}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setMcpDialogOpen(false)
                resetMcpForm()
              }}
              disabled={mcpPending}
            >
              取消
            </Button>
            <Button onClick={() => void handleSubmitMcp()} disabled={mcpPending}>
              {mcpPending ? "新增中..." : "确认新增"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
