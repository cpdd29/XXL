"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Plus, Save } from "lucide-react"
import { useAgents } from "@/hooks/use-agents"
import { toast } from "@/hooks/use-toast"
import { useCreateWorkflow, useWorkflows } from "@/hooks/use-workflows"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  type CreateWorkflowRequest,
  WORKFLOW_PAGE_CATEGORY_OPTIONS,
  WORKFLOW_PAGE_DEFAULT_CATEGORY,
  type Workflow,
  type WorkflowPageCategory,
} from "@/types"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type PendingWorkflowAction =
  | { type: "select"; workflowId: string }
  | { type: "filter"; workflowCategory: WorkflowPageCategory; workflowId: string }
  | { type: "open-create-dialog"; workflowCategory: CreatableWorkflowCategory }

type CreatableWorkflowCategory = Exclude<WorkflowPageCategory, "basic">

type WorkflowCategoryStorage = Record<string, CreatableWorkflowCategory>

type CreateWorkflowDraft = {
  workflowCategory: CreatableWorkflowCategory
  name: string
}

const BASIC_WORKFLOW_ID = "mandatory-workflow-brain-foundation"
const LEGACY_HIDDEN_WORKFLOW_IDS = new Set(["workflow-1"])
const USER_WORKFLOW_ID_PREFIX = "workflow-"
const FREE_WORKFLOW_IDS = new Set(["mandatory-workflow-free-agent"])
const PROFESSIONAL_WORKFLOW_IDS = new Set(["mandatory-workflow-professional-agent"])
const AGENT_WORKFLOW_IDS = new Set([
  "mandatory-workflow-agent-conversation-pipeline",
  "mandatory-workflow-agent-general-assistant-pipeline",
  "mandatory-workflow-agent-requirement-dispatch-pipeline",
  "mandatory-workflow-agent-security-pipeline",
])
const WORKFLOW_CATEGORY_STORAGE_KEY = "workflow-page.custom-categories"
const DEFAULT_CREATE_WORKFLOW_CATEGORY: CreatableWorkflowCategory = "free"

function isUserWorkflowId(value: string) {
  return value.startsWith(USER_WORKFLOW_ID_PREFIX)
}

function isCreatableWorkflowCategory(value: string): value is CreatableWorkflowCategory {
  return value === "professional" || value === "free" || value === "agent"
}

function readStoredWorkflowCategories(): WorkflowCategoryStorage {
  if (typeof window === "undefined") {
    return {}
  }

  try {
    const rawValue = window.localStorage.getItem(WORKFLOW_CATEGORY_STORAGE_KEY)
    if (!rawValue) {
      return {}
    }

    const parsedValue = JSON.parse(rawValue)
    if (!parsedValue || typeof parsedValue !== "object") {
      return {}
    }

    return Object.fromEntries(
      Object.entries(parsedValue).filter(
        (entry): entry is [string, CreatableWorkflowCategory] =>
          isUserWorkflowId(String(entry[0] ?? "")) && isCreatableWorkflowCategory(String(entry[1] ?? "")),
      ),
    )
  } catch {
    return {}
  }
}

function writeStoredWorkflowCategories(categories: WorkflowCategoryStorage) {
  if (typeof window === "undefined") {
    return
  }

  if (Object.keys(categories).length === 0) {
    window.localStorage.removeItem(WORKFLOW_CATEGORY_STORAGE_KEY)
    return
  }

  window.localStorage.setItem(WORKFLOW_CATEGORY_STORAGE_KEY, JSON.stringify(categories))
}

function createWorkflowDraft(workflowCategory: CreatableWorkflowCategory): CreateWorkflowDraft {
  return {
    workflowCategory,
    name: "",
  }
}

function resolveInitialCreateWorkflowCategory(
  workflowCategory: WorkflowPageCategory | null | undefined,
): CreatableWorkflowCategory {
  return workflowCategory && isCreatableWorkflowCategory(workflowCategory)
    ? workflowCategory
    : DEFAULT_CREATE_WORKFLOW_CATEGORY
}

function buildCreateWorkflowPayload(name: string): CreateWorkflowRequest {
  return {
    name,
    description: "",
    version: "v1.0",
    status: "draft",
    trigger: {
      type: "manual",
      description: "",
      priority: 100,
      channels: [],
    },
    nodes: [],
    edges: [],
  }
}

