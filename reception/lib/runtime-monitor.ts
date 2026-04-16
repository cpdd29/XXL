import type { RuntimeAlert, RuntimeQueueSnapshot } from "@/types"

export type RuntimeQueueFocus =
  | "all"
  | "non_zero"
  | "active_risk"
  | "active_leases"
  | "retry_backlog"
  | "dead_letters"

export type RuntimeAlertSeverityFilter = "all" | "critical" | "warning"

function normalizeSearch(value: string | null | undefined) {
  return String(value || "").trim().toLowerCase()
}

function includesSearch(values: Array<string | null | undefined>, search: string) {
  if (!search) return true
  return values.some((value) => normalizeSearch(value).includes(search))
}

function queueHasNonZeroActivity(queue: RuntimeQueueSnapshot) {
  return (
    queue.depth > 0 ||
    queue.ready > 0 ||
    queue.delayed > 0 ||
    queue.activeLeases > 0 ||
    queue.staleClaims > 0 ||
    queue.retryScheduled > 0 ||
    queue.deadLetters > 0
  )
}

export function runtimeQueueRiskState(queue: RuntimeQueueSnapshot): "healthy" | "warning" | "critical" {
  if (queue.deadLetters > 0 || queue.staleClaims > 0) return "critical"
  if (queue.retryScheduled > 0 || queue.delayed > 0 || queue.activeLeases > 0) return "warning"
  return "healthy"
}

export function runtimeQueueRiskScore(queue: RuntimeQueueSnapshot) {
  return (
    queue.deadLetters * 40 +
    queue.staleClaims * 30 +
    queue.retryScheduled * 18 +
    queue.delayed * 12 +
    queue.activeLeases * 8 +
    queue.ready * 4 +
    queue.depth * 2
  )
}

export function filterRuntimeQueues(
  queues: RuntimeQueueSnapshot[],
  {
    search,
    focus,
  }: {
    search?: string
    focus?: RuntimeQueueFocus
  },
) {
  const normalizedSearch = normalizeSearch(search)
  const resolvedFocus = focus ?? "all"

  return [...queues]
    .filter((queue) => {
      if (
        !includesSearch(
          [queue.label, queue.key],
          normalizedSearch,
        )
      ) {
        return false
      }

      switch (resolvedFocus) {
        case "non_zero":
          return queueHasNonZeroActivity(queue)
        case "active_risk":
          return queue.deadLetters > 0 || queue.staleClaims > 0 || queue.retryScheduled > 0
        case "active_leases":
          return queue.activeLeases > 0 || queue.staleClaims > 0
        case "retry_backlog":
          return queue.retryScheduled > 0 || queue.delayed > 0
        case "dead_letters":
          return queue.deadLetters > 0
        case "all":
        default:
          return true
      }
    })
    .sort((left, right) => {
      const riskDiff = runtimeQueueRiskScore(right) - runtimeQueueRiskScore(left)
      if (riskDiff !== 0) return riskDiff
      const depthDiff = right.depth - left.depth
      if (depthDiff !== 0) return depthDiff
      return left.label.localeCompare(right.label, "zh-CN")
    })
}

export function summarizeRuntimeQueues(queues: RuntimeQueueSnapshot[]) {
  return {
    total: queues.length,
    nonZero: queues.filter(queueHasNonZeroActivity).length,
    critical: queues.filter((queue) => runtimeQueueRiskState(queue) === "critical").length,
    warning: queues.filter((queue) => runtimeQueueRiskState(queue) === "warning").length,
    leaseHotspots: queues.filter((queue) => queue.activeLeases > 0 || queue.staleClaims > 0).length,
    retryHotspots: queues.filter((queue) => queue.retryScheduled > 0 || queue.delayed > 0).length,
    deadLetterHotspots: queues.filter((queue) => queue.deadLetters > 0).length,
  }
}

export function collectRuntimeAlertSources(alerts: RuntimeAlert[]) {
  return Array.from(
    new Set(
      alerts
        .map((alert) => String(alert.source || "").trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right, "zh-CN"))
}

function runtimeAlertPriority(alert: RuntimeAlert) {
  const severity = String(alert.severity || "").trim().toLowerCase()
  if (severity === "critical") return 2
  if (severity === "warning") return 1
  return 0
}

export function filterRuntimeAlerts(
  alerts: RuntimeAlert[],
  {
    search,
    severity,
    source,
  }: {
    search?: string
    severity?: RuntimeAlertSeverityFilter
    source?: string
  },
) {
  const normalizedSearch = normalizeSearch(search)
  const normalizedSource = normalizeSearch(source)
  const resolvedSeverity = severity ?? "all"

  return [...alerts]
    .filter((alert) => {
      const alertSeverity = normalizeSearch(alert.severity)
      if (resolvedSeverity !== "all" && alertSeverity !== resolvedSeverity) {
        return false
      }
      if (normalizedSource && normalizedSource !== "all" && normalizeSearch(alert.source) !== normalizedSource) {
        return false
      }
      return includesSearch(
        [alert.title, alert.detail, alert.source, alert.workflowRunId, alert.taskId],
        normalizedSearch,
      )
    })
    .sort((left, right) => {
      const severityDiff = runtimeAlertPriority(right) - runtimeAlertPriority(left)
      if (severityDiff !== 0) return severityDiff
      const timeDiff = Date.parse(right.updatedAt || "") - Date.parse(left.updatedAt || "")
      if (Number.isFinite(timeDiff) && timeDiff !== 0) return timeDiff
      return left.title.localeCompare(right.title, "zh-CN")
    })
}

export function summarizeRuntimeAlerts(alerts: RuntimeAlert[]) {
  return {
    total: alerts.length,
    critical: alerts.filter((alert) => normalizeSearch(alert.severity) === "critical").length,
    warning: alerts.filter((alert) => normalizeSearch(alert.severity) === "warning").length,
    distinctSources: collectRuntimeAlertSources(alerts).length,
  }
}
