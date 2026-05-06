import {
  Activity,
  Bot,
  Building2,
  ClipboardCheck,
  Database,
  Headphones,
  LayoutDashboard,
  ListTodo,
  Settings,
  Shield,
  Sparkles,
  TerminalSquare,
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
        title: "知识库",
        href: "/knowledge",
        icon: Database,
        permission: "settings:read",
      },
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
        title: "执行器接入",
        href: "/settings/executors",
        icon: TerminalSquare,
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
    title: "接入层",
    items: [
      {
        title: "接入运营台",
        href: "/intake",
        icon: Activity,
        permission: "dashboard:read",
      },
      {
        title: "安全监听配置",
        href: "/settings/intake-security",
        icon: Shield,
        permission: "settings:read",
      },
    ],
  },
  {
    title: "组织设置",
    items: [
      {
        title: "客户准入配置",
        href: "/settings/admission-template",
        icon: ClipboardCheck,
        permission: "settings:read",
      },
      {
        title: "租户管理",
        href: "/settings/tenants",
        icon: Building2,
        permission: "users:read",
      },
      {
        title: "知识库管理",
        href: "/settings/knowledge",
        icon: Database,
        permission: "settings:read",
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
    href === "/agents" ||
    href === "/tools" ||
    href === "/knowledge"
  ) {
    return pathname.startsWith(`${href}/`)
  }
  return pathname.startsWith(`${href}/`)
}
