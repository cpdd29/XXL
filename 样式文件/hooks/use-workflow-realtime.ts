'use client'

import { useEffect, useState } from 'react'
import { buildAuthenticatedWebSocketUrl } from '@/lib/api/auth-storage'
import { WS_BASE_URL } from '@/lib/api/config'
import type { WorkflowRealtimePayload, WorkflowRun } from '@/types'

export type WorkflowRealtimeStatus = 'idle' | 'connecting' | 'connected' | 'disconnected'

function selectRun(payload: WorkflowRealtimePayload, taskId?: string) {
  if (!taskId) {
    return payload.run ?? payload.items[0] ?? null
  }

  if (payload.run?.taskId === taskId) {
    return payload.run
  }

  return payload.items.find((item) => item.taskId === taskId) ?? null
}

export function useWorkflowRealtime({
  workflowId,
  taskId,
}: {
  workflowId?: string
  taskId?: string
}) {
  const [status, setStatus] = useState<WorkflowRealtimeStatus>('idle')
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [run, setRun] = useState<WorkflowRun | null>(null)

  useEffect(() => {
    setRuns([])
    setRun(null)

    if (!workflowId) {
      setStatus('idle')
      return
    }

    let isUnmounted = false
    setStatus('connecting')

    const socketUrl = buildAuthenticatedWebSocketUrl(
      `/api/workflows/${encodeURIComponent(workflowId)}/realtime`,
      WS_BASE_URL,
    )
    if (!socketUrl) {
      setStatus('disconnected')
      return
    }

    let socket: WebSocket

    try {
      socket = new WebSocket(socketUrl)
    } catch {
      setStatus('disconnected')
      return
    }

    socket.onopen = () => {
      if (!isUnmounted) {
        setStatus('connected')
      }
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as WorkflowRealtimePayload

        if (Array.isArray(payload.items) && payload.items.length > 0) {
          setRuns(payload.items)
        }

        const nextRun = selectRun(payload, taskId)
        if (nextRun) {
          setRun(nextRun)
        }
      } catch {
        // Ignore malformed demo payloads and preserve the latest known state.
      }
    }

    socket.onerror = () => {
      if (!isUnmounted) {
        setStatus('disconnected')
      }
    }

    socket.onclose = () => {
      if (!isUnmounted) {
        setStatus('disconnected')
      }
    }

    return () => {
      isUnmounted = true
      socket.close()
    }
  }, [workflowId, taskId])

  return {
    status,
    runs,
    run,
    isConnected: status === 'connected',
  }
}
