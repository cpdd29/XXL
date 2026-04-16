"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { buildAuthenticatedWebSocketUrl } from "@/lib/api/auth-storage"
import { cn } from "@/lib/utils"
import { WS_BASE_URL } from "@/lib/api/config"
import type { DashboardLogEntry } from "@/types"

const typeStyles = {
  info: "bg-primary/20 text-primary",
  success: "bg-success/20 text-success",
  warning: "bg-warning/20 text-warning-foreground",
  error: "bg-destructive/20 text-destructive",
}

export function RealtimeLog({ initialLogs }: { initialLogs: DashboardLogEntry[] }) {
  const [logs, setLogs] = useState<DashboardLogEntry[]>(initialLogs)

  useEffect(() => {
    setLogs(initialLogs)
  }, [initialLogs])

  useEffect(() => {
    const socketUrl = buildAuthenticatedWebSocketUrl("/api/dashboard/realtime", WS_BASE_URL)
    if (!socketUrl) {
      return
    }

    let socket: WebSocket

    try {
      socket = new WebSocket(socketUrl)
    } catch {
      return
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { items?: DashboardLogEntry[] }
        if (payload.items?.length) {
          setLogs(payload.items)
        }
      } catch {
        // Ignore malformed demo payloads and keep the latest known logs.
      }
    }

    return () => {
      socket.close()
    }
  }, [])

  return (
    <Card className="bg-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium">实时消息流</CardTitle>
          <div className="flex items-center gap-2">
            <div className="size-2 animate-pulse rounded-full bg-success" />
            <span className="text-xs text-muted-foreground">实时更新</span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[300px] pr-4">
          <div className="space-y-3">
            {logs.map((log, index) => (
              <div
                key={log.id}
                className={cn(
                  "flex items-start gap-3 rounded-lg border border-border bg-secondary/30 p-3 transition-all",
                  index === 0 && "animate-in fade-in slide-in-from-top-2"
                )}
              >
                <span className="shrink-0 font-mono text-xs text-muted-foreground">
                  {log.timestamp}
                </span>
                <Badge
                  variant="secondary"
                  className={cn("shrink-0", typeStyles[log.type])}
                >
                  {log.agent}
                </Badge>
                <span className="text-sm text-foreground">{log.message}</span>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
