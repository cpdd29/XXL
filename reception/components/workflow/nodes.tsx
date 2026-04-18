"use client"

import { memo } from "react"
import { Handle, Position, NodeProps } from "@xyflow/react"
import { cn } from "@/lib/utils"
import { getWorkflowTriggerTypeLabel } from "./workflow-trigger-config"
import {
  Bot,
  Database,
  Zap,
  GitBranch,
  Search,
  FileText,
  Shield,
  Send,
  MessageCircle,
  MessageSquare,
  Wrench,
  Workflow as WorkflowIcon,
} from "lucide-react"

type WorkflowCanvasNodeData = {
  label?: string
  description?: string | null
  config?: Record<string, unknown> | null
  triggerType?: string
  triggerSummary?: string
  agentType?: string
  agentId?: string | null
  agentName?: string | null
  toolId?: string | null
  toolName?: string | null
  workflowId?: string | null
  workflowName?: string | null
  message?: string | null
  latestError?: string | null
  errorCount?: number
  status?: "idle" | "running" | "waiting" | "completed" | "error"
  tokens?: number
}

function getConfigText(config: Record<string, unknown> | null | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = config?.[key]
    if (value === null || value === undefined) continue
    const normalized = String(value).trim()
    if (normalized) return normalized
  }
  return ""
}

