import type { WorkflowTrigger, WorkflowTriggerType } from "@/types"

type WorkflowTriggerOption = {
  value: WorkflowTriggerType
  label: string
  hint: string
  legacy?: boolean
}

const primaryTriggerOptions: WorkflowTriggerOption[] = [
  { value: "message", label: "消息触发", hint: "由客户消息或关键词命中当前工作流" },
  { value: "internal", label: "工作流触发", hint: "由上游工作流或系统流程继续触发当前工作流" },
]

const legacyTriggerOptions: WorkflowTriggerOption[] = [
  { value: "schedule", label: "定时触发", hint: "兼容历史定时工作流配置", legacy: true },
  { value: "webhook", label: "Webhook 触发", hint: "兼容历史外部回调工作流配置", legacy: true },
  { value: "manual", label: "手动触发", hint: "兼容历史控制台手动启动配置", legacy: true },
]

export function getWorkflowTriggerOptions(
  currentType?: WorkflowTriggerType,
): WorkflowTriggerOption[] {
  const options = [...primaryTriggerOptions]
  if (!currentType || primaryTriggerOptions.some((option) => option.value === currentType)) {
    return options
  }

  const matchedLegacy = legacyTriggerOptions.find((option) => option.value === currentType)
  return matchedLegacy ? options.concat(matchedLegacy) : options
}

export function getWorkflowTriggerTypeLabel(type?: string | null) {
  const normalized = String(type || "").trim().toLowerCase()
  const prefix = normalized.split(":")[0]
  if (prefix === "internal") return "工作流触发"
  if (prefix === "schedule") return "定时触发"
  if (prefix === "webhook") return "Webhook 触发"
  if (prefix === "manual") return "手动触发"
  return "消息触发"
}

export function getWorkflowTriggerValue(trigger: WorkflowTrigger) {
  switch (trigger.type) {
    case "message":
      return trigger.keyword ?? ""
    case "schedule":
      return trigger.cron ?? ""
    case "webhook":
      return trigger.webhookPath ?? ""
    case "internal":
      return trigger.internalEvent ?? ""
    case "manual":
      return trigger.description ?? ""
  }

  return ""
}

export function patchWorkflowTriggerValue(
  trigger: WorkflowTrigger,
  value: string,
): WorkflowTrigger {
  if (trigger.type === "message") {
    return { ...trigger, keyword: value }
  }
  if (trigger.type === "schedule") {
    return { ...trigger, cron: value }
  }
  if (trigger.type === "webhook") {
    return { ...trigger, webhookPath: value }
  }
  if (trigger.type === "internal") {
    return { ...trigger, internalEvent: value }
  }

  return { ...trigger, description: value }
}

export function getWorkflowTriggerFieldMeta(type: WorkflowTriggerType) {
  switch (type) {
    case "message":
      return {
        label: "消息关键词",
        placeholder: "例如：退款、开票、进度查询",
      }
    case "internal":
      return {
        label: "工作流触发标识",
        placeholder: "例如：order.review.completed",
      }
    case "schedule":
      return {
        label: "Cron 表达式",
        placeholder: "例如：0 * * * *",
      }
    case "webhook":
      return {
        label: "Webhook 路径",
        placeholder: "例如：/webhooks/customer-service",
      }
  }

  return {
    label: "触发说明",
    placeholder: "例如：由管理员手动发起运行",
  }
}

export function nextWorkflowTriggerByType(
  type: WorkflowTriggerType,
  current: WorkflowTrigger,
): WorkflowTrigger {
  return {
    type,
    keyword: type === "message" ? current.keyword ?? "" : null,
    cron: type === "schedule" ? current.cron ?? "" : null,
    webhookPath: type === "webhook" ? current.webhookPath ?? "" : null,
    internalEvent:
      type === "internal" ? current.internalEvent ?? current.description ?? "" : null,
    description:
      type === "internal"
        ? current.description ?? "由上游工作流或系统流程继续触发"
        : type === "manual"
          ? current.description ?? "由控制台手动启动"
          : current.description ?? "",
    priority: current.priority ?? 100,
    channels: current.channels ?? [],
    preferredLanguage: current.preferredLanguage ?? null,
    stepDelaySeconds: current.stepDelaySeconds ?? 0.6,
    maxDispatchRetry: current.maxDispatchRetry ?? 6,
    dispatchRetryBackoffSeconds: current.dispatchRetryBackoffSeconds ?? 2,
    executionTimeoutSeconds: current.executionTimeoutSeconds ?? 45,
    naturalLanguageRule: current.naturalLanguageRule ?? null,
    schedulePlan: current.schedulePlan ?? null,
  }
}
