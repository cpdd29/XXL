"use client"

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react"
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  type NodeMouseHandler,
  MarkerType,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"
import { useTools } from "@/hooks/use-tools"
import { useWorkflowRealtime } from "@/hooks/use-workflow-realtime"
import { NodePanel } from "./node-panel"
import { WorkflowInspector, type WorkflowEditorMeta } from "./workflow-inspector"
import { WorkflowNodeConfigDialog } from "./workflow-node-config-dialog"
import {
  TriggerNode,
  AgentNode,
  ConditionNode,
  ParallelNode,
  MergeNode,
  WorkflowCallNode,
  ToolNode,
  TransformNode,
  OutputNode,
  AggregateNode,
} from "./nodes"
import {
  useCreateWorkflow,
  useWorkflowMonitor,
  useTickWorkflowRun,
  useUpdateWorkflow,
  useWorkflowRuns,
} from "@/hooks/use-workflows"
import { useAgents } from "@/hooks/use-agents"
import type {
  Agent,
  CreateWorkflowRequest,
  Tool,
  Workflow,
  WorkflowTrigger,
  WorkflowNodeType,
  WorkflowRun,
} from "@/types"
import { ChevronLeft, ChevronRight } from "lucide-react"

const nodeTypes: NodeTypes = {
  trigger: TriggerNode,
  agent: AgentNode,
  condition: ConditionNode,
  parallel: ParallelNode,
  merge: MergeNode,
  workflow: WorkflowCallNode,
  sub_workflow: WorkflowCallNode,
  trigger_workflow: WorkflowCallNode,
  tool: ToolNode,
  transform: TransformNode,
  output: OutputNode,
  aggregate: AggregateNode,
}

type FlowNodeData = {
  label?: string
  description?: string | null
  config?: Record<string, unknown> | null
  message?: string | null
  latestError?: string | null
  errorCount?: number
  agentType?: string
  agentId?: string | null
  agentName?: string | null
  toolId?: string | null
  toolName?: string | null
  workflowId?: string | null
  workflowName?: string | null
  workflowNodeKind?: "workflow" | "sub_workflow" | "trigger_workflow"
  triggerType?: string
  triggerSummary?: string
  status?: "idle" | "running" | "waiting" | "completed" | "error"
  tokens?: number
  relationSummary?: string | null
  relatedRunId?: string | null
  relatedRunStatus?: "idle" | "pending" | "running" | "waiting" | "completed" | "error" | null
  relatedRunAnchor?: string | null
  parentRunId?: string | null
  parentWorkflowId?: string | null
  parentNodeId?: string | null
}

const defaultWorkflowMeta: WorkflowEditorMeta = {
  name: "新工作流",
  description: "",
  version: "v1.0",
  status: "draft",
  trigger: {
    type: "message",
    keyword: "",
    cron: null,
    webhookPath: null,
    internalEvent: null,
    description: "",
    priority: 100,
    channels: [],
    preferredLanguage: null,
    stepDelaySeconds: 0.6,
    maxDispatchRetry: 6,
    dispatchRetryBackoffSeconds: 2,
    executionTimeoutSeconds: 45,
  },
}

const initialNodes: Node[] = []

const initialEdges: Edge[] = []
const BASIC_WORKFLOW_ID = "mandatory-workflow-brain-foundation"

let nextNodeId = 9

const getId = () => `${nextNodeId++}`

function getAgentType(label: string) {
  const normalized = label.toLowerCase()
  if (label.includes("对话") || normalized.includes("conversation")) return "conversation"
  if (
    label.includes("分发") ||
    label.includes("调度") ||
    normalized.includes("dispatcher") ||
    normalized.includes("task_dispatcher")
  ) {
    return "task_dispatcher"
  }
  if (
    label.includes("规划") ||
    label.includes("工作流规划") ||
    normalized.includes("workflow_planner") ||
    normalized.includes("workflow planner")
  ) {
    return "workflow_planner"
  }
  if (label.includes("记忆") || normalized.includes("memory")) return "memory"
  if (label.includes("安全") || normalized.includes("security")) return "security"
  if (label.includes("意图") || normalized.includes("intent")) return "intent"
  if (label.includes("搜索") || normalized.includes("search")) return "search"
  if (label.includes("写作") || normalized.includes("write")) return "write"
  if (label.includes("发送") || normalized.includes("output")) return "output"
  return "default"
}

