"use client"

import { cn } from "@/lib/utils"
import { isAgentType, type AgentStatus, type AgentType } from "@/types/agent"
import {
  Bot,
  Database,
  FileText,
  GitBranch,
  MessageCircle,
  MessageSquare,
  Search,
  Shield,
  Zap,
  type LucideIcon,
} from "lucide-react"

interface AgentAvatarProps {
  name: string
  type?: AgentType
  status?: AgentStatus
  size?: "sm" | "md" | "lg"
  showStatus?: boolean
}

const agentIcons = {
  conversation: MessageCircle,
  task_dispatcher: GitBranch,
  workflow_planner: GitBranch,
  memory: Database,
  search: Search,
  write: FileText,
  security: Shield,
  security_guardian: Shield,
  intent: Zap,
  default: Bot,
  output: MessageSquare,
} satisfies Record<AgentType, LucideIcon>

const statusColors = {
  idle: "bg-muted-foreground",
  running: "bg-success animate-pulse",
  waiting: "bg-warning",
  busy: "bg-success animate-pulse",
  degraded: "bg-warning animate-pulse",
  offline: "bg-muted-foreground/60",
  maintenance: "bg-primary/60",
  error: "bg-destructive animate-pulse",
}

const sizeClasses = {
  sm: "size-8",
  md: "size-10",
  lg: "size-12",
}

const iconSizes = {
  sm: "size-4",
  md: "size-5",
  lg: "size-6",
}

export function AgentAvatar({
  name,
  type = "default",
  status = "idle",
  size = "md",
  showStatus = true,
}: AgentAvatarProps) {
  const Icon = agentIcons[type && isAgentType(type) ? type : "default"]

  return (
    <div className="relative inline-flex">
      <div
        className={cn(
          "flex items-center justify-center rounded-lg bg-primary/20 text-primary",
          sizeClasses[size]
        )}
      >
        <Icon className={iconSizes[size]} />
      </div>
      {showStatus && (
        <div
          className={cn(
            "absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-background",
            statusColors[status]
          )}
        />
      )}
    </div>
  )
}