function resolveDefaultWorkflowId(workflows: Workflow[]) {
  return (
    workflows.find((item) => ["running", "active"].includes(String(item.status).toLowerCase()))?.id ??
    workflows[0]?.id ??
    ""
  )
}

function isHiddenWorkflow(workflow: Workflow) {
  const workflowId = String(workflow.id ?? "").trim()
  return LEGACY_HIDDEN_WORKFLOW_IDS.has(workflowId)
}

function isAgentWorkflow(workflow: Workflow, agentWorkflowIds: ReadonlySet<string>) {
  const workflowId = String(workflow.id ?? "").trim()
  return agentWorkflowIds.has(workflowId) || AGENT_WORKFLOW_IDS.has(workflowId)
}

function isProfessionalWorkflow(workflow: Workflow) {
  const workflowId = String(workflow.id ?? "").trim()
  return PROFESSIONAL_WORKFLOW_IDS.has(workflowId)
}

function isFreeWorkflow(workflow: Workflow) {
  const workflowId = String(workflow.id ?? "").trim()
  return FREE_WORKFLOW_IDS.has(workflowId)
}

function resolveExplicitWorkflowCategory(
  workflow: Workflow,
  agentWorkflowIds: ReadonlySet<string>,
  storedWorkflowCategories: WorkflowCategoryStorage,
): WorkflowPageCategory | null {
  const workflowId = String(workflow.id ?? "").trim()

  if (workflowId === BASIC_WORKFLOW_ID) {
    return "basic"
  }
  if (isAgentWorkflow(workflow, agentWorkflowIds)) {
    return "agent"
  }
  if (storedWorkflowCategories[workflowId]) {
    return storedWorkflowCategories[workflowId]
  }
  if (isProfessionalWorkflow(workflow)) {
    return "professional"
  }
  if (isFreeWorkflow(workflow)) {
    return "free"
  }
  return null
}

function resolveWorkflowCategory(
  workflow: Workflow,
  agentWorkflowIds: ReadonlySet<string>,
  storedWorkflowCategories: WorkflowCategoryStorage,
): WorkflowPageCategory {
  return resolveExplicitWorkflowCategory(workflow, agentWorkflowIds, storedWorkflowCategories) ?? "free"
}

function getWorkflowDisplayName(workflow: Workflow) {
  return String(workflow.id ?? "").trim() === BASIC_WORKFLOW_ID ? "基本工作流" : workflow.name
}

function isVisibleWorkflow(
  workflow: Workflow,
  agentWorkflowIds: ReadonlySet<string>,
  storedWorkflowCategories: WorkflowCategoryStorage,
) {
  if (isHiddenWorkflow(workflow)) {
    return false
  }

  return resolveExplicitWorkflowCategory(workflow, agentWorkflowIds, storedWorkflowCategories) !== null
}