function normalizeNodeType(type?: string | null): WorkflowNodeType {
  if (type === "aggregate") return "merge"
  return (type ?? "agent") as WorkflowNodeType
}

function normalizeWorkflowNodeKind(type?: string | null): FlowNodeData["workflowNodeKind"] {
  if (type === "workflow" || type === "sub_workflow" || type === "trigger_workflow") {
    return type
  }
  return undefined
}

function defaultLabelForNodeType(type: string) {
  const labelByType: Record<string, string> = {
    trigger: "触发节点",
    agent: "Agent 节点",
    condition: "条件节点",
    parallel: "并行节点",
    merge: "合流节点",
    workflow: "子工作流节点",
    sub_workflow: "子工作流节点",
    trigger_workflow: "触发工作流节点",
    tool: "历史工具节点",
    transform: "转换节点",
    output: "输出节点",
  }
  return labelByType[type] ?? `新${type}节点`
}

function getTriggerSummary(trigger: WorkflowTrigger) {
  if (trigger.type === "schedule") return trigger.cron?.trim() || "未配置 Cron 表达式"
  if (trigger.type === "webhook") return trigger.webhookPath?.trim() || "未配置 Webhook 路径"
  if (trigger.type === "internal") return trigger.internalEvent?.trim() || "等待上游工作流触发"
  if (trigger.type === "manual") return trigger.description?.trim() || "由控制台手动触发"

  const parts = [
    trigger.keyword?.trim() ? `关键词：${trigger.keyword}` : null,
    trigger.naturalLanguageRule?.trim() ? `规则：${trigger.naturalLanguageRule}` : null,
    trigger.channels?.length ? `渠道：${trigger.channels.join(", ")}` : null,
  ].filter(Boolean)
  return parts[0] ?? "按消息条件进入工作流"
}

function findAgentById(agents: Agent[], agentId?: string | null) {
  const normalizedId = String(agentId || "").trim()
  if (!normalizedId) return undefined
  return agents.find((item) => item.id === normalizedId)
}

function findToolById(tools: Tool[], toolId?: string | null) {
  const normalizedId = String(toolId || "").trim()
  if (!normalizedId) return undefined
  return tools.find((item) => item.id === normalizedId)
}

function findWorkflowById(workflows: Workflow[], workflowId?: string | null) {
  const normalizedId = String(workflowId || "").trim()
  if (!normalizedId) return undefined
  return workflows.find((item) => item.id === normalizedId)
}

function defaultAgentBindingForPaletteType(type: string, agents: Agent[]) {
  if (type === "security-agent") return agents.find((item) => item.type === "security")
  return undefined
}

function decorateNodeData(
  node: {
    type?: string | null
    label?: string | null
    description?: string | null
    config?: Record<string, unknown> | null
    agentId?: string | null
    toolId?: string | null
    workflowId?: string | null
  },
  {
    agents,
    tools,
    workflows,
    trigger,
  }: {
    agents: Agent[]
    tools: Tool[]
    workflows: Workflow[]
    trigger: WorkflowTrigger
  },
): FlowNodeData {
  const normalizedType = normalizeNodeType(node.type)
  const boundAgent = findAgentById(agents, node.agentId)
  const boundTool = findToolById(tools, node.toolId)
  const boundWorkflow = findWorkflowById(workflows, node.workflowId)

  return {
    label: String(node.label || defaultLabelForNodeType(normalizedType)),
    description: node.description ?? null,
    config: node.config ? { ...node.config } : null,
    agentType:
      normalizedType === "agent"
        ? (boundAgent?.type ?? getAgentType(String(node.label || defaultLabelForNodeType(normalizedType))))
        : undefined,
    agentId: node.agentId ?? undefined,
    agentName: boundAgent?.name ?? undefined,
    toolId: node.toolId ?? undefined,
    toolName: boundTool?.name ?? undefined,
    workflowId: node.workflowId ?? undefined,
    workflowName: boundWorkflow?.name ?? undefined,
    workflowNodeKind: normalizeWorkflowNodeKind(node.type),
    triggerType: normalizedType === "trigger" ? trigger.type : undefined,
    triggerSummary: normalizedType === "trigger" ? getTriggerSummary(trigger) : undefined,
    message: null,
    latestError: null,
    errorCount: 0,
    status: "idle",
    tokens: 0,
    relationSummary: null,
    relatedRunId: null,
    relatedRunStatus: null,
    relatedRunAnchor: null,
    parentRunId: null,
    parentWorkflowId: null,
    parentNodeId: null,
  }
}

