export type IntakeAdmissionStatus =
  | 'passed'
  | 'pending_verification'
  | 'rejected'
  | 'security_blocked'

export type IntakeReceptionSessionState = 'serving' | 'replied' | 'failed'
export type IntakeOutputSecurityStatus = 'listening' | 'passed' | 'blocked' | 'failed'

export interface IntakeStatusSummary {
  passed: number
  pendingVerification: number
  rejected: number
  securityBlocked: number
}

export interface IntakeAdmissionEvent {
  id: string
  timestamp: string
  status: IntakeAdmissionStatus
  agent: string
  message: string
  tenantId?: string | null
  tenantName?: string | null
  profileId?: string | null
  customerId?: string | null
  personName?: string | null
  channel?: string | null
  platformUserId?: string | null
  serviceCode?: string | null
  sessionId?: string | null
  traceId?: string | null
  missingFields: string[]
  reason?: string | null
}

export interface IntakeKnowledgeHitPreview {
  title: string
  source?: string | null
  summary?: string | null
  scope?: string | null
  score?: number | null
}

export interface IntakeActiveTaskPreview {
  taskId: string
  title?: string | null
  status?: string | null
  summary?: string | null
  updatedAt?: string | null
}

export interface IntakeReceptionSession {
  sessionKey: string
  updatedAt: string
  state: IntakeReceptionSessionState
  agent: string
  latestMessage: string
  tenantId?: string | null
  tenantName?: string | null
  profileId?: string | null
  customerId?: string | null
  personName?: string | null
  channel?: string | null
  platformUserId?: string | null
  serviceCode?: string | null
  sessionId?: string | null
  traceId?: string | null
  currentStage?: string | null
  activeTaskId?: string | null
  activeTask?: IntakeActiveTaskPreview | null
  lastInteractionMode?: string | null
  lastTaskSignal?: string | null
  lastInputSecurityStatus?: IntakeAdmissionStatus | null
  lastOutputSecurityStatus?: IntakeOutputSecurityStatus | null
  outputBlockReason?: string | null
  outputBlockLayer?: string | null
  outputBlockRuleName?: string | null
  outputBlockStatusCode?: number | null
  replyPreview?: string | null
  protocolMode?: string | null
  knowledgeHitCount: number
  knowledgeTenantHits: number
  knowledgeSharedHits: number
  knowledgeHitsPreview: IntakeKnowledgeHitPreview[]
}

export interface IntakeSecurityEvent {
  id: string
  timestamp: string
  status: IntakeAdmissionStatus
  agent: string
  message: string
  blockStage?: string | null
  securityLayer?: string | null
  securityRuleName?: string | null
  statusCode?: number | null
  tenantId?: string | null
  tenantName?: string | null
  profileId?: string | null
  customerId?: string | null
  personName?: string | null
  channel?: string | null
  platformUserId?: string | null
  serviceCode?: string | null
  sessionId?: string | null
  traceId?: string | null
  reason?: string | null
}

export interface IntakeHermesEvent {
  id: string
  timestamp: string
  state: IntakeReceptionSessionState
  agent: string
  message: string
  currentStage?: string | null
  interactionMode?: string | null
  taskSignal?: string | null
  protocolMode?: string | null
  replyPreview?: string | null
  outputSecurityStatus?: IntakeOutputSecurityStatus | null
  outputBlockLayer?: string | null
  outputBlockRuleName?: string | null
  outputBlockStatusCode?: number | null
  activeTaskId?: string | null
  activeTask?: IntakeActiveTaskPreview | null
  tenantId?: string | null
  tenantName?: string | null
  profileId?: string | null
  customerId?: string | null
  personName?: string | null
  channel?: string | null
  platformUserId?: string | null
  serviceCode?: string | null
  sessionId?: string | null
  traceId?: string | null
  reason?: string | null
  knowledgeHitCount: number
  knowledgeTenantHits: number
  knowledgeSharedHits: number
  knowledgeHitsPreview: IntakeKnowledgeHitPreview[]
}

export interface IntakeConsoleOverviewResponse {
  summary: IntakeStatusSummary
  admissionEvents: IntakeAdmissionEvent[]
  securityEvents: IntakeSecurityEvent[]
  hermesEvents: IntakeHermesEvent[]
  receptionSessions: IntakeReceptionSession[]
  activeSessionCount: number
  updatedAt?: string | null
}

export interface IntakeTraceLogEntry {
  id: string
  timestamp: string
  type: string
  agent: string
  message: string
  source: string
  traceId?: string | null
  taskId?: string | null
  workflowRunId?: string | null
  metadata?: Record<string, unknown> | null
}

export interface IntakeTraceDetailResponse {
  traceId: string
  tenantId?: string | null
  tenantName?: string | null
  profileId?: string | null
  customerId?: string | null
  personName?: string | null
  channel?: string | null
  platformUserId?: string | null
  serviceCode?: string | null
  sessionId?: string | null
  items: IntakeTraceLogEntry[]
}
