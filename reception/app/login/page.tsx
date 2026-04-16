"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/hooks/use-auth"

export default function LoginPage() {
  const router = useRouter()
  const { isAuthenticated, loginMutation, login } = useAuth()
  const [email, setEmail] = useState("admin@workbot.ai")
  const [password, setPassword] = useState("workbot123")
  const [nextPath, setNextPath] = useState("/dashboard")

  useEffect(() => {
    if (typeof window === "undefined") return
    const requestedPath = new URLSearchParams(window.location.search).get("next")
    setNextPath(requestedPath || "/dashboard")
  }, [])

  useEffect(() => {
    if (!isAuthenticated) return
    router.replace(nextPath)
  }, [isAuthenticated, nextPath, router])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md bg-card">
        <CardHeader>
          <CardTitle>管理员登录</CardTitle>
          <CardDescription>
            使用 WorkBot 管理后台演示账号登录
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">邮箱</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button
            className="w-full"
            onClick={async () => {
              await login({ email, password })
              router.replace(nextPath)
            }}
            disabled={loginMutation.isPending}
          >
            {loginMutation.isPending ? "登录中..." : "登录"}
          </Button>
          {loginMutation.isError ? (
            <p className="text-sm text-destructive">
              登录失败，请确认后端服务与账号密码配置。
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