function toWorkflowMeta(workflow?: Workflow): WorkflowEditorMeta {
  if (!workflow) return defaultWorkflowMeta
  return {
    name: workflow.name,
    description: workflow.description,
    version: workflow.version,
    status: workflow.status,
    trigger: {
      ...defaultWorkflowMeta.trigger,
      ...workflow.trigger,
      internalEvent:
        workflow.trigger.type === "internal"
          ? (workflow.trigger.internalEvent ?? workflow.trigger.description ?? null)
          : workflow.trigger.internalEvent ?? null,
    },
  }
}

function toReactFlowNodes(
  workflow: Workflow | undefined,
  {
    agents,
    tools,
    workflows,
  }: {
    agents: Agent[]
    tools: Tool[]
    workflows: Workflow[]
  },
): Node[] {
  if (!workflow) return initialNodes

  return workflow.nodes.map((node) => ({
    id: node.id,
    type: normalizeNodeType(node.type),
    position: { x: node.x, y: node.y },
    data: decorateNodeData(
      {
        type: node.type,
        label: node.label,
        description: node.description,
        config: node.config,
        agentId: node.agentId,
        toolId: node.toolId,
        workflowId: node.workflowId,
      },
      { agents, tools, workflows, trigger: workflow.trigger },
    ),
  }))
}

function toReactFlowEdges(workflow?: Workflow): Edge[] {
  if (!workflow) return initialEdges

  return workflow.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    animated: true,
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  }))
}

const referencedRunPatterns = [
  /run=([A-Za-z0-9:_-]+)/i,
  /运行 ID[:：]\s*([A-Za-z0-9:_-]+)/i,
]

function extractReferencedRunId(...texts: Array<string | null | undefined>) {
  for (const text of texts) {
    const normalized = String(text || "").trim()
    if (!normalized) continue
    for (const pattern of referencedRunPatterns) {
      const matched = normalized.match(pattern)
      if (matched?.[1]) {
        return matched[1]
      }
    }
  }
  return null
}

function parseWorkflowTriggerReference(trigger?: string | null) {
  const normalized = String(trigger || "").trim()
  const [prefix = "", workflowId = "", nodeId = ""] = normalized.split(":", 3)
  if (!["workflow", "sub_workflow", "trigger_workflow"].includes(prefix)) return null
  return {
    parentWorkflowId: workflowId || null,
    parentNodeId: nodeId || null,
  }
}

function workflowRelationSummary(
  kind: FlowNodeData["workflowNodeKind"],
  {
    workflowName,
    runId,
    status,
    latestError,
  }: {
    workflowName?: string | null
    runId?: string | null
    status?: string | null
    latestError?: string | null
  },
) {
  const relationLabel = kind === "trigger_workflow" ? "触发流程" : "子流程"
  const workflowText = workflowName ? ` · ${workflowName}` : ""
  const runText = runId ? ` · run ${runId}` : ""
  if (status === "error") {
    return latestError
      ? `${relationLabel}${workflowText}${runText} · ${latestError}`
      : `${relationLabel}${workflowText}${runText} · 执行异常`
  }
  if (status === "completed") {
    return `${relationLabel}${workflowText}${runText} · 已完成`
  }
  if (status === "running") {
    return `${relationLabel}${workflowText}${runText} · 运行中`
  }
  if (status === "waiting" || status === "pending") {
    return `${relationLabel}${workflowText}${runText} · 等待返回`
  }
  return runId ? `${relationLabel}${workflowText}${runText}` : null
}