function truncateLine(text?: string | null, limit = 52) {
  const normalized = String(text || "").trim()
  if (!normalized) return ""
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit - 1)}…`
}

function runtimeHint(nodeData: WorkflowCanvasNodeData) {
  if (nodeData.status === "error") {
    return truncateLine(nodeData.latestError || nodeData.message, 56)
  }
  if (nodeData.status && nodeData.status !== "idle") {
    return truncateLine(nodeData.message, 56)
  }
  return ""
}

function DetailLine({
  text,
  tone = "muted",
}: {
  text?: string | null
  tone?: "muted" | "danger"
}) {
  if (!text) return null
  return (
    <div
      className={cn(
        "mt-1 max-w-[220px] truncate text-[11px]",
        tone === "danger" ? "text-destructive" : "text-muted-foreground",
      )}
      title={text}
    >
      {text}
    </div>
  )
}

// Trigger Node
export const TriggerNode = memo(function TriggerNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "running"
            ? "border-success"
            : status === "completed"
              ? "border-primary"
              : status === "error"
                ? "border-destructive"
                : "border-border"
      )}
    >
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-warning/20 text-warning-foreground">
          <Zap className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">{nodeData.label || "触发器"}</div>
          <div className="text-xs text-muted-foreground">
            {status === "completed" ? "已接收任务" : getWorkflowTriggerTypeLabel(nodeData.triggerType)}
          </div>
          {nodeData.triggerSummary ? (
            <div className="mt-1 max-w-[220px] truncate text-[11px] text-muted-foreground">
              {nodeData.triggerSummary}
            </div>
          ) : null}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-warning !bg-background"
      />
    </div>
  )
})

// Agent Node
export const AgentNode = memo(function AgentNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const agentIcons: Record<string, React.ReactNode> = {
    conversation: <MessageCircle className="size-5" />,
    task_dispatcher: <GitBranch className="size-5" />,
    workflow_planner: <GitBranch className="size-5" />,
    memory: <Database className="size-5" />,
    search: <Search className="size-5" />,
    write: <FileText className="size-5" />,
    security: <Shield className="size-5" />,
    intent: <Zap className="size-5" />,
    default: <Bot className="size-5" />,
  }

  const statusColors = {
    idle: "border-muted-foreground/50",
    running: "border-success",
    waiting: "border-warning",
    completed: "border-primary",
    error: "border-destructive",
  }

  const status = nodeData.status || "idle"

  return (
    <div
      className={cn(
        "min-w-[220px] rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected ? "border-primary shadow-primary/20" : statusColors[status]
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          {agentIcons[nodeData.agentType || "default"]}
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-foreground">{nodeData.label || "Agent"}</div>
          <div
            className={cn(
              "truncate text-xs",
              nodeData.agentName ? "text-muted-foreground" : "text-destructive",
            )}
          >
            {nodeData.agentName
              ? nodeData.agentName
              : "未绑定 Agent"}
          </div>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})

// Condition Node
export const ConditionNode = memo(function ConditionNode({
  data,
  selected,
}: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const expressionHint = truncateLine(getConfigText(nodeData.config, "expression"), 52)
  const branchHint = truncateLine(getConfigText(nodeData.config, "branchNote", "branch_note"), 52)
  const detailText =
    runtimeHint(nodeData) ||
    expressionHint ||
    branchHint ||
    truncateLine(nodeData.description, 52) ||
    "点击节点配置分支规则"

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "running"
              ? "border-success"
              : status === "error"
                ? "border-destructive"
                : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-accent !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-accent/20 text-accent">
          <GitBranch className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "条件分支"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "completed" ? "分支已决策" : "分支逻辑"}
          </div>
          <DetailLine text={detailText} tone={nodeData.status === "error" ? "danger" : "muted"} />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        id="true"
        style={{ top: "30%" }}
        className="!size-3 !border-2 !border-success !bg-background"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="false"
        style={{ top: "70%" }}
        className="!size-3 !border-2 !border-destructive !bg-background"
      />
    </div>
  )
})

// Output Node
export const OutputNode = memo(function OutputNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const outputHint = truncateLine(
    getConfigText(nodeData.config, "outputRequirement", "output_requirement", "outputTemplate", "output_template"),
    52,
  )
  const detailText =
    runtimeHint(nodeData) ||
    outputHint ||
    truncateLine(nodeData.description, 52) ||
    "点击节点配置输出要求"

  return (
    <div
      className={cn(
        "min-w-[220px] rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-success"
            : status === "running"
              ? "border-success"
              : status === "waiting"
                ? "border-warning"
            : status === "error"
              ? "border-destructive"
              : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-success !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-success/20 text-success">
          <Send className="size-5" />
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "输出结果"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "completed" ? "已完成输出" : "交付结果"}
          </div>
          <DetailLine text={detailText} tone={nodeData.status === "error" ? "danger" : "muted"} />
        </div>
      </div>
    </div>
  )
})

// Aggregate Node
export const AggregateNode = memo(function AggregateNode({
  data,
  selected,
}: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const mergeHint = truncateLine(getConfigText(nodeData.config, "mergeStrategy", "merge_strategy"), 52)
  const detailText =
    runtimeHint(nodeData) ||
    mergeHint ||
    truncateLine(nodeData.description, 52) ||
    "点击节点配置聚合策略"

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "waiting"
              ? "border-warning"
              : status === "error"
                ? "border-destructive"
                : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <MessageSquare className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "聚合节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "waiting" ? "等待汇总" : status === "completed" ? "已完成汇总" : "合并结果"}
          </div>
          <DetailLine text={detailText} tone={nodeData.status === "error" ? "danger" : "muted"} />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})

export const ParallelNode = memo(function ParallelNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const strategyHint = truncateLine(getConfigText(nodeData.config, "strategy"), 52)
  const maxConcurrency = getConfigText(nodeData.config, "maxConcurrency", "max_concurrency")
  const concurrencyHint = maxConcurrency ? `最大并发：${maxConcurrency}` : ""
  const detailText =
    runtimeHint(nodeData) ||
    strategyHint ||
    concurrencyHint ||
    truncateLine(nodeData.description, 52) ||
    "点击节点配置并行策略"

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "running"
              ? "border-success"
              : status === "waiting"
                ? "border-warning"
                : status === "error"
                  ? "border-destructive"
                  : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <MessageSquare className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "并行节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "并行分发中" : status === "completed" ? "并行已收敛" : "多路并发"}
          </div>
          <DetailLine text={detailText} tone={nodeData.status === "error" ? "danger" : "muted"} />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})

export const MergeNode = memo(function MergeNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const mergeHint = truncateLine(getConfigText(nodeData.config, "mergeStrategy", "merge_strategy"), 52)
  const detailText =
    runtimeHint(nodeData) ||
    mergeHint ||
    truncateLine(nodeData.description, 52) ||
    "点击节点配置合流方式"

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "waiting"
              ? "border-warning"
              : status === "error"
                ? "border-destructive"
                : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <MessageSquare className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "合流节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "waiting" ? "等待合流" : status === "completed" ? "已完成合流" : "汇总上游结果"}
          </div>
          <DetailLine text={detailText} tone={nodeData.status === "error" ? "danger" : "muted"} />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})

export const ToolNode = memo(function ToolNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const payloadHint = truncateLine(getConfigText(nodeData.config, "payloadTemplate", "payload_template"), 52)
  const mappingHint = truncateLine(getConfigText(nodeData.config, "resultMapping", "result_mapping"), 52)
  const detailText =
    runtimeHint(nodeData) ||
    payloadHint ||
    mappingHint ||
    truncateLine(nodeData.description, 52) ||
    (nodeData.toolName ? "点击节点补充工具参数模板" : "点击节点绑定工具能力并配置参数")

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "running"
              ? "border-success"
              : status === "waiting"
                ? "border-warning"
                : status === "error"
                  ? "border-destructive"
                  : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <Wrench className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">{nodeData.label || "历史工具节点"}</div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "工具执行中" : status === "completed" ? "工具已返回" : "调用外部工具"}
          </div>
          <div
            className={cn(
              "mt-1 max-w-[220px] truncate text-[11px]",
              nodeData.toolName ? "text-muted-foreground" : "text-destructive",
            )}
          >
            {nodeData.toolName
              ? `${nodeData.toolName}${nodeData.toolId ? ` · ${nodeData.toolId}` : ""}`
              : "未绑定工具能力"}
          </div>
          <DetailLine
            text={detailText}
            tone={nodeData.status === "error" || !nodeData.toolName ? "danger" : "muted"}
          />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})

export const WorkflowCallNode = memo(function WorkflowCallNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const handoffHint = truncateLine(getConfigText(nodeData.config, "handoffNote", "handoff_note"), 52)
  const detailText =
    runtimeHint(nodeData) ||
    handoffHint ||
    truncateLine(nodeData.description, 52) ||
    (nodeData.workflowName ? "点击节点补充父子流程交接说明" : "点击节点绑定子工作流")

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "running"
              ? "border-success"
              : status === "waiting"
                ? "border-warning"
                : status === "error"
                  ? "border-destructive"
                  : "border-border",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <WorkflowIcon className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">{nodeData.label || "子工作流节点"}</div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "子工作流执行中" : status === "completed" ? "子工作流已完成" : "调用另一个工作流"}
          </div>
          <div
            className={cn(
              "mt-1 max-w-[220px] truncate text-[11px]",
              nodeData.workflowName ? "text-muted-foreground" : "text-destructive",
            )}
          >
            {nodeData.workflowName
              ? `${nodeData.workflowName}${nodeData.workflowId ? ` · ${nodeData.workflowId}` : ""}`
              : "未绑定子工作流"}
          </div>
          <DetailLine
            text={detailText}
            tone={nodeData.status === "error" || !nodeData.workflowName ? "danger" : "muted"}
          />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})

export const TransformNode = memo(function TransformNode({ data, selected }: NodeProps) {
  const nodeData = data as WorkflowCanvasNodeData
  const status = nodeData.status
  const transformHint = truncateLine(getConfigText(nodeData.config, "transformRule", "transform_rule"), 52)
  const detailText =
    runtimeHint(nodeData) ||
    transformHint ||
    truncateLine(nodeData.description, 52) ||
    "点击节点配置转换规则"

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-primary"
            : status === "running"
              ? "border-success"
              : status === "waiting"
                ? "border-warning"
                : status === "error"
                  ? "border-destructive"
                  : "border-border"
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <FileText className="size-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "转换节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "结果转换中" : status === "completed" ? "转换已完成" : "整理中间结果"}
          </div>
          <DetailLine text={detailText} tone={nodeData.status === "error" ? "danger" : "muted"} />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-3 !border-2 !border-primary !bg-background"
      />
    </div>
  )
})
