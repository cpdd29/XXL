"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Bot,
} from "lucide-react"
import { cn } from "@/shared/utils"
import { useAuth } from "@/modules/auth/hooks/use-auth"
import { isSidebarNavItemActive, sidebarNavSections } from "@/modules/navigation/sidebar-nav"

export function AppSidebar() {
  const pathname = usePathname()
  const { currentUser, hasPermission } = useAuth()

  const visibleSections = sidebarNavSections
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
          <div className="text-[11px] text-sidebar-foreground/60">主脑运行总控台</div>
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
                  const isActive = isSidebarNavItemActive(pathname, item.href)
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