function applyRunStateToNodes(currentNodes: Node[], run?: WorkflowRun | null): Node[] {
  const runNodesById = new Map((run?.nodes ?? []).map((node) => [node.id, node]))
  const triggerReference = parseWorkflowTriggerReference(run?.trigger)
  const relationsBySourceNodeId = new Map(
    (run?.dispatchContext?.workflowRelations ?? [])
      .filter((relation) => relation.sourceNodeId)
      .map((relation) => [String(relation.sourceNodeId), relation]),
  )
  const parentRunId = run?.dispatchContext?.parentRunId ?? null
  const parentWorkflowId = run?.dispatchContext?.parentWorkflowId ?? triggerReference?.parentWorkflowId ?? null
  const parentNodeId = run?.dispatchContext?.parentNodeId ?? triggerReference?.parentNodeId ?? null
  let changed = false

  const nextNodes = currentNodes.map((node) => {
    const runNode = runNodesById.get(node.id)
    const currentData = node.data as FlowNodeData
    const nextStatus = runNode?.status ?? "idle"
    const nextTokens = runNode?.tokens ?? 0
    const nextMessage = runNode?.message ?? null
    const nextLatestError = runNode?.latestError ?? null
    const nextErrorCount = runNode?.errorCount ?? 0
    let relationSummary: string | null = null
    let relatedRunId: string | null = null
    let relatedRunStatus: FlowNodeData["relatedRunStatus"] = null
    let relatedRunAnchor: string | null = null
    let nextParentRunId: string | null = null
    let nextParentWorkflowId: string | null = null
    let nextParentNodeId: string | null = null

    if ((node.type ?? "") === "trigger" && (parentRunId || parentWorkflowId)) {
      nextParentRunId = parentRunId
      nextParentWorkflowId = parentWorkflowId
      nextParentNodeId = parentNodeId
      relatedRunId = parentRunId
      relatedRunAnchor = parentRunId ? `#workflow-run-${parentRunId}` : null
      relationSummary = [
        "父流程触发",
        parentWorkflowId ? `流程 ${parentWorkflowId}` : null,
        parentRunId ? `run ${parentRunId}` : null,
      ]
        .filter(Boolean)
        .join(" · ")
    } else if (
      currentData.workflowNodeKind === "workflow" ||
      currentData.workflowNodeKind === "sub_workflow" ||
      currentData.workflowNodeKind === "trigger_workflow"
    ) {
      const relatedRelation = relationsBySourceNodeId.get(node.id)
      relatedRunId =
        relatedRelation?.targetRunId ??
        extractReferencedRunId(
          runNode?.message,
          runNode?.latestError,
          ...(runNode?.errorHistory ?? []).map((issue) => issue.message),
        )
      relatedRunStatus = (relatedRelation?.targetStatus as FlowNodeData["relatedRunStatus"]) ?? null
      relatedRunAnchor = relatedRunId ? `#workflow-run-${relatedRunId}` : null
      relationSummary = workflowRelationSummary(currentData.workflowNodeKind, {
        workflowName: relatedRelation?.targetWorkflowName ?? currentData.workflowName,
        runId: relatedRunId,
        status: relatedRunStatus,
        latestError: runNode?.latestError,
      })
    } else if ((run?.trigger ?? "").startsWith("internal:") && (node.type ?? "") === "trigger") {
      relationSummary = `来源事件 · ${(run?.trigger ?? "").slice("internal:".length) || "internal"}`
    }

    if (
      currentData.status === nextStatus &&
      currentData.tokens === nextTokens &&
      currentData.message === nextMessage &&
      currentData.latestError === nextLatestError &&
      currentData.errorCount === nextErrorCount &&
      currentData.relationSummary === relationSummary &&
      currentData.relatedRunId === relatedRunId &&
      currentData.relatedRunStatus === relatedRunStatus &&
      currentData.relatedRunAnchor === relatedRunAnchor &&
      currentData.parentRunId === nextParentRunId &&
      currentData.parentWorkflowId === nextParentWorkflowId &&
      currentData.parentNodeId === nextParentNodeId
    ) {
      return node
    }

    changed = true
    return {
      ...node,
      data: {
        ...currentData,
        status: nextStatus,
        tokens: nextTokens,
        message: nextMessage,
        latestError: nextLatestError,
        errorCount: nextErrorCount,
        relationSummary,
        relatedRunId,
        relatedRunStatus,
        relatedRunAnchor,
        parentRunId: nextParentRunId,
        parentWorkflowId: nextParentWorkflowId,
        parentNodeId: nextParentNodeId,
      } satisfies FlowNodeData,
    }
  })

  return changed ? nextNodes : currentNodes
}

