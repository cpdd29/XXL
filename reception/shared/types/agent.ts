export type AgentStatus =
  | 'idle'
  | 'running'
  | 'waiting'
  | 'busy'
  | 'degraded'
  | 'offline'
  | 'maintenance'
  | 'error'

export const AGENT_TYPES = [
  'conversation',
  'task_dispatcher',
  'workflow_planner',
  'memory',
  'security',
  'security_guardian',
  'intent',
  'search',
  'write',
  'output',
  'default',
] as const

export type AgentType = (typeof AGENT_TYPES)[number]
export type AgentRuntimeState = 'online' | 'degraded' | 'offline' | 'unknown'

export const AGENT_TYPE_LABELS: Record<AgentType, string> = {
  conversation: '对话',
  task_dispatcher: '任务分发',
  workflow_planner: '工作流规划',
  memory: '记忆管理',
  security: '安全检测',
  security_guardian: '安全守卫',
  intent: '意图识别',
  search: '搜索',
  write: '写作',
  output: '输出',
  default: '通用',
}

export type AgentTypeOption = {
  value: AgentType
  label: string
}

export const AGENT_TYPE_OPTIONS: AgentTypeOption[] = AGENT_TYPES.map((value) => ({
  value,
  label: AGENT_TYPE_LABELS[value],
}))

export function isAgentType(value: string): value is AgentType {
  return (AGENT_TYPES as readonly string[]).includes(value)
}

export function getAgentTypeLabel(value: string): string {
  return isAgentType(value) ? AGENT_TYPE_LABELS[value] : `自定义类型 (${value})`
}

export interface AgentConfigSummary {
  status: string
  directory: string | null
  version: string | null
  filesLoaded: string[]
  toolsCount: number
  examplesCount: number
  memoryRulesPresent: boolean
  soulPresent: boolean
  warnings: string[]
}

export interface AgentModelBinding {
  providerKey: string | null
  providerLabel: string | null
  model: string | null
  source: string | null
}

export interface AgentBoundSkill {
  id: string
  name: string
  fileName?: string | null
  format?: string | null
  description?: string | null
  tags?: string[]
}

export interface AgentBoundTool {
  id: string
  name: string
  type: string
  description?: string | null
  source?: string | null
}

export interface AgentBindableTool {
  id: string
  name: string
  type: string
  description: string
  source: string
  enabled: boolean
}

export type AgentWorkflowContract = Readonly<Record<string, unknown>>

export interface Agent {
  id: string
  name: string
  description: string
  type: AgentType
  status: AgentStatus
  enabled: boolean
  tasksCompleted: number
  tasksTotal: number
  avgResponseTime: string
  tokensUsed: number
  tokensLimit: number
  successRate: number
  lastActive: string
  runtimeStatus?: AgentRuntimeState | null
  runtimeStatusReason?: string | null
  routable?: boolean | null
  runtimePriority?: number | null
  lastHeartbeatAt?: string | null
  heartbeatIntervalSeconds?: number | null
  heartbeatTimeoutSeconds?: number | null
  runtimeMetrics?: {
    heartbeatAgeSeconds?: number | null
    lastReportedStatus?: string | null
    source?: string | null
    load?: number | null
    queueDepth?: number | null
  } | null
  configSummary?: AgentConfigSummary | null
  configSnapshot?: Record<string, unknown> | null
  modelBinding?: AgentModelBinding | null
  boundSkillIds?: string[] | null
  boundSkills?: AgentBoundSkill[] | null
  boundToolIds?: string[] | null
  boundTools?: AgentBoundTool[] | null
  readonly agent_workflow_id?: string | null
  readonly input_contract?: AgentWorkflowContract | null
  readonly output_contract?: AgentWorkflowContract | null
  readonly contract_version?: string | null
  readonly agentWorkflowId?: string | null
  readonly inputContract?: AgentWorkflowContract | null
  readonly outputContract?: AgentWorkflowContract | null
  readonly contractVersion?: string | null
  deletable?: boolean | null
  deleteBlockedReason?: string | null
}

export interface AgentRuntimeStatus {
  id: string
  name: string
  status: AgentStatus
  runtimeStatus?: AgentRuntimeState | null
  enabled: boolean
  lastActive: string
  avgResponseTime: string
  tokensUsed: number
  tokensLimit: number
}

export interface AgentListResponse {
  items: Agent[]
  total: number
}

export interface AgentActionResponse {
  ok: boolean
  message: string
  agent: Agent
}

export interface AgentDeleteResponse {
  ok: boolean
  message: string
  agentId: string
}

export interface AgentConfigRequest {
  name: string
  description: string
  type: string
  enabled: boolean
  providerKey?: string | null
  model?: string | null
  skillIds?: string[]
  toolIds?: string[]
  agentWorkflowId?: string | null
  inputContract?: AgentWorkflowContract | null
  outputContract?: AgentWorkflowContract | null
  contractVersion?: string | null
}
