export type ExecutorDriverType = "codex_cli" | "claude_code_cli" | "http_runner"
export type ExecutorRunMode = "local" | "remote"
export type ExecutorWorkspacePolicy = "tenant_sandbox" | "fixed_path"
export type ExecutorShellPermission = "read_only" | "limited_exec" | "full_exec"
export type ExecutorApprovalPolicy = "auto" | "confirm_on_risk" | "always_confirm"
export type ExecutorStatus = "unknown" | "online" | "offline" | "degraded"

export interface Executor {
  id: string
  name: string
  description: string
  driverType: ExecutorDriverType
  runMode: ExecutorRunMode
  entry: string
  healthPath: string
  workspacePolicy: ExecutorWorkspacePolicy
  shellPermission: ExecutorShellPermission
  approvalPolicy: ExecutorApprovalPolicy
  blockedCommands: string[]
  timeoutSeconds: number
  enabled: boolean
  status: ExecutorStatus
  lastValidatedAt: string | null
  lastHealthAt: string | null
  lastError: string | null
  validationMessage: string | null
  versionInfo: string | null
  metadata: Record<string, unknown>
}

export interface ExecutorListResponse {
  items: Executor[]
  total: number
  updatedAt: string
}

export interface ExecutorCreateRequest {
  id?: string
  name: string
  description?: string
  driverType: ExecutorDriverType
  runMode: ExecutorRunMode
  entry: string
  healthPath?: string
  workspacePolicy: ExecutorWorkspacePolicy
  shellPermission: ExecutorShellPermission
  approvalPolicy: ExecutorApprovalPolicy
  blockedCommands: string[]
  timeoutSeconds: number
  enabled: boolean
  metadata?: Record<string, unknown>
}

export interface ExecutorUpdateRequest {
  name?: string
  description?: string
  driverType?: ExecutorDriverType
  runMode?: ExecutorRunMode
  entry?: string
  healthPath?: string
  workspacePolicy?: ExecutorWorkspacePolicy
  shellPermission?: ExecutorShellPermission
  approvalPolicy?: ExecutorApprovalPolicy
  blockedCommands?: string[]
  timeoutSeconds?: number
  enabled?: boolean
  metadata?: Record<string, unknown>
}

export interface ExecutorActionResponse {
  ok: boolean
  message: string
  executor: Executor
}

export interface ExecutorDeleteResponse {
  ok: boolean
  message: string
  executorId: string
}

export interface ExecutorCheckResponse {
  ok: boolean
  message: string
  executor: Executor
  details: Record<string, unknown>
}

export interface ExecutorRuntimeLocalDriver {
  driverType: Extract<ExecutorDriverType, "codex_cli" | "claude_code_cli">
  command: string
  installed: boolean
  resolvedPath: string | null
  versionInfo: string | null
}

export interface ExecutorRuntimeCapabilitiesResponse {
  localDrivers: ExecutorRuntimeLocalDriver[]
  availableLocalDriverTypes: Extract<ExecutorDriverType, "codex_cli" | "claude_code_cli">[]
  missingLocalDriverTypes: Extract<ExecutorDriverType, "codex_cli" | "claude_code_cli">[]
  remoteDriverTypes: Extract<ExecutorDriverType, "http_runner">[]
  detectedAt: string
}

export interface ExecutorRuntimeInstallRequest {
  targets?: Extract<ExecutorDriverType, "codex_cli" | "claude_code_cli">[]
}

export interface ExecutorRuntimeInstallResult {
  driverType: Extract<ExecutorDriverType, "codex_cli" | "claude_code_cli">
  command: string
  packageName: string
  attempted: boolean
  installed: boolean
  resolvedPath: string | null
  versionInfo: string | null
  message: string
}

export interface ExecutorRuntimeInstallResponse {
  ok: boolean
  message: string
  results: ExecutorRuntimeInstallResult[]
  capabilities: ExecutorRuntimeCapabilitiesResponse
}
