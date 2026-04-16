"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  Panel,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/hooks/use-auth"
import { useWorkflowRealtime } from "@/hooks/use-workflow-realtime"
import { NodePanel } from "./node-panel"
import { WorkflowInspector, type WorkflowEditorMeta } from "./workflow-inspector"
import {
  TriggerNode,
  AgentNode,
  ConditionNode,
  ParallelNode,
  MergeNode,
  ToolNode,
  TransformNode,
  OutputNode,
  AggregateNode,
} from "./nodes"
import {
  useCreateWorkflow,
  useRunWorkflow,
  useWorkflowMonitor,
  useTickWorkflowRun,
  useUpdateWorkflow,
  useWorkflowRuns,
} from "@/hooks/use-workflows"
import { useAgents } from "@/hooks/use-agents"
import type {
  CreateWorkflowRequest,
  Workflow,
  WorkflowNodeType,
  WorkflowRun,
} from "@/types"
import { Play, Save } from "lucide-react"

const nodeTypes: NodeTypes = {
  trigger: TriggerNode,
  agent: AgentNode,
  condition: ConditionNode,
  parallel: ParallelNode,
  merge: MergeNode,
  tool: ToolNode,
  transform: TransformNode,
  output: OutputNode,
  aggregate: AggregateNode,
}

type FlowNodeData = {
  label?: string
  agentType?: string
  agentId?: string | null
  status?: "idle" | "running" | "waiting" | "completed" | "error"
  tokens?: number
}

const defaultWorkflowMeta: WorkflowEditorMeta = {
  name: "客户服务工作流",
  description: "处理用户咨询并聚合结果",
  version: "v1.0",
  status: "draft",
  trigger: {
    type: "message",
    keyword: "搜索, 写作, 帮助",
    cron: null,
    webhookPath: null,
    internalEvent: null,
    description: "默认消息入口，按关键词进入客户服务工作流",
    priority: 100,
    channels: [],
    preferredLanguage: null,
    stepDelaySeconds: 0.6,
    maxDispatchRetry: 6,
    dispatchRetryBackoffSeconds: 2,
    executionTimeoutSeconds: 45,
  },
}

const initialNodes: Node[] = [
  {
    id: "1",
    type: "trigger",
    position: { x: 50, y: 200 },
    data: { label: "消息触发" },
  },
  {
    id: "2",
    type: "agent",
    position: { x: 280, y: 120 },
    data: { label: "安全检测", agentType: "security", status: "idle", agentId: "2" },
  },
  {
    id: "3",
    type: "agent",
    position: { x: 280, y: 280 },
    data: { label: "意图识别", agentType: "intent", status: "idle", agentId: "1" },
  },
  {
    id: "4",
    type: "condition",
    position: { x: 520, y: 200 },
    data: { label: "意图分支" },
  },
  {
    id: "5",
    type: "agent",
    position: { x: 760, y: 120 },
    data: { label: "搜索 Agent", agentType: "search", status: "idle", agentId: "3" },
  },
  {
    id: "6",
    type: "agent",
    position: { x: 760, y: 280 },
    data: { label: "写作 Agent", agentType: "write", status: "idle", agentId: "4" },
  },
  {
    id: "7",
    type: "merge",
    position: { x: 1000, y: 200 },
    data: { label: "结果合流" },
  },
  {
    id: "8",
    type: "output",
    position: { x: 1240, y: 200 },
    data: { label: "发送结果", agentType: "output", agentId: "6" },
  },
]