function buildDraftPayload({
  workflowMeta,
  nodes,
  edges,
}: {
  workflowMeta: WorkflowEditorMeta
  nodes: Node[]
  edges: Edge[]
}): CreateWorkflowRequest {
  const payloadNodes = nodes.map((node) => ({
    id: node.id,
    type: (node.type ?? "agent") as WorkflowNodeType,
    label: String((node.data as FlowNodeData | undefined)?.label ?? "未命名节点"),
    x: node.position.x,
    y: node.position.y,
    description: (node.data as FlowNodeData | undefined)?.description ?? null,
    config: (node.data as FlowNodeData | undefined)?.config ?? null,
    agentId: (node.data as FlowNodeData | undefined)?.agentId ?? null,
    toolId: (node.data as FlowNodeData | undefined)?.toolId ?? null,
    workflowId: (node.data as FlowNodeData | undefined)?.workflowId ?? null,
  }))

  const agentBindings = Array.from(
    new Set(
      payloadNodes
        .map((node) => node.agentId)
        .filter((agentId): agentId is string => Boolean(agentId)),
    ),
  )

  return {
    name: workflowMeta.name,
    description: workflowMeta.description,
    version: workflowMeta.version,
    status: workflowMeta.status,
    trigger: workflowMeta.trigger,
    nodes: payloadNodes,
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? undefined,
    })),
    agentBindings,
  }
}

function serializeDraftPayload(payload: CreateWorkflowRequest) {
  return JSON.stringify(payload)
}

interface WorkflowEditorProps {
  workflow?: Workflow
  availableWorkflows?: Workflow[]
  onWorkflowCreated?: (workflow: Workflow) => void
  onActionStateChange?: (state: WorkflowEditorActionState) => void
  onDirtyChange?: (dirty: boolean) => void
}

export interface WorkflowEditorActionState {
  saveDisabled: boolean
  savePending: boolean
}

export interface WorkflowEditorHandle {
  save: () => Promise<void>
  setEnabled: (enabled: boolean) => Promise<void>
}

