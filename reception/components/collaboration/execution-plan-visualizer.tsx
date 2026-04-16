"use client"

import { Bot, GitBranch, Route, ShieldAlert, Split, Workflow } from "lucide-react"

import type {
  CollaborationExecutionPlan,
  CollaborationExecutionPlanBranchResult,
  CollaborationExecutionPlanStep,
} from "@/types"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

function planModeTone(mode?: string | null) {
  const normalized = `${mode ?? ""}`.trim().toLowerCase()
  if (normalized === "parallel") return "bg-primary/15 text-primary"
  if (normalized === "serial") return "bg-secondary text-secondary-foreground"
  if (normalized === "race") return "bg-warning/20 text-warning-foreground"
  if (normalized === "quorum") return "bg-success/15 text-success"
  return "bg-muted text-muted-foreground"
}

function planTypeLabel(planType?: string | null) {
  const normalized = `${planType ?? ""}`.trim().toLowerCase()
  if (normalized === "multi_agent") return "多触手编排"
  if (normalized === "single_path") return "单路径执行"
  if (normalized === "free_workflow") return "自由工作流"
  return planType || "--"
}

function coordinationLabel(mode?: string | null) {
  const normalized = `${mode ?? ""}`.trim().toLowerCase()
  if (normalized === "parallel") return "并行协同"
  if (normalized === "serial") return "串行推进"
  if (normalized === "race") return "竞速择优"
  if (normalized === "quorum") return "法定数收敛"
  return mode || "--"
}

function fallbackLabel(mode?: string | null) {
  const normalized = `${mode ?? ""}`.trim().toLowerCase()
  if (normalized === "planner_recovery") return "Planner 恢复"
  if (normalized === "approval_gate") return "人工审批闸门"
  if (normalized === "direct_agent_fallback") return "直连触手兜底"
  if (normalized === "none") return "无自动回退"
  return mode || "--"
}

function stepIntentLabel(step: CollaborationExecutionPlanStep) {
  return step.intent ?? step.role ?? step.agentType ?? "execution"
}

function summarizeBranches(steps: CollaborationExecutionPlanStep[]) {
  const grouped = new Map<string, CollaborationExecutionPlanStep[]>()
  for (const step of steps) {
    const key = step.branchId ?? `main-${step.index}`
    const current = grouped.get(key) ?? []
    current.push(step)
    grouped.set(key, current)
  }
  return Array.from(grouped.entries()).map(([branchId, branchSteps]) => ({
    branchId,
    steps: branchSteps.sort((left, right) => left.index - right.index),
  }))
}

function branchStatusTone(status?: string | null) {
  const normalized = `${status ?? ""}`.trim().toLowerCase()
  if (normalized === "completed") return "bg-success/15 text-success"
  if (normalized === "failed") return "bg-destructive/15 text-destructive"
  if (normalized === "cancelled") return "bg-warning/20 text-warning-foreground"
  if (normalized === "running") return "bg-primary/15 text-primary"
  return "bg-muted text-muted-foreground"
}

function branchStatusLabel(status?: string | null) {
  const normalized = `${status ?? ""}`.trim().toLowerCase()
  if (normalized === "completed") return "已完成"
  if (normalized === "failed") return "失败"
  if (normalized === "cancelled") return "已取消"
  if (normalized === "running") return "运行中"
  return status || "--"
}

function indexBranchResults(results?: CollaborationExecutionPlanBranchResult[]) {
  const byStepId = new Map<string, CollaborationExecutionPlanBranchResult>()
  const byBranchId = new Map<string, CollaborationExecutionPlanBranchResult>()
  for (const item of results ?? []) {
    if (item.stepId) byStepId.set(item.stepId, item)
    if (item.branchId) byBranchId.set(item.branchId, item)
  }
  return { byStepId, byBranchId }
}

