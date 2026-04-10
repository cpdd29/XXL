"use client"

import { cn } from "@/lib/utils"
import { Bot, Search, FileText, Shield, Zap, MessageSquare } from "lucide-react"

type AgentStatus = "idle" | "running" | "waiting" | "busy" | "degraded" | "offline" | "maintenance" | "error"

interface AgentAvatarProps {
  name: string
  type?: "search" | "write" | "security" | "intent" | "default" | "output"
  status?: AgentStatus
  size?: "sm" | "md" | "lg"
  showStatus?: boolean
}

const agentIcons = {
  search: Search,
  write: FileText,
  security: Shield,
  intent: Zap,
  default: Bot,
  output: MessageSquare,
}

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
  const Icon = agentIcons[type]

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
