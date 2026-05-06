"use client"

import { useEffect, useState } from "react"
import { Plus, Save, Trash2 } from "lucide-react"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Checkbox } from "@/shared/ui/checkbox"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Textarea } from "@/shared/ui/textarea"
import {
  useCustomerAccessSettings,
  useUpdateCustomerAccessSettings,
} from "@/modules/settings/hooks/use-settings"
import { toast } from "@/shared/hooks/use-toast"
import type {
  CustomerAccessTenantPolicy,
  CustomerAccessVerificationMode,
  UpdateCustomerAccessTenantPolicyRequest,
} from "@/shared/types"

type TenantPolicyDraft = {
  tenantId: string
  tenantName: string
  verificationMode: CustomerAccessVerificationMode
  serviceCodesText: string
  enabled: boolean
}

const EMPTY_POLICY: TenantPolicyDraft = {
  tenantId: "",
  tenantName: "",
  verificationMode: "relaxed",
  serviceCodesText: "",
  enabled: true,
}

function formatTimestamp(value?: string | null) {
  if (!value) return "--"
  return value.replace("T", " ").replace("Z", "").slice(0, 19)
}

function toPolicyDraft(policy: CustomerAccessTenantPolicy): TenantPolicyDraft {
  return {
    tenantId: policy.tenantId,
    tenantName: policy.tenantName ?? "",
    verificationMode: policy.verificationMode,
    serviceCodesText: policy.serviceCodes.join(", "),
    enabled: policy.enabled,
  }
}

function parseServiceCodes(value: string) {
  const seen = new Set<string>()
  return value
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item) return false
      const key = item.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

function toPolicyPayload(draft: TenantPolicyDraft): UpdateCustomerAccessTenantPolicyRequest | null {
  const tenantId = draft.tenantId.trim()
  if (!tenantId) return null
  return {
    tenantId,
    tenantName: draft.tenantName.trim() || undefined,
    verificationMode: draft.verificationMode,
    serviceCodes: parseServiceCodes(draft.serviceCodesText),
    enabled: draft.enabled,
  }
}

function isDefinedPolicy(
  value: UpdateCustomerAccessTenantPolicyRequest | null,
): value is UpdateCustomerAccessTenantPolicyRequest {
  return value !== null
}

export default function CustomerAdmissionTemplatePage() {
  const settingsQuery = useCustomerAccessSettings()
  const updateMutation = useUpdateCustomerAccessSettings()
  const [templateIntro, setTemplateIntro] = useState("")
  const [policies, setPolicies] = useState<TenantPolicyDraft[]>([])

  const settings = settingsQuery.data?.settings

  useEffect(() => {
    if (!settings) return
    setTemplateIntro(settings.templateIntro)
    setPolicies(settings.tenantPolicies.map(toPolicyDraft))
  }, [settings])

  const saveSettings = async () => {
    const tenantPolicies = policies.map(toPolicyPayload).filter(isDefinedPolicy)
    try {
      const response = await updateMutation.mutateAsync({
        templateIntro: templateIntro.trim(),
        tenantPolicies,
      })
      setTemplateIntro(response.settings.templateIntro)
      setPolicies(response.settings.tenantPolicies.map(toPolicyDraft))
      toast({
        title: "客户准入配置已保存",
        description: response.message,
      })
    } catch (error) {
      toast({
        title: "保存失败",
        description: error instanceof Error ? error.message : "客户准入配置更新失败。",
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
              <CardTitle>客户准入模板配置</CardTitle>
              <div className="text-xs text-muted-foreground">
                最近更新时间：{formatTimestamp(settings?.updatedAt)}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {settingsQuery.error ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                客户准入配置加载失败：
                {settingsQuery.error instanceof Error ? settingsQuery.error.message : "未知错误"}
              </div>
            ) : null}

            <div className="space-y-2">
              <Label htmlFor="admission-template-intro">模板引导文案</Label>
              <Textarea
                id="admission-template-intro"
                value={templateIntro}
                onChange={(event) => setTemplateIntro(event.target.value)}
                className="min-h-36"
                placeholder="请输入客户准入模板引导文案"
              />
            </div>

            <div className="space-y-2">
              <Label>系统内置模板字段（只读）</Label>
              <div className="rounded-lg border border-border p-3">
                <div className="flex flex-wrap gap-2">
                  {(settings?.templateFields ?? []).map((field) => (
                    <Badge key={field.key} variant="secondary">
                      {field.label} ({field.key}){field.required ? " *" : ""}
                    </Badge>
                  ))}
                  {(settings?.templateFields ?? []).length === 0 ? (
                    <span className="text-sm text-muted-foreground">暂无字段</span>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>租户准入策略</Label>
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => setPolicies((current) => [...current, { ...EMPTY_POLICY }])}
                >
                  <Plus className="mr-2 size-4" />
                  添加策略
                </Button>
              </div>
              {policies.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
                  暂无租户策略，保存后将按默认逻辑执行客户准入。
                </div>
              ) : null}
              {policies.map((policy, index) => (
                <div key={`policy-${index}`} className="space-y-3 rounded-lg border border-border p-3">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label>tenant_id</Label>
                      <Input
                        value={policy.tenantId}
                        onChange={(event) =>
                          setPolicies((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, tenantId: event.target.value } : item,
                            ),
                          )
                        }
                        placeholder="tenant_acme"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>tenant_name（可选）</Label>
                      <Input
                        value={policy.tenantName}
                        onChange={(event) =>
                          setPolicies((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, tenantName: event.target.value } : item,
                            ),
                          )
                        }
                        placeholder="Acme Corp"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>verification_mode</Label>
                      <Select
                        value={policy.verificationMode}
                        onValueChange={(value) =>
                          setPolicies((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, verificationMode: value as CustomerAccessVerificationMode }
                                : item,
                            ),
                          )
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="选择校验模式" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="relaxed">relaxed</SelectItem>
                          <SelectItem value="strict">strict</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-end gap-2">
                      <Checkbox
                        id={`policy-enabled-${index}`}
                        checked={policy.enabled}
                        onCheckedChange={(checked) =>
                          setPolicies((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, enabled: Boolean(checked) } : item,
                            ),
                          )
                        }
                      />
                      <Label htmlFor={`policy-enabled-${index}`}>启用策略</Label>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>service_codes（逗号或换行分隔）</Label>
                    <Textarea
                      value={policy.serviceCodesText}
                      onChange={(event) =>
                        setPolicies((current) =>
                          current.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, serviceCodesText: event.target.value } : item,
                          ),
                        )
                      }
                      placeholder="SC-001, SC-002"
                      className="min-h-20"
                    />
                  </div>
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      onClick={() =>
                        setPolicies((current) => current.filter((_, itemIndex) => itemIndex !== index))
                      }
                    >
                      <Trash2 className="mr-2 size-4" />
                      删除策略
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end">
              <Button onClick={saveSettings} disabled={updateMutation.isPending || settingsQuery.isLoading}>
                <Save className="mr-2 size-4" />
                保存配置
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
