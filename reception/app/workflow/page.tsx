"use client"

import { useWorkflows } from "@/hooks/use-workflows"
import { WorkflowEditor } from "@/components/workflow/workflow-editor"

export default function WorkflowPage() {
  const { data, error, isLoading, isError } = useWorkflows()
  const workflow = data?.items[0]

  return (
    <div className="flex min-h-full min-w-0 flex-col">
      <div className="flex items-center justify-between border-b border-border bg-card px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">工作流设计</h1>
          <p className="text-sm text-muted-foreground">
            {workflow ? `${workflow.name} ${workflow.version}` : "客户服务工作流 v2.1"}
          </p>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            正在加载工作流...
          </div>
        ) : null}
        {isError ? (
          <div className="flex h-full items-center justify-center text-sm text-destructive">
            工作流加载失败：{error instanceof Error ? error.message : "未知错误"}
          </div>
        ) : null}
        {!isLoading && !isError ? <WorkflowEditor workflow={workflow} /> : null}
      </div>
    </div>
  )
}
