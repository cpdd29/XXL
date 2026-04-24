import {
  Bot,
  Building2,
  Headphones,
  LayoutDashboard,
  ListTodo,
  Settings,
  Shield,
  Sparkles,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react"

export type NavItem = {
  title: string
  href: string
  icon: LucideIcon
  permission?: string
}

export type NavSection = {
  title: string
  items: NavItem[]
}

export const sidebarNavSections: NavSection[] = [
  {
    title: "工作台",
    items: [
      {
        title: "主脑总览",
        href: "/dashboard",
        icon: LayoutDashboard,
        permission: "dashboard:read",
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
    title: "风险治理",
    items: [
      {
        title: "风险与安全",
        href: "/security",
        icon: Shield,
        permission: "security:read",
      },
    ],
  },
  {
    title: "能力接入",
    items: [
      {
        title: "SKILL/MCP",
        href: "/tools",
        icon: Wrench,
        permission: "tool_sources:read",
      },
      {
        title: "渠道接入",
        href: "/settings/channel-integration",
        icon: Headphones,
        permission: "settings:read",
      },
      {
        title: "模型接入",
        href: "/settings/agent-api",
        icon: Sparkles,
        permission: "settings:read",
      },
      {
        title: "Agent 管理",
        href: "/agents",
        icon: Bot,
        permission: "agents:read",
      },
    ],
  },
  {
    title: "组织设置",
    items: [
      {
        title: "租户管理",
        href: "/settings/tenants",
        icon: Building2,
        permission: "users:read",
      },
      {
        title: "人员画像",
        href: "/users",
        icon: Users,
        permission: "users:read",
      },
      {
        title: "通用设置",
        href: "/settings/general",
        icon: Settings,
        permission: "settings:read",
      },
    ],
  },
]

export function isSidebarNavItemActive(pathname: string, href: string) {
  if (pathname === href) return true
  if (href === "/security") return pathname === "/security"
  if (
    href === "/dashboard" ||
    href === "/tasks" ||
    href === "/users" ||
    href === "/agents" ||
    href === "/tools"
  ) {
    return pathname.startsWith(`${href}/`)
  }
  return pathname.startsWith(`${href}/`)
}
