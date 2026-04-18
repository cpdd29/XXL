"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Play, Plus, Save } from "lucide-react"
import { useWorkflows } from "@/hooks/use-workflows"
import {
  WorkflowEditor,
  type WorkflowEditorActionState,
  type WorkflowEditorHandle,
} from "@/components/workflow/workflow-editor"
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import type { Workflow } from "@/types"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type PendingWorkflowAction =
  | { type: "select"; workflowId: string }
  | { type: "create" }

export default function WorkflowPage() {
  const { data, error, isLoading, isError } = useWorkflows()
  const workflows = data?.items ?? []
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("")
  const [isCreatingWorkflow, setIsCreatingWorkflow] = useState(false)
  const [pendingCreatedWorkflow, setPendingCreatedWorkflow] = useState<Workflow | null>(null)
  const editorRef = useRef<WorkflowEditorHandle>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [pendingAction, setPendingAction] = useState<PendingWorkflowAction | null>(null)
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [isResolvingPendingAction, setIsResolvingPendingAction] = useState(false)
  const [editorActionState, setEditorActionState] = useState<WorkflowEditorActionState>({
    saveDisabled: true,
    runDisabled: true,
    savePending: false,
    runPending: false,
  })

  const defaultWorkflowId = useMemo(
    () =>
      workflows.find((item) => ["running", "active"].includes(String(item.status).toLowerCase()))?.id ??
      workflows[0]?.id ??
      "",
    [workflows],
  )

  useEffect(() => {
    if (isCreatingWorkflow) return
    if (selectedWorkflowId) return
    if (!defaultWorkflowId) return
    setSelectedWorkflowId(defaultWorkflowId)
  }, [defaultWorkflowId, isCreatingWorkflow, selectedWorkflowId])

  useEffect(() => {
    if (!pendingCreatedWorkflow) return
    if (workflows.some((item) => item.id === pendingCreatedWorkflow.id)) {
      setPendingCreatedWorkflow(null)
    }
  }, [pendingCreatedWorkflow, workflows])

  const workflow = useMemo(() => {
    if (isCreatingWorkflow) return undefined
    if (!selectedWorkflowId) {
      return workflows.find((item) => item.id === defaultWorkflowId) ?? workflows[0]
    }
    return (
      workflows.find((item) => item.id === selectedWorkflowId) ??
      (pendingCreatedWorkflow?.id === selectedWorkflowId ? pendingCreatedWorkflow : undefined)
    )
  }, [defaultWorkflowId, isCreatingWorkflow, pendingCreatedWorkflow, selectedWorkflowId, workflows])

  const selectValue = isCreatingWorkflow
    ? "__new__"
    : workflow?.id ?? (selectedWorkflowId || undefined)

  const applyPendingAction = (action: PendingWorkflowAction) => {
    if (action.type === "create") {
      setIsCreatingWorkflow(true)
      setSelectedWorkflowId("")
      return
    }

    setIsCreatingWorkflow(false)
    setSelectedWorkflowId(action.workflowId)
  }

  const requestWorkflowChange = (action: PendingWorkflowAction) => {
    if (action.type === "select" && !isCreatingWorkflow && action.workflowId === selectedWorkflowId) {
      return
    }
    if (action.type === "create" && isCreatingWorkflow && !isDirty) {
      return
    }

    if (isDirty) {
      setPendingAction(action)
      setIsConfirmOpen(true)
      return
    }

    applyPendingAction(action)
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-6 py-3">
        <div className="min-w-[260px] max-w-xl flex-1">
          <div className="mb-1 text-xs text-muted-foreground">工作流筛选</div>
          <Select
            value={selectValue}
            onValueChange={(value) => {
              if (value === "__new__") {
                requestWorkflowChange({ type: "create" })
                return
              }
              requestWorkflowChange({ type: "select", workflowId: value })
            }}
            disabled={isLoading || (workflows.length === 0 && !isCreatingWorkflow)}
          >
            <SelectTrigger className="w-full bg-background">
              <SelectValue placeholder="选择要查看的工作流" />
            </SelectTrigger>
            <SelectContent>
              {isCreatingWorkflow ? <SelectItem value="__new__">新工作流草稿</SelectItem> : null}
              {!isCreatingWorkflow && selectedWorkflowId && !workflow ? (
                <SelectItem value={selectedWorkflowId}>正在同步工作流...</SelectItem>
              ) : null}
              {workflows.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name} · {item.version}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            disabled={editorActionState.saveDisabled}
            onClick={() => {
              void editorRef.current?.save()
            }}
          >
            <Save className="mr-2 size-4" />
            {editorActionState.savePending ? "保存中..." : "保存流程"}
          </Button>
          <Button
            disabled={editorActionState.runDisabled}
            onClick={() => {
              void editorRef.current?.run()
            }}
          >
            <Play className="mr-2 size-4" />
            {editorActionState.runPending ? "启动中..." : "启动运行"}
          </Button>
          <Button
            onClick={() => {
              requestWorkflowChange({ type: "create" })
            }}
          >
            <Plus className="mr-2 size-4" />
            新增工作流
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {isLoading && workflows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            正在加载工作流...
          </div>
        ) : null}
        {isError ? (
          <div className="flex h-full items-center justify-center text-sm text-destructive">
            工作流加载失败：{error instanceof Error ? error.message : "未知错误"}
          </div>
        ) : null}
        {!isError ? (
          <WorkflowEditor
            ref={editorRef}
            workflow={workflow}
            availableWorkflows={workflows}
            onWorkflowCreated={(createdWorkflow) => {
              setIsCreatingWorkflow(false)
              setPendingCreatedWorkflow(createdWorkflow)
              setSelectedWorkflowId(createdWorkflow.id)
            }}
            onActionStateChange={setEditorActionState}
            onDirtyChange={setIsDirty}
          />
        ) : null}
      </div>
      <AlertDialog
        open={isConfirmOpen}
        onOpenChange={(open) => {
          setIsConfirmOpen(open)
          if (!open && !isResolvingPendingAction) {
            setPendingAction(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>当前工作流有未保存的变动</AlertDialogTitle>
            <AlertDialogDescription>
              切换工作流前，是否先保存当前修改？如果直接切换，当前未保存内容会被清空。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              variant="outline"
              disabled={isResolvingPendingAction}
              onClick={() => {
                setIsConfirmOpen(false)
                setPendingAction(null)
              }}
            >
              取消
            </Button>
            <Button
              variant="secondary"
              disabled={isResolvingPendingAction}
              onClick={() => {
                if (!pendingAction) return
                applyPendingAction(pendingAction)
                setPendingAction(null)
                setIsConfirmOpen(false)
              }}
            >
              不保存，直接切换
            </Button>
            <Button
              disabled={isResolvingPendingAction || editorActionState.saveDisabled}
              onClick={async () => {
                if (!pendingAction) return
                setIsResolvingPendingAction(true)
                try {
                  await editorRef.current?.save()
                  applyPendingAction(pendingAction)
                  setPendingAction(null)
                  setIsConfirmOpen(false)
                } catch (error) {
                  console.error("Failed to save workflow before switching", error)
                } finally {
                  setIsResolvingPendingAction(false)
                }
              }}
            >
              {isResolvingPendingAction ? "保存中..." : "先保存再切换"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