const initialEdges: Edge[] = [
  {
    id: "e1-2",
    source: "1",
    target: "2",
    animated: true,
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  },
  {
    id: "e1-3",
    source: "1",
    target: "3",
    animated: true,
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  },
  {
    id: "e2-4",
    source: "2",
    target: "4",
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  },
  {
    id: "e3-4",
    source: "3",
    target: "4",
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  },
  {
    id: "e4-5",
    source: "4",
    sourceHandle: "true",
    target: "5",
    style: { stroke: "oklch(0.55 0.22 160)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.55 0.22 160)" },
  },
  {
    id: "e4-6",
    source: "4",
    sourceHandle: "false",
    target: "6",
    style: { stroke: "oklch(0.55 0.22 25)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.55 0.22 25)" },
  },
  {
    id: "e5-7",
    source: "5",
    target: "7",
    animated: true,
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  },
  {
    id: "e6-7",
    source: "6",
    target: "7",
    style: { stroke: "oklch(0.65 0.2 265)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.65 0.2 265)" },
  },
  {
    id: "e7-8",
    source: "7",
    target: "8",
    animated: true,
    style: { stroke: "oklch(0.55 0.22 160)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "oklch(0.55 0.22 160)" },
  },
]

let nextNodeId = 9

const getId = () => `${nextNodeId++}`

function getAgentType(label: string) {
  if (label.includes("安全")) return "security"
  if (label.includes("意图")) return "intent"
  if (label.includes("搜索")) return "search"
  if (label.includes("写作")) return "write"
  if (label.includes("发送")) return "output"
  return "default"
}

function normalizeNodeType(type?: string | null): WorkflowNodeType {
  if (type === "aggregate") return "merge"
  return (type ?? "agent") as WorkflowNodeType
}

function defaultLabelForNodeType(type: string) {
  const labelByType: Record<string, string> = {
    trigger: "触发节点",
    agent: "Agent 节点",
    condition: "条件节点",
    parallel: "并行分发",
    merge: "结果合流",
    tool: "工具节点",
    transform: "转换节点",
    output: "发送结果",
  }
  return labelByType[type] ?? `新${type}节点`
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

function toReactFlowNodes(workflow?: Workflow): Node[] {
  if (!workflow) return initialNodes

  return workflow.nodes.map((node) => ({
    id: node.id,
    type: normalizeNodeType(node.type),
    position: { x: node.x, y: node.y },
    data: {
      label: node.label,
      agentType: node.type === "agent" ? getAgentType(node.label) : undefined,
      agentId: node.agentId ?? undefined,
      status: "idle",
      tokens: 0,
    } satisfies FlowNodeData,
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

function applyRunStateToNodes(currentNodes: Node[], run?: WorkflowRun | null): Node[] {
  const runNodesById = new Map((run?.nodes ?? []).map((node) => [node.id, node]))
  let changed = false

  const nextNodes = currentNodes.map((node) => {
    const runNode = runNodesById.get(node.id)
    const currentData = node.data as FlowNodeData
    const nextStatus = runNode?.status ?? "idle"
    const nextTokens = runNode?.tokens ?? 0

    if (currentData.status === nextStatus && currentData.tokens === nextTokens) {
      return node
    }

    changed = true
    return {
      ...node,
      data: {
        ...currentData,
        status: nextStatus,
        tokens: nextTokens,
      } satisfies FlowNodeData,
    }
  })

  return changed ? nextNodes : currentNodes
}

interface WorkflowEditorProps {
  workflow?: Workflow
}

export function WorkflowEditor({ workflow }: WorkflowEditorProps) {
  const { hasPermission } = useAuth()
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [reactFlowInstance, setReactFlowInstance] = useState<unknown>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string>()
  const [workflowMeta, setWorkflowMeta] = useState<WorkflowEditorMeta>(defaultWorkflowMeta)

  const createWorkflow = useCreateWorkflow()
  const updateWorkflow = useUpdateWorkflow()
  const runWorkflow = useRunWorkflow()
  const tickWorkflowRun = useTickWorkflowRun()
  const runsQuery = useWorkflowRuns(workflow?.id)
  const monitorQuery = useWorkflowMonitor(workflow?.id)
  const { data: agentsData } = useAgents()
  const { runs: realtimeRuns } = useWorkflowRealtime({ workflowId: workflow?.id })
  const canEditDefinition = hasPermission("workflows:definition:write")
  const canRunWorkflow = hasPermission("workflows:run:create")
  const canTickRun = hasPermission("workflows:run:tick")
  const liveRuns = useMemo<WorkflowRun[]>(
    () => (realtimeRuns.length > 0 ? realtimeRuns : runsQuery.data?.items ?? []),
    [realtimeRuns, runsQuery.data?.items],
  )
  const activeRun = liveRuns[0] ?? null

  useEffect(() => {
    setNodes(toReactFlowNodes(workflow))
    setEdges(toReactFlowEdges(workflow))
    setWorkflowMeta(toWorkflowMeta(workflow))
    setSelectedNodeId(undefined)
  }, [workflow, setNodes, setEdges])

  useEffect(() => {
    setNodes((currentNodes) => applyRunStateToNodes(currentNodes, activeRun))
  }, [activeRun, setNodes])

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

      const label = type.includes("agent") ? type.replace("-agent", " Agent") : defaultLabelForNodeType(type)
      const nodeType = type.includes("agent") ? "agent" : normalizeNodeType(type)

      setNodes((currentNodes) =>
        currentNodes.concat({
          id: getId(),
          type: nodeType,
          position,
          data: {
            label,
            agentType: nodeType === "agent" ? getAgentType(label) : undefined,
            agentId: undefined,
            status: "idle",
          } satisfies FlowNodeData,
        }),
      )
    },
    [reactFlowInstance, setNodes],
  )

  const selectedNode = useMemo(
    () =>
      nodes.find((node) => node.id === selectedNodeId)
        ? {
            id: selectedNodeId as string,
            type: String(nodes.find((node) => node.id === selectedNodeId)?.type ?? "agent"),
            label: String(
              (nodes.find((node) => node.id === selectedNodeId)?.data as FlowNodeData | undefined)?.label ??
                "未命名节点",
            ),
            agentId:
              (nodes.find((node) => node.id === selectedNodeId)?.data as FlowNodeData | undefined)?.agentId ??
              undefined,
          }
        : undefined,
    [nodes, selectedNodeId],
  )

  const buildPayload = (): CreateWorkflowRequest => {
    const payloadNodes = nodes.map((node) => ({
      id: node.id,
      type: (node.type ?? "agent") as WorkflowNodeType,
      label: String((node.data as FlowNodeData | undefined)?.label ?? "未命名节点"),
      x: node.position.x,
      y: node.position.y,
      agentId: (node.data as FlowNodeData | undefined)?.agentId ?? null,
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

  const handleSave = async () => {
    const payload = buildPayload()

    if (workflow?.id) {
      await updateWorkflow.mutateAsync({ workflowId: workflow.id, payload })
      return
    }

    await createWorkflow.mutateAsync(payload)
  }

  const handleRun = async () => {
    if (!workflow?.id) return
    await runWorkflow.mutateAsync(workflow.id)
    await Promise.all([runsQuery.refetch(), monitorQuery.refetch()])
  }

  const handleTickRun = async (runId: string) => {
    await tickWorkflowRun.mutateAsync(runId)
    await Promise.all([runsQuery.refetch(), monitorQuery.refetch()])
  }

  const onNodeClick: NodeMouseHandler = (_, node) => {
    setSelectedNodeId(node.id)
  }

  return (
    <div className="flex h-full min-h-0 min-w-0">
      <NodePanel onDragStart={onDragStart} />
      <div ref={reactFlowWrapper} className="min-h-0 min-w-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={setReactFlowInstance}
          onNodeClick={onNodeClick}
          onPaneClick={() => setSelectedNodeId(undefined)}
          onDrop={onDrop}
          onDragOver={onDragOver}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
          className="bg-background"
        >
          <Background />
          <MiniMap />
          <Controls />
          <Panel position="top-right" className="flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                void handleSave()
              }}
              disabled={!canEditDefinition || createWorkflow.isPending || updateWorkflow.isPending}
            >
              <Save className="mr-2 size-4" />
              保存
            </Button>
            <Button
              size="sm"
              onClick={() => {
                void handleRun()
              }}
              disabled={!canRunWorkflow || !workflow?.id || runWorkflow.isPending}
            >
              <Play className="mr-2 size-4" />
              运行
            </Button>
          </Panel>
        </ReactFlow>
      </div>
      <WorkflowInspector
        workflowId={workflow?.id}
        workflowMeta={workflowMeta}
        selectedNode={selectedNode}
        agents={agentsData?.items ?? []}
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
        onTriggerChange={(trigger) => {
          setWorkflowMeta((current) => ({ ...current, trigger }))
        }}
        onNodeLabelChange={(label) => {
          if (!selectedNodeId) return
          setNodes((currentNodes) =>
            currentNodes.map((node) =>
              node.id === selectedNodeId
                ? {
                    ...node,
                    data: {
                      ...(node.data as FlowNodeData),
                      label,
                    },
                  }
                : node,
            ),
          )
        }}
        onNodeAgentChange={(agentId) => {
          if (!selectedNodeId) return
          setNodes((currentNodes) =>
            currentNodes.map((node) =>
              node.id === selectedNodeId
                ? {
                    ...node,
                    data: {
                      ...(node.data as FlowNodeData),
                      agentId: agentId ?? null,
                    },
                  }
                : node,
            ),
          )
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
  )
}
