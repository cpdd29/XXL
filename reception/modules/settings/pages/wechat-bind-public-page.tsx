"use client"

import { useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { CheckCircle2, LoaderCircle, QrCode } from "lucide-react"
import {
  useConfirmWecomBindSession,
  usePublicWecomBindSession,
} from "@/modules/settings/hooks/use-settings"
import { toast } from "@/shared/hooks/use-toast"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "--"
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString("zh-CN", { hour12: false })
}

export default function WechatBindPublicPage() {
  const searchParams = useSearchParams()
  const token = useMemo(() => searchParams.get("token")?.trim() ?? "", [searchParams])
  const publicSession = usePublicWecomBindSession(token)
  const confirmBindSession = useConfirmWecomBindSession()
  const [displayName, setDisplayName] = useState("")
  const [externalAccount, setExternalAccount] = useState("")

  const session = publicSession.data?.session ?? null
  const isPending = session?.status === "pending"
  const isBound = session?.status === "bound"
  const isUnavailable = session?.status === "expired" || session?.status === "cancelled"

  const handleConfirm = async () => {
    if (!token) {
      return
    }
    try {
      await confirmBindSession.mutateAsync({
        token,
        body: {
          displayName: displayName.trim(),
          externalAccount: externalAccount.trim() || undefined,
        },
      })
      toast({
        title: "绑定完成",
        description: "当前接入身份已经绑定到平台。",
      })
      await publicSession.refetch()
    } catch (error) {
      toast({
        title: "绑定失败",
        description: error instanceof Error ? error.message : "未知错误",
      })
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_45%),linear-gradient(180deg,_rgba(15,23,42,1),_rgba(2,6,23,1))] p-4">
      <Card className="w-full max-w-lg border-border/70 bg-card/95 shadow-2xl backdrop-blur">
        <CardHeader className="space-y-3 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            {isBound ? <CheckCircle2 className="size-6" /> : <QrCode className="size-6" />}
          </div>
          <CardTitle className="text-xl">微信接入扫码绑定</CardTitle>
        </CardHeader>

        <CardContent className="space-y-4">
          {!token ? (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
              缺少绑定参数，请返回平台重新生成二维码。
            </div>
          ) : null}

          {publicSession.isLoading ? (
            <div className="flex items-center justify-center gap-3 rounded-xl border border-border/70 bg-background/70 p-8 text-sm text-muted-foreground">
              <LoaderCircle className="size-5 animate-spin" />
              正在读取绑定会话...
            </div>
          ) : null}

          {publicSession.error ? (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
              会话读取失败：{publicSession.error instanceof Error ? publicSession.error.message : "未知错误"}
            </div>
          ) : null}

          {session ? (
            <>
              <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
                <div className="text-xs text-muted-foreground">当前租户</div>
                <div className="mt-2 text-base font-medium text-foreground">
                  {publicSession.data?.tenantName || publicSession.data?.tenantId}
                </div>
                <div className="mt-3 text-xs text-muted-foreground">
                  二维码过期时间：{formatDateTime(session.expiresAt)}
                </div>
              </div>

              {isBound ? (
                <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-100">
                  绑定已完成：{session.displayName || "已确认"}
                </div>
              ) : null}

              {isUnavailable ? (
                <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
                  当前二维码已失效，请返回平台重新生成。
                </div>
              ) : null}

              {isPending ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="bind-display-name">接入备注</Label>
                    <Input
                      id="bind-display-name"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                      placeholder="例如：市场部客服微信"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="bind-external-account">补充标识</Label>
                    <Input
                      id="bind-external-account"
                      value={externalAccount}
                      onChange={(event) => setExternalAccount(event.target.value)}
                      placeholder="可填写微信号、手机号或备注，不填也可以"
                    />
                  </div>

                  <Button
                    className="w-full"
                    onClick={() => void handleConfirm()}
                    disabled={confirmBindSession.isPending || !displayName.trim()}
                  >
                    {confirmBindSession.isPending ? "提交中..." : "确认绑定"}
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