export const WorkflowEditor = forwardRef<WorkflowEditorHandle, WorkflowEditorProps>(function WorkflowEditor(
  { workflow, availableWorkflows = [], onWorkflowCreated, onActionStateChange, onDirtyChange },
  ref,
) {
  const { hasPermission } = useAuth()
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [reactFlowInstance, setReactFlowInstance] = useState<unknown>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string>()
  const [workflowMeta, setWorkflowMeta] = useState<WorkflowEditorMeta>(defaultWorkflowMeta)
  const [savedSnapshot, setSavedSnapshot] = useState(() =>
    serializeDraftPayload(buildDraftPayload({ workflowMeta: defaultWorkflowMeta, nodes: initialNodes, edges: initialEdges })),
  )
  const [isPaletteOpen, setIsPaletteOpen] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isNodeConfigOpen, setIsNodeConfigOpen] = useState(false)

  const createWorkflow = useCreateWorkflow()
  const updateWorkflow = useUpdateWorkflow()
  const tickWorkflowRun = useTickWorkflowRun()
  const runsQuery = useWorkflowRuns(workflow?.id)
  const monitorQuery = useWorkflowMonitor(workflow?.id)
  const { data: agentsData } = useAgents()
  const { data: toolsData } = useTools()
  const { runs: realtimeRuns } = useWorkflowRealtime({ workflowId: workflow?.id })
  const canEditDefinition = hasPermission("workflows:definition:write")
  const canTickRun = hasPermission("workflows:run:tick")
  const liveRuns = useMemo<WorkflowRun[]>(
    () => (realtimeRuns.length > 0 ? realtimeRuns : runsQuery.data?.items ?? []),
    [realtimeRuns, runsQuery.data?.items],
  )
  const activeRun = liveRuns[0] ?? null
  const savePending = createWorkflow.isPending || updateWorkflow.isPending
  const saveDisabled = !canEditDefinition || savePending
  const isBasicWorkflow = String(workflow?.id ?? "").trim() === BASIC_WORKFLOW_ID
  const agentOptions = agentsData?.items ?? []
  const toolOptions = toolsData?.items ?? []
  const workflowOptions = availableWorkflows
  const currentSnapshot = useMemo(
    () => serializeDraftPayload(buildDraftPayload({ workflowMeta, nodes, edges })),
    [edges, nodes, workflowMeta],
  )
  const isDirty = currentSnapshot !== savedSnapshot

  useEffect(() => {
    const nextNodes = toReactFlowNodes(workflow, {
      agents: agentOptions,
      tools: toolOptions,
      workflows: workflowOptions,
    })
    const nextEdges = toReactFlowEdges(workflow)
    const nextMeta = toWorkflowMeta(workflow)

    setNodes(nextNodes)
    setEdges(nextEdges)
    setWorkflowMeta(nextMeta)
    setSelectedNodeId(undefined)
    setSavedSnapshot(
      serializeDraftPayload(buildDraftPayload({ workflowMeta: nextMeta, nodes: nextNodes, edges: nextEdges })),
    )
  }, [setEdges, setNodes, workflow])

  useEffect(() => {
    setIsPaletteOpen(false)
    setIsSidebarOpen(false)
    setIsNodeConfigOpen(false)
  }, [workflow?.id])

  useEffect(() => {
    setNodes((currentNodes) => applyRunStateToNodes(currentNodes, activeRun))
  }, [activeRun, setNodes])

  useEffect(() => {
    setNodes((currentNodes) => {
      let changed = false

      const nextNodes = currentNodes.map((node) => {
        const currentData = node.data as FlowNodeData
        const decoratedData = decorateNodeData(
          {
            type: String(node.type ?? "agent"),
            label: currentData.label,
            description: currentData.description,
            config: currentData.config,
            agentId: currentData.agentId,
            toolId: currentData.toolId,
            workflowId: currentData.workflowId,
          },
          { agents: agentOptions, tools: toolOptions, workflows: workflowOptions, trigger: workflowMeta.trigger },
        )

        const nextData = {
          ...currentData,
          ...decoratedData,
          status: currentData.status,
          tokens: currentData.tokens,
          message: currentData.message,
          latestError: currentData.latestError,
          errorCount: currentData.errorCount,
        } satisfies FlowNodeData

        if (JSON.stringify(nextData) === JSON.stringify(currentData)) {
          return node
        }

        changed = true
        return {
          ...node,
          data: nextData,
        }
      })

      return changed ? nextNodes : currentNodes
    })
  }, [agentOptions, setNodes, toolOptions, workflowMeta.trigger, workflowOptions])

  useEffect(() => {
    onActionStateChange?.({
      saveDisabled,
      savePending,
    })
  }, [onActionStateChange, saveDisabled, savePending])

  useEffect(() => {
    onDirtyChange?.(isDirty)
  }, [isDirty, onDirtyChange])

  useEffect(() => {
    if (!selectedNodeId) {
      setIsNodeConfigOpen(false)
    }
  }, [selectedNodeId])

  const onConnect = useCallback(
    (params: Connection) =>
      setEdges((currentEdges) =>
        addEdge(
          {
            ...params,
            animated: true,
            style: { stroke: "oklch(0.65 0.2 265)" },
            markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
          },
          currentEdges,
        ),
      ),
    [setEdges],
  )

  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData("application/reactflow", nodeType)
    event.dataTransfer.effectAllowed = "move"
  }

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = "move"
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()

      const type = event.dataTransfer.getData("application/reactflow")
      if (!type || !reactFlowWrapper.current || !reactFlowInstance) return

      const reactFlowBounds = reactFlowWrapper.current.getBoundingClientRect()
      const position = (
        reactFlowInstance as {
          screenToFlowPosition: (pos: { x: number; y: number }) => { x: number; y: number }
        }
      ).screenToFlowPosition({
        x: event.clientX - reactFlowBounds.left,
        y: event.clientY - reactFlowBounds.top,
      })

      const label =
        type === "security-agent"
          ? "安全角色"
          : type.includes("agent")
            ? defaultLabelForNodeType("agent")
            : defaultLabelForNodeType(type)
      const nodeType = type.includes("agent") ? "agent" : normalizeNodeType(type)
      const boundAgent = defaultAgentBindingForPaletteType(type, agentOptions)
      const newNodeId = getId()

      setNodes((currentNodes) =>
        currentNodes.concat({
          id: newNodeId,
          type: nodeType,
          position,
          data: {
            ...decorateNodeData(
              {
                type: nodeType,
                label,
                description: null,
                config: null,
                agentId: boundAgent?.id,
              },
              {
                agents: agentOptions,
                tools: toolOptions,
                workflows: workflowOptions,
                trigger: workflowMeta.trigger,
              },
            ),
          },
        }),
      )
      setSelectedNodeId(newNodeId)
      setIsNodeConfigOpen(true)
    },
    [agentOptions, reactFlowInstance, setNodes, toolOptions, workflowMeta.trigger, workflowOptions],
  )

  const selectedNode = useMemo(
    () => {
      const matchedNode = nodes.find((node) => node.id === selectedNodeId)
      if (!matchedNode) return undefined
      const nodeData = matchedNode.data as FlowNodeData | undefined
      return {
        id: selectedNodeId as string,
        type: String(matchedNode.type ?? "agent"),
        label: String(nodeData?.label ?? "未命名节点"),
        description: nodeData?.description ?? null,
        config: nodeData?.config ?? null,
        agentId: nodeData?.agentId ?? undefined,
        toolId: nodeData?.toolId ?? undefined,
        workflowId: nodeData?.workflowId ?? undefined,
      }
    },
    [nodes, selectedNodeId],
  )

  const updateSelectedNodeData = useCallback(
    (patch: Partial<FlowNodeData>) => {
      if (!selectedNodeId) return
      setNodes((currentNodes) =>
        currentNodes.map((node) =>
          node.id === selectedNodeId
            ? {
                ...node,
                data: {
                  ...(node.data as FlowNodeData),
                  ...patch,
                } satisfies FlowNodeData,
              }
            : node,
        ),
      )
    },
    [selectedNodeId, setNodes],
  )

  const updateSelectedNodeConfig = useCallback(
    (key: string, value?: string | null) => {
      if (!selectedNodeId) return

      setNodes((currentNodes) =>
        currentNodes.map((node) => {
          if (node.id !== selectedNodeId) return node

          const currentData = node.data as FlowNodeData
          const nextConfig = { ...(currentData.config ?? {}) }

          if (value === null || value === undefined || value === "") {
            delete nextConfig[key]
          } else {
            nextConfig[key] = value
          }

          return {
            ...node,
            data: {
              ...currentData,
              config: Object.keys(nextConfig).length > 0 ? nextConfig : null,
            } satisfies FlowNodeData,
          }
        }),
      )
    },
    [selectedNodeId, setNodes],
  )

  const handleSave = useCallback(async () => {
    if (saveDisabled) return
    const payload = buildDraftPayload({ workflowMeta, nodes, edges })

    if (workflow?.id) {
      await updateWorkflow.mutateAsync({ workflowId: workflow.id, payload })
      setSavedSnapshot(serializeDraftPayload(payload))
      return
    }

    const response = await createWorkflow.mutateAsync(payload)
    setSavedSnapshot(serializeDraftPayload(payload))
    onWorkflowCreated?.(response.workflow)
  }, [
    createWorkflow,
    edges,
    nodes,
    onWorkflowCreated,
    saveDisabled,
    updateWorkflow,
    workflowMeta,
    workflow?.id,
  ])

  const handleSetEnabled = useCallback(
    async (enabled: boolean) => {
      if (savePending || !workflow?.id || (!canEditDefinition && !isBasicWorkflow)) return

      const nextMeta = {
        ...workflowMeta,
        status: enabled ? "active" : "paused",
      }
      const payload = buildDraftPayload({ workflowMeta: nextMeta, nodes, edges })

      await updateWorkflow.mutateAsync({ workflowId: workflow.id, payload })
      setWorkflowMeta(nextMeta)
      setSavedSnapshot(serializeDraftPayload(payload))
    },
    [canEditDefinition, edges, isBasicWorkflow, nodes, savePending, updateWorkflow, workflow, workflowMeta],
  )

  const handleTickRun = async (runId: string) => {
    await tickWorkflowRun.mutateAsync(runId)
    await Promise.all([runsQuery.refetch(), monitorQuery.refetch()])
  }

  const onNodeClick: NodeMouseHandler = (_, node) => {
    setSelectedNodeId(node.id)
    setIsNodeConfigOpen(true)
  }

  useImperativeHandle(
    ref,
    () => ({
      save: handleSave,
      setEnabled: handleSetEnabled,
    }),
    [handleSave, handleSetEnabled],
  )

  return (
    <div className="relative flex h-full min-h-0 min-w-0 overflow-hidden">
      <WorkflowNodeConfigDialog
        open={isNodeConfigOpen}
        onOpenChange={(open) => {
          setIsNodeConfigOpen(open)
          if (!open) {
            setSelectedNodeId(undefined)
          }
        }}
        selectedNode={selectedNode}
        workflowMeta={workflowMeta}
        agents={agentOptions}
        workflows={workflowOptions.filter((item) => item.id !== workflow?.id)}
        canEditConfiguration={canEditDefinition}
        onTriggerChange={(trigger) => {
          setWorkflowMeta((current) => ({ ...current, trigger }))
        }}
        onNodeLabelChange={(label) => {
          updateSelectedNodeData({ label })
        }}
        onNodeDescriptionChange={(description) => {
          updateSelectedNodeData({ description: description || null })
        }}
        onNodeAgentChange={(agentId) => {
          const boundAgent = findAgentById(agentOptions, agentId)
          updateSelectedNodeData({
            agentId: agentId ?? null,
            agentName: boundAgent?.name ?? null,
            agentType: boundAgent?.type ?? undefined,
          })
        }}
        onNodeWorkflowChange={(workflowId) => {
          const boundWorkflow = findWorkflowById(workflowOptions, workflowId)
          updateSelectedNodeData({
            workflowId: workflowId ?? null,
            workflowName: boundWorkflow?.name ?? null,
          })
        }}
        onNodeConfigChange={updateSelectedNodeConfig}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={cn(
          "absolute top-4 z-20 w-28 justify-center shadow-sm",
          isPaletteOpen ? "pointer-events-none opacity-0" : "left-4",
        )}
        onClick={() => setIsPaletteOpen((current) => !current)}
      >
        {isPaletteOpen ? <ChevronLeft className="mr-2 size-4" /> : <ChevronRight className="mr-2 size-4" />}
        {isPaletteOpen ? "收起组件栏" : "展开组件栏"}
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={cn(
          "absolute top-4 z-20 w-28 justify-center shadow-sm",
          isSidebarOpen ? "pointer-events-none opacity-0" : "right-4",
        )}
        onClick={() => setIsSidebarOpen((current) => !current)}
      >
        {isSidebarOpen ? <ChevronRight className="mr-2 size-4" /> : <ChevronLeft className="mr-2 size-4" />}
        {isSidebarOpen ? "收起侧栏" : "展开侧栏"}
      </Button>
      <div
        className={cn(
          "absolute inset-y-0 left-0 z-10 w-[280px] overflow-hidden border-r border-transparent bg-card shadow-lg transition-transform duration-300 ease-out",
          isPaletteOpen ? "translate-x-0 border-border" : "-translate-x-full",
        )}
      >
        {isPaletteOpen ? (
          <div className="flex h-full min-h-0 flex-col">
            <div className="flex justify-end border-b border-border px-4 py-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-28 justify-center"
                onClick={() => setIsPaletteOpen(false)}
              >
                <ChevronLeft className="mr-2 size-4" />
                收起组件栏
              </Button>
            </div>
            <div className="min-h-0 flex-1">
              <NodePanel onDragStart={onDragStart} canEdit={canEditDefinition} />
            </div>
          </div>
        ) : null}
      </div>
      <div ref={reactFlowWrapper} className="h-full min-h-0 min-w-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={setReactFlowInstance}
          onNodeClick={onNodeClick}
          onPaneClick={() => {
            setSelectedNodeId(undefined)
            setIsNodeConfigOpen(false)
          }}
          onDrop={onDrop}
          onDragOver={onDragOver}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
          className="h-full bg-background"
        >
          <Background />
          <MiniMap />
          <Controls />
        </ReactFlow>
      </div>
      <div
        className={cn(
          "absolute inset-y-0 right-0 z-10 w-[420px] overflow-hidden border-l border-transparent bg-card shadow-lg transition-transform duration-300 ease-out",
          isSidebarOpen ? "translate-x-0 border-border" : "translate-x-full",
        )}
      >
        {isSidebarOpen ? (
          <div className="flex h-full min-h-0 flex-col">
            <div className="border-b border-border px-4 py-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-28 justify-center"
                onClick={() => setIsSidebarOpen(false)}
              >
                <ChevronRight className="mr-2 size-4" />
                收起侧边栏
              </Button>
            </div>
            <div className="min-h-0 flex-1">
              <WorkflowInspector
                workflowId={workflow?.id}
                workflowMeta={workflowMeta}
                selectedNode={selectedNode}
                runs={liveRuns}
                isRunsLoading={runsQuery.isLoading}
                isRunsFetching={runsQuery.isFetching}
                monitor={monitorQuery.data}
                isMonitorLoading={monitorQuery.isLoading}
                isMonitorFetching={monitorQuery.isFetching}
                tickingRunId={tickWorkflowRun.isPending ? tickWorkflowRun.variables ?? null : null}
                onWorkflowMetaChange={(patch) => {
                  setWorkflowMeta((current) => ({ ...current, ...patch }))
                }}
                onRefreshRuns={() => {
                  void Promise.all([runsQuery.refetch(), monitorQuery.refetch()])
                }}
                onTickRun={(runId) => {
                  void handleTickRun(runId)
                }}
                canEditConfiguration={canEditDefinition}
                canTickRun={canTickRun}
              />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
})
