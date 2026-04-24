"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { ensureActiveAccessToken } from "@/platform/api/client"

export function HomeRedirect() {
  const router = useRouter()

  useEffect(() => {
    let cancelled = false

    const redirect = async () => {
      const token = await ensureActiveAccessToken()
      if (!cancelled) {
        router.replace(token ? "/dashboard" : "/login")
      }
    }

    void redirect()

    return () => {
      cancelled = true
    }
  }, [router])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
      正在跳转...
    </div>
  )
}
