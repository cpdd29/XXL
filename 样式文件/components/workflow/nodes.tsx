"use client"

import { memo } from "react"
import { Handle, Position, NodeProps } from "@xyflow/react"
import { cn } from "@/lib/utils"
import {
  Bot,
  Zap,
  GitBranch,
  Search,
  FileText,
  Shield,
  Send,
  MessageSquare,
  Wrench,
} from "lucide-react"

// Trigger Node
export const TriggerNode = memo(function TriggerNode({ data, selected }: NodeProps) {
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
          <div className="text-sm font-medium text-foreground">
            {(data as { label?: string }).label || "触发器"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "completed" ? "已接收任务" : "消息触发"}
          </div>
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
  const nodeData = data as {
    label?: string
    agentType?: string
    agentName?: string
    status?: "idle" | "running" | "waiting" | "completed" | "error"
    tokens?: number
  }
  
  const agentIcons: Record<string, React.ReactNode> = {
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
        "min-w-[180px] rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
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
          <div className="text-sm font-medium text-foreground">
            {nodeData.label || "Agent"}
          </div>
          {nodeData.agentName ? (
            <div className="truncate text-[11px] text-muted-foreground">{nodeData.agentName}</div>
          ) : null}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span
              className={cn(
                "size-2 rounded-full",
                status === "running" && "animate-pulse bg-success",
                status === "idle" && "bg-muted-foreground",
                status === "waiting" && "bg-warning",
                status === "completed" && "bg-primary",
                status === "error" && "bg-destructive"
              )}
            />
            {status === "running"
              ? "运行中"
              : status === "idle"
                ? "空闲"
                : status === "waiting"
                  ? "等待"
                  : status === "completed"
                    ? "已完成"
                    : "错误"}
            {nodeData.tokens && (
              <span className="ml-1">| {nodeData.tokens} tokens</span>
            )}
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
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
            {(data as { label?: string }).label || "条件分支"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "completed" ? "分支已决策" : "分支逻辑"}
          </div>
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
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-card px-4 py-3 shadow-lg transition-all",
        selected
          ? "border-primary shadow-primary/20"
          : status === "completed"
            ? "border-success"
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
        <div>
          <div className="text-sm font-medium text-foreground">
            {(data as { label?: string }).label || "输出结果"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "completed" ? "已完成输出" : "发送响应"}
          </div>
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
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
            {(data as { label?: string }).label || "聚合节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "waiting" ? "等待汇总" : status === "completed" ? "已完成汇总" : "合并结果"}
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

export const ParallelNode = memo(function ParallelNode({ data, selected }: NodeProps) {
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
            {(data as { label?: string }).label || "并行节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "并行分发中" : status === "completed" ? "并行已收敛" : "多路并发"}
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

export const MergeNode = memo(function MergeNode({ data, selected }: NodeProps) {
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
            {(data as { label?: string }).label || "合流节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "waiting" ? "等待合流" : status === "completed" ? "已完成合流" : "汇总上游结果"}
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

export const ToolNode = memo(function ToolNode({ data, selected }: NodeProps) {
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
          <div className="text-sm font-medium text-foreground">
            {(data as { label?: string }).label || "工具节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "工具执行中" : status === "completed" ? "工具已返回" : "调用外部工具"}
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

export const TransformNode = memo(function TransformNode({ data, selected }: NodeProps) {
  const status = (data as { status?: "idle" | "running" | "waiting" | "completed" | "error" }).status

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
            {(data as { label?: string }).label || "转换节点"}
          </div>
          <div className="text-xs text-muted-foreground">
            {status === "running" ? "结果转换中" : status === "completed" ? "转换已完成" : "整理中间结果"}
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
