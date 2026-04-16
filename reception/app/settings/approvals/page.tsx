"use client"

import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useApproveApproval, useApprovals, useCreateApproval, useRejectApproval } from "@/hooks/use-approvals"
import type { ApprovalRequestType, ApprovalStatus } from "@/types"

const statusTone = {
  pending: "bg-warning/10 text-warning",
  approved: "bg-success/10 text-success",
  rejected: "bg-destructive/10 text-destructive",
  expired: "bg-secondary text-secondary-foreground",
  cancelled: "bg-secondary text-secondary-foreground",
} as const

export default function ApprovalsPage() {
  const [status, setStatus] = useState<ApprovalStatus | "all">("all")
  const [requestType, setRequestType] = useState<ApprovalRequestType | "all">("all")
  const approvals = useApprovals({ status, requestType })
  const createApproval = useCreateApproval()
  const approveApproval = useApproveApproval()
  const rejectApproval = useRejectApproval()
  const [title, setTitle] = useState("")
  const [resource, setResource] = useState("")
  const [reason, setReason] = useState("")

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">审批中心</h1>
        <p className="text-sm text-muted-foreground">
          统一承接高风险配置、安全放行、人工接管等控制面审批请求。
        </p>
      </div>

      <Card className="bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium">新建审批单</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="审批标题" />
            <Input value={resource} onChange={(event) => setResource(event.target.value)} placeholder="资源，如 settings.general" />
            <Input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="申请理由" />
          </div>
          <div className="flex justify-end">
            <Button
              disabled={!title.trim() || !resource.trim() || createApproval.isPending}
              onClick={() =>
                createApproval.mutate({
                  requestType: "settings_change",
                  title: title.trim(),
                  resource: resource.trim(),
                  reason: reason.trim() || undefined,
                  payload: { source: "approvals_page" },
                })
              }
            >
              提交审批
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium">筛选</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2">
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value as ApprovalStatus | "all")}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">全部状态</option>
              <option value="pending">pending</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
              <option value="expired">expired</option>
              <option value="cancelled">cancelled</option>
            </select>
            <select
              value={requestType}
              onChange={(event) => setRequestType(event.target.value as ApprovalRequestType | "all")}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">全部类型</option>
              <option value="settings_change">settings_change</option>
              <option value="security_release">security_release</option>
              <option value="manual_handoff">manual_handoff</option>
              <option value="external_capability_release">external_capability_release</option>
            </select>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        {(approvals.data?.items ?? []).map((item) => (
          <Card key={item.id} className="bg-card">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-medium text-foreground">{item.title}</div>
                    <Badge variant="secondary" className={statusTone[item.status]}>
                      {item.status}
                    </Badge>
                    <Badge variant="secondary">{item.requestType}</Badge>
                    <Badge variant="secondary">{item.resource}</Badge>
                  </div>
                  <div className="mt-2 text-sm text-muted-foreground">
                    申请人 {item.requestedBy}，申请时间 {item.requestedAt}
                  </div>
                  {item.reason ? (
                    <div className="mt-2 text-sm leading-6 text-muted-foreground">{item.reason}</div>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={item.status !== "pending" || approveApproval.isPending}
                    onClick={() => approveApproval.mutate({ approvalId: item.id })}
                  >
                    批准
                  </Button>
                  <Button
                    size="sm"
                    disabled={item.status !== "pending" || rejectApproval.isPending}
                    onClick={() => rejectApproval.mutate({ approvalId: item.id })}
                  >
                    拒绝
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {!(approvals.data?.items?.length) ? (
          <Card className="bg-card">
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              当前没有匹配的审批单。
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  )
}
