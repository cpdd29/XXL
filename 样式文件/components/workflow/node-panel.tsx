"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
    description: "工作流入口",
    icon: <Zap className="size-4" />,
    category: "基础",
  },
  {
    type: "agent",
    label: "Agent 节点",
    description: "执行 AI 任务",
    icon: <Bot className="size-4" />,
    category: "基础",
  },
  {
    type: "condition",
    label: "条件节点",
    description: "分支逻辑",
    icon: <GitBranch className="size-4" />,
    category: "流程",
  },
  {
    type: "parallel",
    label: "并行节点",
    description: "并发分发分支",
    icon: <MessageSquare className="size-4" />,
    category: "流程",
  },
  {
    type: "merge",
    label: "合流节点",
    description: "汇总上游结果",
    icon: <MessageSquare className="size-4" />,
    category: "流程",
  },
  {
    type: "transform",
    label: "转换节点",
    description: "重整中间结果",
    icon: <FileText className="size-4" />,
    category: "流程",
  },
  {
    type: "output",
    label: "输出节点",
    description: "发送结果",
    icon: <Send className="size-4" />,
    category: "基础",
  },
  {
    type: "aggregate",
    label: "聚合节点",
    description: "合并多路输入",
    icon: <MessageSquare className="size-4" />,
    category: "基础",
  },
  {
    type: "search-agent",
    label: "搜索 Agent",
    description: "文档/知识搜索",
    icon: <Search className="size-4" />,
    category: "Agent",
  },
  {
    type: "write-agent",
    label: "写作 Agent",
    description: "内容生成",
    icon: <FileText className="size-4" />,
    category: "Agent",
  },
  {
    type: "security-agent",
    label: "安全 Agent",
    description: "安全检测过滤",
    icon: <Shield className="size-4" />,
    category: "Agent",
  },
  {
    type: "tool",
    label: "工具节点",
    description: "调用外部工具",
    icon: <Wrench className="size-4" />,
    category: "工具",
  },
]

const categories = ["基础", "流程", "Agent", "工具"]

interface NodePanelProps {
  onDragStart: (event: React.DragEvent, nodeType: string) => void
}

export function NodePanel({ onDragStart }: NodePanelProps) {
  return (
    <Card className="flex h-full w-64 shrink-0 flex-col rounded-none border-0 border-r border-border bg-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          节点面板
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 space-y-4 overflow-y-auto p-3 pt-0">
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
                    draggable
                    onDragStart={(e) => onDragStart(e, node.type)}
                    className={cn(
                      "flex cursor-grab items-center gap-3 rounded-lg border border-border bg-secondary/50 p-2",
                      "transition-all hover:border-primary/50 hover:bg-secondary active:cursor-grabbing"
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
