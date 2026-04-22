"use client"

import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import {
  Bot,
  Zap,
  GitBranch,
  FileText,
  Shield,
  Send,
  MessageSquare,
  Workflow as WorkflowIcon,
} from "lucide-react"

interface NodeTypeItem {
  type: string
  label: string
  description: string
  icon: React.ReactNode
  category: string
}

const nodeTypes: NodeTypeItem[] = [
  {
    type: "trigger",
    label: "触发节点",
    description: "消息触发 / 工作流触发",
    icon: <Zap className="size-4" />,
    category: "动态节点",
  },
  {
    type: "agent",
    label: "Agent 节点",
    description: "绑定 Agent 执行任务",
    icon: <Bot className="size-4" />,
    category: "动态节点",
  },
  {
    type: "output",
    label: "输出节点",
    description: "定义最终输出要求",
    icon: <Send className="size-4" />,
    category: "动态节点",
  },
  {
    type: "condition",
    label: "条件节点",
    description: "分支逻辑",
    icon: <GitBranch className="size-4" />,
    category: "控制节点",
  },
  {
    type: "parallel",
    label: "并行节点",
    description: "并发分发分支",
    icon: <MessageSquare className="size-4" />,
    category: "控制节点",
  },
  {
    type: "merge",
    label: "合流节点",
    description: "汇总上游结果",
    icon: <MessageSquare className="size-4" />,
    category: "控制节点",
  },
  {
    type: "sub_workflow",
    label: "子工作流节点",
    description: "在父流程中嵌套执行子流程",
    icon: <WorkflowIcon className="size-4" />,
    category: "控制节点",
  },
  {
    type: "trigger_workflow",
    label: "触发工作流节点",
    description: "流程内触发另一个工作流",
    icon: <WorkflowIcon className="size-4" />,
    category: "控制节点",
  },
  {
    type: "transform",
    label: "转换节点",
    description: "重整中间结果",
    icon: <FileText className="size-4" />,
    category: "控制节点",
  },
  {
    type: "security-agent",
    label: "安全角色",
    description: "常用安全审查 Agent",
    icon: <Shield className="size-4" />,
    category: "常用 Agent",
  },
]

const categories = ["动态节点", "控制节点", "常用 Agent"]

interface NodePanelProps {
  onDragStart: (event: React.DragEvent, nodeType: string) => void
  canEdit: boolean
}

export function NodePanel({ onDragStart, canEdit }: NodePanelProps) {
  return (
    <Card className="flex h-full w-full flex-col rounded-none border-0 border-r border-border bg-card">
      <CardContent className="flex-1 space-y-4 overflow-y-auto p-3">
        {categories.map((category) => (
          <div key={category} className="space-y-2">
            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {category}
            </h4>
            <div className="space-y-1">
              {nodeTypes
                .filter((node) => node.category === category)
                .map((node) => (
                  <div
                    key={node.type}
                    draggable={canEdit}
                    onDragStart={(e) => onDragStart(e, node.type)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg border border-border bg-secondary/50 p-2",
                      canEdit
                        ? "cursor-grab transition-all hover:border-primary/50 hover:bg-secondary active:cursor-grabbing"
                        : "cursor-default"
                    )}
                  >
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/20 text-primary">
                      {node.icon}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-foreground">
                        {node.label}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {node.description}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