export default function WorkflowPage() {
  const { data, error, isLoading, isError } = useWorkflows()
  const createWorkflow = useCreateWorkflow()
  const { data: agentsData } = useAgents()
  const workflows = data?.items ?? []
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("")
  const [selectedWorkflowCategory, setSelectedWorkflowCategory] = useState<WorkflowPageCategory | null>(null)
  const [pendingCreatedWorkflow, setPendingCreatedWorkflow] = useState<Workflow | null>(null)
  const [storedWorkflowCategories, setStoredWorkflowCategories] = useState<WorkflowCategoryStorage>(() =>
    readStoredWorkflowCategories(),
  )
  const editorRef = useRef<WorkflowEditorHandle>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [pendingAction, setPendingAction] = useState<PendingWorkflowAction | null>(null)
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [isResolvingPendingAction, setIsResolvingPendingAction] = useState(false)
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [createDraft, setCreateDraft] = useState<CreateWorkflowDraft>(() =>
    createWorkflowDraft(DEFAULT_CREATE_WORKFLOW_CATEGORY),
  )
  const [editorActionState, setEditorActionState] = useState<WorkflowEditorActionState>({
    saveDisabled: true,
    savePending: false,
  })
  const [workflowEnabledOverride, setWorkflowEnabledOverride] = useState<boolean | null>(null)

  const agentWorkflowIds = useMemo(() => {
    const ids = new Set<string>()
    for (const agent of agentsData?.items ?? []) {
      const workflowId = String(agent.agentWorkflowId ?? "").trim()
      if (workflowId) {
        ids.add(workflowId)
      }
    }
    return ids
  }, [agentsData?.items])

  useEffect(() => {
    writeStoredWorkflowCategories(storedWorkflowCategories)
  }, [storedWorkflowCategories])

  useEffect(() => {
    if (!workflows.length) {
      return
    }

    const availableUserWorkflowIds = new Set(
      workflows
        .map((item) => String(item.id ?? "").trim())
        .filter((workflowId) => isUserWorkflowId(workflowId) && !LEGACY_HIDDEN_WORKFLOW_IDS.has(workflowId)),
    )

    setStoredWorkflowCategories((current) => {
      const nextEntries = Object.entries(current).filter(([workflowId]) => availableUserWorkflowIds.has(workflowId))
      if (nextEntries.length === Object.keys(current).length) {
        return current
      }
      return Object.fromEntries(nextEntries)
    })
  }, [workflows])

  const visibleWorkflows = useMemo(
    () => {
      const items = workflows.filter((item) =>
        isVisibleWorkflow(item, agentWorkflowIds, storedWorkflowCategories),
      )

      if (
        pendingCreatedWorkflow &&
        !items.some((item) => item.id === pendingCreatedWorkflow.id) &&
        isVisibleWorkflow(pendingCreatedWorkflow, agentWorkflowIds, storedWorkflowCategories)
      ) {
        items.push(pendingCreatedWorkflow)
      }

      return items
    },
    [agentWorkflowIds, pendingCreatedWorkflow, storedWorkflowCategories, workflows],
  )

  const effectiveWorkflowCategory = useMemo<WorkflowPageCategory>(() => {
    if (selectedWorkflowCategory) {
      return selectedWorkflowCategory
    }
    if (visibleWorkflows.some((item) => String(item.id ?? "").trim() === BASIC_WORKFLOW_ID)) {
      return WORKFLOW_PAGE_DEFAULT_CATEGORY
    }
    const seedWorkflow = visibleWorkflows[0]
    return seedWorkflow
      ? resolveWorkflowCategory(seedWorkflow, agentWorkflowIds, storedWorkflowCategories)
      : WORKFLOW_PAGE_DEFAULT_CATEGORY
  }, [agentWorkflowIds, selectedWorkflowCategory, storedWorkflowCategories, visibleWorkflows])

  const filteredWorkflows = useMemo(
    () =>
      visibleWorkflows.filter(
        (item) =>
          resolveWorkflowCategory(item, agentWorkflowIds, storedWorkflowCategories) ===
          effectiveWorkflowCategory,
      ),
    [agentWorkflowIds, effectiveWorkflowCategory, storedWorkflowCategories, visibleWorkflows],
  )

  const defaultWorkflowId = useMemo(() => resolveDefaultWorkflowId(filteredWorkflows), [filteredWorkflows])

  useEffect(() => {
    if (selectedWorkflowCategory) return
    if (!visibleWorkflows.length) return
    setSelectedWorkflowCategory(effectiveWorkflowCategory)
  }, [effectiveWorkflowCategory, selectedWorkflowCategory, visibleWorkflows.length])

  useEffect(() => {
    if (selectedWorkflowId && filteredWorkflows.some((item) => item.id === selectedWorkflowId)) return
    if (!defaultWorkflowId) {
      if (selectedWorkflowId) {
        setSelectedWorkflowId("")
      }
      return
    }
    setSelectedWorkflowId(defaultWorkflowId)
  }, [defaultWorkflowId, filteredWorkflows, selectedWorkflowId])

  useEffect(() => {
    if (!pendingCreatedWorkflow) return
    if (workflows.some((item) => item.id === pendingCreatedWorkflow.id)) {
      setPendingCreatedWorkflow(null)
    }
  }, [pendingCreatedWorkflow, workflows])

  const workflow = useMemo(() => {
    if (!selectedWorkflowId) {
      return filteredWorkflows.find((item) => item.id === defaultWorkflowId) ?? filteredWorkflows[0]
    }
    return (
      filteredWorkflows.find((item) => item.id === selectedWorkflowId) ??
      (pendingCreatedWorkflow?.id === selectedWorkflowId ? pendingCreatedWorkflow : undefined)
    )
  }, [defaultWorkflowId, filteredWorkflows, pendingCreatedWorkflow, selectedWorkflowId])

  useEffect(() => {
    setWorkflowEnabledOverride(null)
  }, [workflow?.id, workflow?.status])

  const selectValue = workflow?.id ?? (selectedWorkflowId || undefined)
  const isWorkflowEnabled =
    workflowEnabledOverride ?? ["active", "running"].includes(String(workflow?.status ?? "").toLowerCase())
  const isBasicWorkflow = String(workflow?.id ?? "").trim() === BASIC_WORKFLOW_ID
  const isBasicWorkflowCategory = effectiveWorkflowCategory === "basic"
  const isCreateDisabled = isBasicWorkflowCategory || createWorkflow.isPending
  const isWorkflowEnableDisabled =
    !workflow?.id ||
    (isBasicWorkflow ? editorActionState.savePending : editorActionState.saveDisabled)

  const openCreateDialog = (workflowCategory: CreatableWorkflowCategory) => {
    setCreateDraft(createWorkflowDraft(workflowCategory))
    setIsCreateDialogOpen(true)
  }

  const applyPendingAction = (action: PendingWorkflowAction) => {
    if (action.type === "open-create-dialog") {
      openCreateDialog(action.workflowCategory)
      return
    }
    if (action.type === "filter") {
      setSelectedWorkflowCategory(action.workflowCategory)
      setSelectedWorkflowId(action.workflowId)
      return
    }

    setSelectedWorkflowId(action.workflowId)
  }

  const requestWorkflowChange = (action: PendingWorkflowAction) => {
    if (action.type === "select" && action.workflowId === selectedWorkflowId) {
      return
    }
    if (
      action.type === "filter" &&
      action.workflowCategory === effectiveWorkflowCategory &&
      action.workflowId === (workflow?.id ?? selectedWorkflowId)
    ) {
      return
    }
    if (
      action.type === "open-create-dialog" &&
      isCreateDialogOpen &&
      action.workflowCategory === createDraft.workflowCategory &&
      !createDraft.name.trim()
    ) {
      return
    }

    if (isDirty) {
      setPendingAction(action)
      setIsConfirmOpen(true)
      return
    }

    applyPendingAction(action)
  }

  const handleWorkflowCategoryChange = (nextCategory: WorkflowPageCategory) => {
    if (nextCategory === effectiveWorkflowCategory) return

    const currentWorkflowCategory = workflow
      ? resolveWorkflowCategory(workflow, agentWorkflowIds, storedWorkflowCategories)
      : null

    if (workflow && currentWorkflowCategory === nextCategory) {
      setSelectedWorkflowCategory(nextCategory)
      return
    }

    const nextFilteredWorkflows = visibleWorkflows.filter(
      (item) => resolveWorkflowCategory(item, agentWorkflowIds, storedWorkflowCategories) === nextCategory,
    )

    requestWorkflowChange({
      type: "filter",
      workflowCategory: nextCategory,
      workflowId: resolveDefaultWorkflowId(nextFilteredWorkflows),
    })
  }

  const handleEnabledChange = async (checked: boolean) => {
    if (!editorRef.current?.setEnabled) return

    setWorkflowEnabledOverride(checked)

    try {
      await editorRef.current.setEnabled(checked)
    } catch (error) {
      setWorkflowEnabledOverride(null)
      console.error("Failed to update workflow enabled state", error)
    }
  }

  const handleCreateWorkflow = async () => {
    const workflowName = createDraft.name.trim()
    if (!workflowName) {
      return
    }

    try {
      const response = await createWorkflow.mutateAsync(buildCreateWorkflowPayload(workflowName))
      if (!response.workflow) {
        throw new Error("工作流创建结果为空")
      }

      setStoredWorkflowCategories((current) => ({
        ...current,
        [response.workflow.id]: createDraft.workflowCategory,
      }))
      setPendingCreatedWorkflow(response.workflow)
      setSelectedWorkflowCategory(createDraft.workflowCategory)
      setSelectedWorkflowId(response.workflow.id)
      setIsCreateDialogOpen(false)
      setCreateDraft(createWorkflowDraft(createDraft.workflowCategory))
    } catch (error) {
      toast({
        title: "新增工作流失败",
        description: error instanceof Error ? error.message : "请稍后重试",
        variant: "destructive",
      })
    }
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <div className="flex items-end justify-between gap-4 overflow-x-auto border-b border-border bg-card px-6 py-3">
        <div className="flex shrink-0 items-end justify-start gap-3">
          <div className="w-[220px] shrink-0">
            <div className="mb-1 text-xs text-muted-foreground">工作流类型</div>
            <Select
              value={effectiveWorkflowCategory}
              onValueChange={(value) => {
                handleWorkflowCategoryChange(value as WorkflowPageCategory)
              }}
              disabled={isLoading}
            >
              <SelectTrigger className="w-full bg-background">
                <SelectValue placeholder="选择工作流类型" />
              </SelectTrigger>
              <SelectContent>
                {WORKFLOW_PAGE_CATEGORY_OPTIONS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-[360px] shrink-0">
            <div className="mb-1 text-xs text-muted-foreground">工作流筛选</div>
            <Select
              value={selectValue}
              onValueChange={(value) => {
                requestWorkflowChange({ type: "select", workflowId: value })
              }}
              disabled={isLoading || filteredWorkflows.length === 0}
            >
              <SelectTrigger className="w-full bg-background">
                <SelectValue placeholder="选择要查看的工作流" />
              </SelectTrigger>
              <SelectContent>
                {selectedWorkflowId && !workflow ? (
                  <SelectItem value={selectedWorkflowId}>正在同步工作流...</SelectItem>
                ) : null}
                {filteredWorkflows.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {getWorkflowDisplayName(item)} · {item.version}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2">
          <div className="flex items-center">
            <Switch
              className="data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-muted-foreground/25"
              checked={isWorkflowEnabled}
              disabled={isWorkflowEnableDisabled}
              onCheckedChange={(checked) => {
                void handleEnabledChange(checked)
              }}
            />
          </div>
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
            disabled={isCreateDisabled}
            onClick={() => {
              if (isCreateDisabled) return
              requestWorkflowChange({
                type: "open-create-dialog",
                workflowCategory: resolveInitialCreateWorkflowCategory(effectiveWorkflowCategory),
              })
            }}
          >
            <Plus className="mr-2 size-4" />
            新增工作流
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {isLoading && visibleWorkflows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            正在加载工作流...
          </div>
        ) : null}
        {isError ? (
          <div className="flex h-full items-center justify-center text-sm text-destructive">
            工作流加载失败：{error instanceof Error ? error.message : "未知错误"}
          </div>
        ) : null}
        {!isError && filteredWorkflows.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
            当前“{WORKFLOW_PAGE_CATEGORY_OPTIONS.find((item) => item.value === effectiveWorkflowCategory)?.label ?? "工作流"}”下暂无可编辑工作流
          </div>
        ) : null}
        {!isError && filteredWorkflows.length > 0 ? (
          <WorkflowEditor
            ref={editorRef}
            workflow={workflow}
            availableWorkflows={visibleWorkflows}
            onActionStateChange={setEditorActionState}
            onDirtyChange={setIsDirty}
          />
        ) : null}
      </div>
      <Dialog
        open={isCreateDialogOpen}
        onOpenChange={(open) => {
          if (createWorkflow.isPending) {
            return
          }
          setIsCreateDialogOpen(open)
          if (!open) {
            setCreateDraft(createWorkflowDraft(resolveInitialCreateWorkflowCategory(effectiveWorkflowCategory)))
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新增工作流</DialogTitle>
            <DialogDescription>填写工作流类型和名称后创建对应数据。</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="workflow-category">工作流类型</Label>
              <Select
                value={createDraft.workflowCategory}
                onValueChange={(value) => {
                  if (!isCreatableWorkflowCategory(value)) {
                    return
                  }
                  setCreateDraft((current) => ({
                    ...current,
                    workflowCategory: value,
                  }))
                }}
                disabled={createWorkflow.isPending}
              >
                <SelectTrigger id="workflow-category" className="w-full bg-background">
                  <SelectValue placeholder="选择工作流类型" />
                </SelectTrigger>
                <SelectContent>
                  {WORKFLOW_PAGE_CATEGORY_OPTIONS.filter((item) => item.value !== "basic").map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="workflow-name">工作流名称</Label>
              <Input
                id="workflow-name"
                value={createDraft.name}
                onChange={(event) => {
                  setCreateDraft((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }}
                placeholder="请输入工作流名称"
                disabled={createWorkflow.isPending}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={createWorkflow.isPending}
              onClick={() => {
                setIsCreateDialogOpen(false)
                setCreateDraft(createWorkflowDraft(resolveInitialCreateWorkflowCategory(effectiveWorkflowCategory)))
              }}
            >
              取消
            </Button>
            <Button
              type="button"
              disabled={createWorkflow.isPending || !createDraft.name.trim()}
              onClick={() => {
                void handleCreateWorkflow()
              }}
            >
              {createWorkflow.isPending ? "创建中..." : "确认"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