function StepCard({
  step,
  showBranch,
  branchResult,
  isWinner,
}: {
  step: CollaborationExecutionPlanStep
  showBranch: boolean
  branchResult?: CollaborationExecutionPlanBranchResult
  isWinner: boolean
}) {
  return (
    <div className="rounded-2xl border border-border bg-background/80 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Step {step.index + 1}
            </span>
            {showBranch && step.branchId ? (
              <Badge variant="outline" className="border-border text-muted-foreground">
                {step.branchId}
              </Badge>
            ) : null}
            {isWinner ? (
              <Badge variant="secondary" className="bg-success/15 text-success">
                Winner
              </Badge>
            ) : null}
          </div>
          <h4 className="mt-2 text-sm font-semibold text-foreground">
            {step.title ?? step.executionAgent ?? step.id}
          </h4>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {branchResult?.status ? (
            <Badge variant="secondary" className={branchStatusTone(branchResult.status)}>
              {branchStatusLabel(branchResult.status)}
            </Badge>
          ) : null}
          <Badge variant="secondary" className="bg-secondary/70 text-secondary-foreground">
            {stepIntentLabel(step)}
          </Badge>
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted-foreground">
        <div className="flex items-center justify-between gap-3">
          <span>执行触手</span>
          <span className="font-medium text-foreground">{step.executionAgent ?? "--"}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>角色</span>
          <span>{step.role ?? "--"}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span>完成策略</span>
          <span>{step.completionPolicy ?? "--"}</span>
        </div>
        {branchResult ? (
          <div className="flex items-center justify-between gap-3">
            <span>质量分</span>
            <span>{branchResult.score ?? 0}</span>
          </div>
        ) : null}
      </div>

      {step.dependsOn && step.dependsOn.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {step.dependsOn.map((dependency) => (
            <Badge
              key={`${step.id}-${dependency}`}
              variant="outline"
              className="border-primary/20 bg-primary/5 text-primary"
            >
              依赖 {dependency}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function ExecutionPlanVisualizer({
  plan,
  className,
}: {
  plan?: CollaborationExecutionPlan | null
  className?: string
}) {
  if (!plan) return null

  const branches = summarizeBranches(plan.steps)
  const showBranchLane = branches.length > 1 || plan.coordinationMode === "parallel"
  const branchResultIndex = indexBranchResults(plan.branchResults)
  const hasRuntimeResults =
    (plan.branchResults?.length ?? 0) > 0 ||
    !!plan.selectedBranchId ||
    !!plan.selectedAgent ||
    plan.successfulAgents > 0 ||
    plan.failedAgents > 0 ||
    plan.cancelledAgents > 0

  return (
    <Card className={cn("overflow-hidden bg-card", className)}>
      <CardHeader className="border-b border-border pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">执行计划可视化</CardTitle>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {plan.summary ?? "主脑已生成正式执行计划，可用于解释触手编排、汇聚与回退策略。"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className={planModeTone(plan.coordinationMode)}>
              {coordinationLabel(plan.coordinationMode)}
            </Badge>
            <Badge variant="outline" className="border-border text-muted-foreground">
              {planTypeLabel(plan.planType)}
            </Badge>
            <Badge variant="outline" className="border-border text-muted-foreground">
              v{plan.version}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 pt-6">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Workflow className="size-4" />
              Planner / Aggregator
            </div>
            <p className="mt-2 text-sm font-semibold text-foreground">
              {plan.planner ?? "--"} / {plan.aggregator ?? "--"}
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Bot className="size-4" />
              计划规模
            </div>
            <p className="mt-2 text-sm font-semibold text-foreground">
              {plan.stepCount} 步 / {plan.plannedAgentCount ?? plan.stepCount} 个触手
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Route className="size-4" />
              当前归属
            </div>
            <p className="mt-2 text-sm font-semibold text-foreground">{plan.currentOwner ?? "--"}</p>
          </div>
          <div className="rounded-2xl border border-border bg-secondary/30 p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldAlert className="size-4" />
              回退策略
            </div>
            <p className="mt-2 text-sm font-semibold text-foreground">
              {fallbackLabel(plan.fallback?.mode)}
            </p>
          </div>
        </div>

        {hasRuntimeResults ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-border bg-success/10 p-4">
              <div className="text-xs text-muted-foreground">成功触手</div>
              <p className="mt-2 text-sm font-semibold text-foreground">{plan.successfulAgents}</p>
            </div>
            <div className="rounded-2xl border border-border bg-destructive/10 p-4">
              <div className="text-xs text-muted-foreground">失败触手</div>
              <p className="mt-2 text-sm font-semibold text-foreground">{plan.failedAgents}</p>
            </div>
            <div className="rounded-2xl border border-border bg-warning/10 p-4">
              <div className="text-xs text-muted-foreground">取消触手</div>
              <p className="mt-2 text-sm font-semibold text-foreground">{plan.cancelledAgents}</p>
            </div>
            <div className="rounded-2xl border border-border bg-secondary/30 p-4">
              <div className="text-xs text-muted-foreground">胜出分支</div>
              <p className="mt-2 text-sm font-semibold text-foreground">
                {plan.selectedBranchId ?? plan.selectedAgent ?? "--"}
              </p>
            </div>
          </div>
        ) : null}

        <div className="rounded-3xl border border-border bg-[linear-gradient(180deg,rgba(90,110,140,0.08),rgba(90,110,140,0.02))] p-4">
          <div className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground">
            <Split className="size-4" />
            编排轨道
          </div>
          <div className="space-y-4">
            {branches.map((branch, branchIndex) => (
              <div key={branch.branchId} className="rounded-2xl border border-border/70 bg-background/70 p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="bg-primary/10 text-primary">
                      {showBranchLane ? `分支 ${branchIndex + 1}` : "主路径"}
                    </Badge>
                    <span className="text-sm text-muted-foreground">{branch.branchId}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {branch.steps.length} 个执行步骤
                  </span>
                </div>
                <div className="grid gap-3">
                  {branch.steps.map((step) => {
                    const branchResult =
                      branchResultIndex.byStepId.get(step.id) ??
                      (step.branchId ? branchResultIndex.byBranchId.get(step.branchId) : undefined)
                    const isWinner =
                      !!plan.selectedBranchId &&
                      !!step.branchId &&
                      plan.selectedBranchId === step.branchId
                    return (
                      <StepCard
                        key={step.id}
                        step={step}
                        showBranch={showBranchLane}
                        branchResult={branchResult}
                        isWinner={isWinner}
                      />
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-2xl border border-border bg-secondary/20 p-4">
            <h4 className="text-sm font-semibold text-foreground">Fan-out / Fan-in</h4>
            <div className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
              <p>发散方式：{`${(plan.fanOut?.mode as string | undefined) ?? plan.coordinationMode ?? "--"}`}</p>
              <p>分支数量：{`${(plan.fanOut?.branch_count as number | undefined) ?? branches.length}`}</p>
              <p>汇聚策略：{`${(plan.fanIn?.strategy as string | undefined) ?? "--"}`}</p>
              <p>聚合器：{`${(plan.fanIn?.aggregator as string | undefined) ?? plan.aggregator ?? "--"}`}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-secondary/20 p-4">
            <h4 className="text-sm font-semibold text-foreground">汇总规则</h4>
            <div className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
              <p>merge strategy：{plan.mergeStrategy ?? "--"}</p>
              <p>winner strategy：{plan.winnerStrategy ?? "--"}</p>
              <p>selected agent：{plan.selectedAgent ?? "--"}</p>
              <p>
                quorum：
                {plan.quorum && Object.keys(plan.quorum).length > 0
                  ? JSON.stringify(plan.quorum)
                  : "--"}
              </p>
              <p>
                cancel policy：
                {plan.cancelPolicy && Object.keys(plan.cancelPolicy).length > 0
                  ? JSON.stringify(plan.cancelPolicy)
                  : "--"}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-secondary/20 p-4">
            <h4 className="text-sm font-semibold text-foreground">路由依据</h4>
            <div className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
              <p>routing strategy：{plan.routeRationale?.routingStrategy ?? "--"}</p>
              <p>intent：{plan.routeRationale?.intent ?? "--"}</p>
              <p>workflow mode：{plan.routeRationale?.workflowMode ?? "--"}</p>
              <p>interaction mode：{plan.routeRationale?.interactionMode ?? "--"}</p>
              <p>候选 / 跳过：{plan.routeRationale?.candidateCount ?? 0} / {plan.routeRationale?.skippedCount ?? 0}</p>
              {plan.routeRationale?.routeReasonSummary ? (
                <div className="rounded-xl bg-background/70 p-3 text-foreground">
                  {plan.routeRationale.routeReasonSummary}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {plan.branchResults && plan.branchResults.length > 0 ? (
          <div className="rounded-2xl border border-border bg-background/80 p-4">
            <h4 className="text-sm font-semibold text-foreground">并发结果</h4>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {plan.branchResults.map((item) => (
                <div
                  key={`${item.stepId ?? "step"}-${item.branchId ?? "branch"}-${item.agent ?? "agent"}`}
                  className="rounded-xl border border-border bg-secondary/20 p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{item.agent ?? "--"}</span>
                      {plan.selectedBranchId && item.branchId === plan.selectedBranchId ? (
                        <Badge variant="secondary" className="bg-success/15 text-success">
                          选中
                        </Badge>
                      ) : null}
                    </div>
                    <Badge variant="secondary" className={branchStatusTone(item.status)}>
                      {branchStatusLabel(item.status)}
                    </Badge>
                  </div>
                  <div className="mt-2 grid gap-1 text-xs leading-5 text-muted-foreground">
                    <p>branch：{item.branchId ?? "--"}</p>
                    <p>intent：{item.intent ?? "--"}</p>
                    <p>score：{item.score ?? 0}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {plan.fallback ? (
          <div className="rounded-2xl border border-warning/30 bg-warning/10 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="bg-warning/20 text-warning-foreground">
                Fallback
              </Badge>
              <span className="text-sm font-medium text-foreground">
                {fallbackLabel(plan.fallback.mode)}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              target={plan.fallback.target ?? "--"} · onFailure={plan.fallback.onFailure ?? "--"}
            </p>
            {plan.fallback.summary ? (
              <p className="mt-3 text-sm leading-6 text-foreground">{plan.fallback.summary}</p>
            ) : null}
          </div>
        ) : null}

        {plan.metadata && Object.keys(plan.metadata).length > 0 ? (
          <div className="rounded-2xl border border-border bg-background/80 p-4">
            <h4 className="text-sm font-semibold text-foreground">计划元数据</h4>
            <pre className="mt-3 overflow-x-auto rounded-xl bg-secondary/30 p-3 text-xs leading-5 text-muted-foreground">
              {JSON.stringify(plan.metadata, null, 2)}
            </pre>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
