"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { hasStoredSession, subscribeAuthSession } from "@/platform/api/auth-storage"
import { ensureActiveAccessToken } from "@/platform/api/client"

export function AuthGuard({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  const [isReady, setIsReady] = useState(false)
  const [hasToken, setHasToken] = useState(false)

  useEffect(() => {
    let cancelled = false

    const redirectToLogin = () => {
      const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : ""
      router.replace(`/login${next}`)
    }

    const syncSession = async () => {
      if (!hasStoredSession()) {
        if (!cancelled) {
          setHasToken(false)
          setIsReady(true)
        }
        redirectToLogin()
        return
      }

      const token = await ensureActiveAccessToken()
      if (!token) {
        if (!cancelled) {
          setHasToken(false)
          setIsReady(true)
        }
        redirectToLogin()
        return
      }

      if (!cancelled) {
        setHasToken(true)
        setIsReady(true)
      }
    }

    void syncSession()

    const unsubscribe = subscribeAuthSession(() => {
      if (!hasStoredSession()) {
        setHasToken(false)
        setIsReady(true)
        redirectToLogin()
      }
    })

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [pathname, router])

  if (!isReady || !hasToken) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        正在检查登录状态...
      </div>
    )
  }

  return <>{children}</>
}
