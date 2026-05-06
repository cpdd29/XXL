export type KnowledgeVaultType = "shared" | "tenant"
export type KnowledgeVaultSourceType = "obsidian_fs" | "managed_fs" | "external_obsidian_fs"
export type KnowledgeVaultSyncMode = "manual" | "scheduled"
export type KnowledgeVaultSyncStatus =
  | "never_synced"
  | "idle"
  | "running"
  | "success"
  | "failed"
  | "partial"
  | "disabled"

export interface KnowledgeVaultRegistry {
  vaultId: string
  vaultName: string
  vaultType: KnowledgeVaultType
  tenantId: string | null
  tenantName: string | null
  sourceType: KnowledgeVaultSourceType
  localPath: string
  enabled: boolean
  syncMode: KnowledgeVaultSyncMode
  lastSyncAt: string | null
  lastSyncStatus: KnowledgeVaultSyncStatus
  remark: string | null
  metadata: Record<string, unknown>
}

export interface CreateKnowledgeVaultRequest {
  vaultName: string
  vaultType: KnowledgeVaultType
  tenantId?: string | null
  tenantName?: string | null
  sourceType?: KnowledgeVaultSourceType
  localPath?: string | null
  enabled?: boolean
  syncMode?: KnowledgeVaultSyncMode
  remark?: string | null
  metadata?: Record<string, unknown>
}

export interface UpdateKnowledgeVaultRequest {
  vaultName?: string
  tenantId?: string | null
  tenantName?: string | null
  sourceType?: KnowledgeVaultSourceType | null
  localPath?: string
  enabled?: boolean
  syncMode?: KnowledgeVaultSyncMode
  remark?: string | null
  metadata?: Record<string, unknown> | null
}

export interface KnowledgeVaultListResponse {
  items: KnowledgeVaultRegistry[]
  total: number
  updatedAt: string | null
}

export interface KnowledgeVaultActionResponse {
  ok: boolean
  message: string
  vault: KnowledgeVaultRegistry
}

export interface KnowledgeVaultDeleteResponse {
  ok: boolean
  message: string
  vaultId: string
}

export interface KnowledgeImportFileInput {
  fileName: string
  content: string
}

export interface ImportKnowledgeVaultRequest {
  files: KnowledgeImportFileInput[]
}

export interface KnowledgeVaultImportResponse {
  ok: boolean
  message: string
  vaultId: string
  vaultPath: string
  importedFiles: string[]
  totalFiles: number
}

export interface RenameKnowledgeVaultEntryRequest {
  path: string
  newName: string
}

export interface DeleteKnowledgeVaultEntryRequest {
  path: string
}

export interface CreateKnowledgeVaultFolderRequest {
  parentPath?: string | null
  name: string
}

export interface KnowledgeVaultEntryActionResponse {
  ok: boolean
  message: string
  vaultId: string
  entryKind: "file" | "folder"
  path: string
  nextPath: string | null
}

export interface KnowledgeVaultValidationResponse {
  ok: boolean
  message: string
  vaultId: string
  sourceType: KnowledgeVaultSourceType
  localPath: string
  markdownFileCount: number
  sampleFiles: string[]
  checkedAt: string
}

export interface KnowledgeMarkdownFile {
  absolutePath: string
  relativePath: string
  fileName: string
  checksum: string
  updatedAt: string
  sizeBytes: number
  rawMarkdown: string
}

export interface KnowledgeVaultScanResult {
  vaultPath: string
  fileCount: number
  directories: string[]
  items: KnowledgeMarkdownFile[]
}

export type KnowledgeSyncTriggerType = "manual" | "scheduled"
export type KnowledgeSyncJobStatus = "running" | "success" | "failed" | "partial" | "cancelled"

export interface KnowledgeSyncJob {
  syncJobId: string
  vaultId: string
  tenantId: string | null
  triggerType: KnowledgeSyncTriggerType
  status: KnowledgeSyncJobStatus
  scannedFiles: number
  addedFiles: number
  updatedFiles: number
  deletedFiles: number
  addedChunks: number
  updatedChunks: number
  deletedChunks: number
  startedAt: string | null
  finishedAt: string | null
  errorMessage: string | null
  metadata: Record<string, unknown>
}

export interface CreateKnowledgeSyncJobRequest {
  vaultId: string
  triggerType?: KnowledgeSyncTriggerType
  forceFullScan?: boolean
  metadata?: Record<string, unknown>
}

export interface KnowledgeSyncJobListResponse {
  items: KnowledgeSyncJob[]
  total: number
  updatedAt: string | null
}

export interface KnowledgeSyncJobActionResponse {
  ok: boolean
  message: string
  job: KnowledgeSyncJob
}

export type KnowledgeDocumentStatus = "active" | "archived" | "deleted"
export type KnowledgeChunkEmbeddingStatus = "pending" | "ready" | "failed" | "skipped"

export interface KnowledgeDocument {
  documentId: string
  vaultId: string
  tenantId: string | null
  scope: KnowledgeVaultType
  sourcePath: string
  fileName: string
  title: string
  category: string | null
  tags: string[]
  aliases: string[]
  rawMarkdown: string
  normalizedText: string
  frontmatter: Record<string, unknown>
  links: string[]
  checksum: string | null
  version: number
  status: KnowledgeDocumentStatus
  createdAt: string | null
  updatedAt: string | null
  sourceUpdatedAt: string | null
}

export interface KnowledgeChunk {
  chunkId: string
  documentId: string
  vaultId: string
  tenantId: string | null
  scope: KnowledgeVaultType
  title: string
  headingPath: string | null
  summary: string | null
  content: string
  tags: string[]
  sourcePath: string
  chunkIndex: number
  tokenEstimate: number | null
  embeddingStatus: KnowledgeChunkEmbeddingStatus
  createdAt: string | null
  updatedAt: string | null
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocument[]
  total: number
  updatedAt: string | null
}

export interface KnowledgeDocumentDetailResponse {
  document: KnowledgeDocument
  chunks: KnowledgeChunk[]
}

export type KnowledgeScene = "reception" | "dispatch" | "general"

export interface KnowledgeRetrievalLog {
  retrievalLogId: string
  tenantId: string
  query: string
  scene: KnowledgeScene
  hitCount: number
  tenantHitCount: number
  sharedHitCount: number
  topDocumentIds: string[]
  topChunkIds: string[]
  requestSource: string | null
  traceId: string | null
  createdAt: string | null
  metadata: Record<string, unknown>
}

export interface KnowledgeRetrievalLogListResponse {
  items: KnowledgeRetrievalLog[]
  total: number
  updatedAt: string | null
}
