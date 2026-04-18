"use client"

import { Bell, Search, HelpCircle } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Badge } from "@/components/ui/badge"
import { ThemeToggle } from "@/components/theme-toggle"

export function AppHeader() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
      <div className="flex items-center gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索工作流、执行任务、skill/mcp 接入..."
            className="w-80 bg-secondary pl-10"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <ThemeToggle />
        
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="size-5" />
          <Badge className="absolute -right-1 -top-1 flex size-5 items-center justify-center rounded-full bg-destructive p-0 text-xs">
            3
          </Badge>
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <HelpCircle className="size-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>帮助中心</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>文档</DropdownMenuItem>
            <DropdownMenuItem>API 参考</DropdownMenuItem>
            <DropdownMenuItem>联系支持</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="ml-2 flex items-center gap-2 border-l border-border pl-4">
          <div className="flex size-2 animate-pulse rounded-full bg-success" />
          <span className="text-sm text-muted-foreground">主脑正常</span>
        </div>
      </div>
    </header>
  )
}
