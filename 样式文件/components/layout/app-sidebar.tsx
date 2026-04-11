"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  GitBranch,
  Users,
  Bot,
  ListTodo,
  Shield,
  Settings,
  ChevronDown,
  Wrench,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { useState } from "react"

const navItems = [
  {
    title: "控制台",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    title: "工作流编辑器",
    href: "/workflow",
    icon: GitBranch,
  },
  {
    title: "Agent 协作",
    href: "/collaboration",
    icon: Bot,
  },
  {
    title: "任务管理",
    href: "/tasks",
    icon: ListTodo,
  },
  {
    title: "Agent 管理",
    href: "/agents",
    icon: Bot,
  },
  {
    title: "工具库",
    href: "/tools",
    icon: Wrench,
  },
  {
    title: "用户管理",
    href: "/users",
    icon: Users,
  },
  {
    title: "安全中心",
    href: "/security",
    icon: Shield,
  },
]

export function AppSidebar() {
  const pathname = usePathname()
  const [isExpanded, setIsExpanded] = useState(true)
  const settingsItems = [
    { href: "/settings/general", label: "通用设置" },
    { href: "/settings/agent-api", label: "Agent API 配置" },
    { href: "/settings/channel-integration", label: "渠道接入配置" },
  ]

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-4">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary">
          <Bot className="size-5 text-primary-foreground" />
        </div>
        <span className="text-lg font-semibold text-sidebar-foreground">
          WorkBot
        </span>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(`${item.href}/`)
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-primary"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
              )}
            >
              <item.icon className="size-4" />
              {item.title}
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
          <CollapsibleTrigger className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground">
            <Settings className="size-4" />
            <span className="flex-1 text-left">设置</span>
            <ChevronDown
              className={cn(
                "size-4 transition-transform",
                isExpanded && "rotate-180"
              )}
            />
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-1 pt-1">
            {settingsItems.map((item) => {
              const isActive =
                pathname === item.href || pathname.startsWith(`${item.href}/`)

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 pl-10 text-sm transition-colors",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-primary"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                  )}
                >
                  {item.label}
                </Link>
              )
            })}
          </CollapsibleContent>
        </Collapsible>
      </div>

      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="flex size-8 items-center justify-center rounded-full bg-primary/20 text-primary">
            <span className="text-sm font-medium">管</span>
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-sidebar-foreground">管理员</p>
            <p className="text-xs text-sidebar-foreground/60">admin@workbot.ai</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
