"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  GitBranch,
  Headphones,
  Layers3,
  LayoutDashboard,
  Link2,
  ListTodo,
  Settings,
  Shield,
  Sparkles,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"

type NavItem = {
  title: string
  href: string
  icon: LucideIcon
  permission?: string
}

type NavSection = {
  title: string
  items: NavItem[]
}

const navSections: NavSection[] = [
  {
    title: "工作台",
    items: [
      {
        title: "总览",
        href: "/dashboard",
        icon: LayoutDashboard,
        permission: "dashboard:read",
      },
      {
        title: "待办中心",
        href: "/reception",
        icon: Headphones,
      },
      {
        title: "任务中心",
        href: "/tasks",
        icon: ListTodo,
        permission: "tasks:read",
      },
    ],
  },
  {
    title: "风险中心",
    items: [
      {
        title: "安全中心",
        href: "/security",
        icon: Shield,
        permission: "security:read",
      },
      {
        title: "告警中心",
        href: "/security/alerts",
        icon: AlertTriangle,
        permission: "security:read",
      },
      {
        title: "审批中心",
        href: "/settings/approvals",
        icon: CheckCircle2,
        permission: "approvals:read",
      },
    ],
  },
  {
    title: "能力接入",
    items: [
      {
        title: "能力中心",
        href: "/tools",
        icon: Wrench,
        permission: "tool_sources:read",
      },
      {
        title: "外接治理",
        href: "/settings/external-capabilities",
        icon: Link2,
        permission: "external:read",
      },
      {
        title: "渠道接入",
        href: "/settings/channel-integration",
        icon: Headphones,
        permission: "settings:read",
      },
      {
        title: "工作流设计",
        href: "/workflow",
        icon: GitBranch,
        permission: "workflows:read",
      },
    ],
  },
  {
    title: "系统设置",
    items: [
      {
        title: "通用设置",
        href: "/settings/general",
        icon: Settings,
        permission: "settings:read",
      },
      {
        title: "模型与 Provider",
        href: "/settings/agent-api",
        icon: Sparkles,
        permission: "settings:read",
      },
      {
        title: "配置来源与优先级",
        href: "/settings/governance",
        icon: Layers3,
        permission: "settings:read",
      },
      {
        title: "用户管理",
        href: "/users",
        icon: Users,
        permission: "users:read",
      },
      {
        title: "Agent 管理",
        href: "/agents",
        icon: Bot,
        permission: "agents:read",
      },
    ],
  },
]

function isNavItemActive(pathname: string, href: string) {
  if (pathname === href) return true
  if (href === "/security") return pathname === "/security"
  if (
    href === "/dashboard" ||
    href === "/reception" ||
    href === "/tasks" ||
    href === "/users" ||
    href === "/agents" ||
    href === "/tools" ||
    href === "/workflow"
  ) {
    return pathname.startsWith(`${href}/`)
  }
  return pathname.startsWith(`${href}/`)
}

export function AppSidebar() {
  const pathname = usePathname()
  const { currentUser, hasPermission } = useAuth()

  const visibleSections = navSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !item.permission || hasPermission(item.permission)),
    }))
    .filter((section) => section.items.length > 0)

  return (
    <aside className="flex h-screen w-72 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-4">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary">
          <Bot className="size-5 text-primary-foreground" />
        </div>
        <div>
          <div className="text-lg font-semibold text-sidebar-foreground">WorkBot</div>
          <div className="text-[11px] text-sidebar-foreground/60">主脑控制面</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-3">
        <div className="space-y-5">
          {visibleSections.map((section) => (
            <div key={section.title} className="space-y-1.5">
              <div className="px-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-sidebar-foreground/45">
                {section.title}
              </div>
              <div className="space-y-1">
                {section.items.map((item) => {
                  const isActive = isNavItemActive(pathname, item.href)
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-sidebar-accent text-sidebar-primary"
                          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                      )}
                    >
                      <item.icon className="size-4" />
                      {item.title}
                    </Link>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-3 rounded-lg px-3 py-2">
          <div className="flex size-8 items-center justify-center rounded-full bg-primary/20 text-primary">
            <span className="text-sm font-medium">管</span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-sidebar-foreground">
              {currentUser?.name ?? "当前用户"}
            </p>
            <p className="truncate text-xs text-sidebar-foreground/60">
              {currentUser?.email ?? "-"}
            </p>
          </div>
        </div>
      </div>
    </aside>
  )
}
