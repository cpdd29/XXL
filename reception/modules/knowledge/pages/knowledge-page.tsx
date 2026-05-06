"use client"

import { type ChangeEvent, startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import {
  Building2,
  Clock3,
  Database,
  FileText,
  FolderSync,
  HardDrive,
  LibraryBig,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  Upload,
} from "lucide-react"
import {
  useCreateKnowledgeVault,
  useDeleteKnowledgeVault,
  useKnowledgeDocumentDetail,
  useKnowledgeDocuments,
  useImportKnowledgeVaultFiles,
  useKnowledgeRetrievalLogs,
  useKnowledgeSyncJobs,
  useValidateKnowledgeVaultSource,
  useKnowledgeVaults,
  useScanKnowledgeVaultPreview,
  useTriggerKnowledgeVaultSync,
  useUpdateKnowledgeVault,
} from "@/modules/knowledge/hooks/use-knowledge"
import { useProfileTenants } from "@/modules/organization/hooks/use-users"
import { ApiError } from "@/platform/api/errors"
import { toast } from "@/shared/hooks/use-toast"
import type {
  CreateKnowledgeVaultRequest,
  KnowledgeDocument,
  KnowledgeDocumentDetailResponse,
  KnowledgeRetrievalLog,
  KnowledgeSyncJob,
  KnowledgeVaultRegistry,
  KnowledgeVaultScanResult,
  KnowledgeVaultSourceType,
  KnowledgeVaultType,
  KnowledgeVaultValidationResponse,
  UpdateKnowledgeVaultRequest,
  UserTenantOption,
} from "@/shared/types"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/shared/ui/empty"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select"
import { Skeleton } from "@/shared/ui/skeleton"
import { Switch } from "@/shared/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import { Textarea } from "@/shared/ui/textarea"
import { cn } from "@/shared/utils"

type KnowledgeSourceMode = "managed_fs" | "external_obsidian_fs"

type KnowledgeVaultDraft = {
  vaultName: string
  vaultType: KnowledgeVaultType
  sourceType: KnowledgeSourceMode
  tenantId: string
  tenantName: string
  localPath: string
  enabled: boolean
  remark: string
}

type KnowledgePanel = "preview" | "documents" | "jobs" | "logs"

const initialDraft: KnowledgeVaultDraft = {
  vaultName: "",
  vaultType: "tenant",
  sourceType: "managed_fs",
  tenantId: "",
  tenantName: "",
  localPath: "",
  enabled: true,
  remark: "",
}

const syncStatusLabelMap: Record<string, string> = {
  never_synced: "未同步",
  idle: "空闲",
  running: "同步中",
  success: "成功",
  failed: "失败",
  partial: "部分完成",
  disabled: "已停用",
}

const syncStatusClassMap: Record<string, string> = {
  never_synced: "bg-muted text-muted-foreground",
  idle: "bg-secondary text-muted-foreground",
  running: "bg-primary/15 text-primary",
  success: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  partial: "bg-warning/20 text-warning-foreground",
  disabled: "bg-muted text-muted-foreground",
}

const sourceTypeLabelMap: Record<KnowledgeSourceMode | "obsidian_fs", string> = {
  managed_fs: "平台托管",
  external_obsidian_fs: "外部接入",
  obsidian_fs: "外部接入",
}

const syncJobStatusLabelMap: Record<string, string> = {
  running: "执行中",
  success: "成功",
  failed: "失败",
  partial: "部分完成",
  cancelled: "已取消",
}

const syncJobStatusClassMap: Record<string, string> = {
  running: "bg-primary/15 text-primary",
  success: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  partial: "bg-warning/20 text-warning-foreground",
  cancelled: "bg-muted text-muted-foreground",
}

const documentStatusLabelMap: Record<string, string> = {
  active: "生效中",
  archived: "已归档",
  deleted: "已删除",
}

const documentStatusClassMap: Record<string, string> = {
  active: "bg-success/15 text-success",
  archived: "bg-warning/20 text-warning-foreground",
  deleted: "bg-muted text-muted-foreground",
}

function formatTime(value?: string | null): string {
  if (!value) return "--"
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return value
  return new Date(timestamp).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function formatSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function shorten(value: string, limit = 18) {
  if (!value) return "--"
  if (value.length <= limit) return value
  return `${value.slice(0, limit)}...`
}

function normalizeSourceType(sourceType: KnowledgeVaultSourceType): KnowledgeSourceMode {
  return sourceType === "managed_fs" ? "managed_fs" : "external_obsidian_fs"
}

function normalizePathFragment(value: string) {
  const normalized = value.trim().replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^[-_]+|[-_]+$/g, "")
  return normalized || "default"
}

function managedDirectoryName(tenantId: string) {
  return `tenantid_${normalizePathFragment(tenantId)}`
}

function resolveTenantName(tenantId: string, tenantOptions: UserTenantOption[]) {
  return tenantOptions.find((item) => item.id === tenantId)?.name ?? ""
}

function toDraft(vault: KnowledgeVaultRegistry): KnowledgeVaultDraft {
  return {
    vaultName: vault.vaultName,
    vaultType: vault.vaultType,
    sourceType: normalizeSourceType(vault.sourceType),
    tenantId: vault.tenantId ?? "",
    tenantName: vault.tenantName ?? "",
    localPath: vault.localPath,
    enabled: vault.enabled,
    remark: vault.remark ?? "",
  }
}

function toCreatePayload(draft: KnowledgeVaultDraft): CreateKnowledgeVaultRequest {
  return {
    vaultName: draft.vaultName.trim(),
    vaultType: draft.vaultType,
    tenantId: draft.vaultType === "tenant" ? draft.tenantId.trim() || null : null,
    tenantName: draft.vaultType === "tenant" ? draft.tenantName.trim() || null : null,
    sourceType: draft.sourceType,
    localPath: draft.sourceType === "external_obsidian_fs" ? draft.localPath.trim() || null : null,
    enabled: draft.enabled,
    syncMode: "manual",
    remark: draft.remark.trim() || null,
    metadata: {},
  }
}

function toUpdatePayload(draft: KnowledgeVaultDraft): UpdateKnowledgeVaultRequest {
  return {
    vaultName: draft.vaultName.trim(),
    tenantId: draft.vaultType === "tenant" ? draft.tenantId.trim() || null : null,
    tenantName: draft.vaultType === "tenant" ? draft.tenantName.trim() || null : null,
    sourceType: draft.sourceType,
    localPath: draft.sourceType === "external_obsidian_fs" ? draft.localPath.trim() : undefined,
    enabled: draft.enabled,
    remark: draft.remark.trim() || null,
    metadata: {},
  }
}

function getRequiredErrors(draft: KnowledgeVaultDraft) {
  return {
    vaultName: !draft.vaultName.trim(),
    tenantId: draft.vaultType === "tenant" && !draft.tenantId.trim(),
    localPath: draft.sourceType === "external_obsidian_fs" && !draft.localPath.trim(),
  }
}

function syncStatusLabel(value: string) {
  return syncStatusLabelMap[value] ?? (value || "未知")
}

function syncStatusClass(value: string) {
  return syncStatusClassMap[value] ?? "bg-muted text-muted-foreground"
}

function syncJobStatusLabel(value: string) {
  return syncJobStatusLabelMap[value] ?? (value || "未知")
}

function syncJobStatusClass(value: string) {
  return syncJobStatusClassMap[value] ?? "bg-muted text-muted-foreground"
}

function documentStatusLabel(value: string) {
  return documentStatusLabelMap[value] ?? (value || "未知")
}

function documentStatusClass(value: string) {
  return documentStatusClassMap[value] ?? "bg-muted text-muted-foreground"
}

function ReadonlyInfo({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 break-all text-sm text-foreground">{value || "--"}</div>
    </div>
  )
}

function SyncJobTable({ items }: { items: KnowledgeSyncJob[] }) {
  if (items.length === 0) {
    return (
      <Empty className="min-h-[240px] border border-dashed border-border/70 bg-muted/10">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FolderSync />
          </EmptyMedia>
          <EmptyTitle>暂无同步任务</EmptyTitle>
          <EmptyDescription>当前知识仓还没有执行过同步记录。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="overflow-auto rounded-lg border border-border/70">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>状态</TableHead>
            <TableHead>开始时间</TableHead>
            <TableHead>完成时间</TableHead>
            <TableHead>扫描文件</TableHead>
            <TableHead>新增/更新/删除</TableHead>
            <TableHead>Chunk 变更</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.syncJobId}>
              <TableCell>
                <Badge className={cn("border-0", syncJobStatusClass(item.status))}>
                  {syncJobStatusLabel(item.status)}
                </Badge>
              </TableCell>
              <TableCell>{formatTime(item.startedAt)}</TableCell>
              <TableCell>{formatTime(item.finishedAt)}</TableCell>
              <TableCell>{item.scannedFiles}</TableCell>
              <TableCell>
                {item.addedFiles}/{item.updatedFiles}/{item.deletedFiles}
              </TableCell>
              <TableCell>
                {item.addedChunks}/{item.updatedChunks}/{item.deletedChunks}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function KnowledgeDocumentWorkspace({
  items,
  selectedDocumentId,
  onSelect,
  detail,
  loadingList,
  loadingDetail,
}: {
  items: KnowledgeDocument[]
  selectedDocumentId: string | null
  onSelect: (documentId: string) => void
  detail: KnowledgeDocumentDetailResponse | undefined
  loadingList: boolean
  loadingDetail: boolean
}) {
  if (loadingList) {
    return (
      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Skeleton className="h-[320px] w-full" />
        <Skeleton className="h-[320px] w-full" />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <Empty className="min-h-[240px] border border-dashed border-border/70 bg-muted/10">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileText />
          </EmptyMedia>
          <EmptyTitle>还没有同步文档</EmptyTitle>
          <EmptyDescription>先导入或连接知识源，然后执行同步，这里才会出现可检索文档和切片。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="overflow-auto rounded-lg border border-border/70">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>文档</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>更新时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => {
              const isSelected = item.documentId === selectedDocumentId
              return (
                <TableRow
                  key={item.documentId}
                  className={cn("cursor-pointer", isSelected && "bg-primary/5")}
                  onClick={() => onSelect(item.documentId)}
                >
                  <TableCell className="max-w-[220px] align-top">
                    <div className="line-clamp-2 font-medium text-foreground">{item.title}</div>
                    <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.sourcePath}</div>
                  </TableCell>
                  <TableCell className="align-top">
                    <Badge className={cn("border-0", documentStatusClass(item.status))}>
                      {documentStatusLabel(item.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="align-top">{formatTime(item.sourceUpdatedAt || item.updatedAt)}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {loadingDetail ? (
        <Skeleton className="h-[320px] w-full" />
      ) : !detail ? (
        <Empty className="min-h-[320px] border border-dashed border-border/70 bg-muted/10">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FileText />
            </EmptyMedia>
            <EmptyTitle>请选择文档</EmptyTitle>
            <EmptyDescription>选中文档后，这里会展示原始元数据和同步后的切片结果。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="text-base font-semibold text-foreground">{detail.document.title}</div>
                <div className="text-xs text-muted-foreground">{detail.document.sourcePath}</div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={cn("border-0", documentStatusClass(detail.document.status))}>
                  {documentStatusLabel(detail.document.status)}
                </Badge>
                {detail.document.category ? (
                  <Badge variant="secondary">{detail.document.category}</Badge>
                ) : null}
                <Badge variant="secondary">v{detail.document.version}</Badge>
              </div>
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              <ReadonlyInfo label="文件名" value={detail.document.fileName} />
              <ReadonlyInfo label="来源范围" value={detail.document.scope === "shared" ? "通用" : "租户专用"} />
              <ReadonlyInfo label="最后更新时间" value={formatTime(detail.document.sourceUpdatedAt || detail.document.updatedAt)} />
            </div>

            {detail.document.tags.length > 0 ? (
              <div className="mt-4">
                <div className="mb-2 text-xs text-muted-foreground">标签</div>
                <div className="flex flex-wrap gap-2">
                  {detail.document.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {detail.document.aliases.length > 0 ? (
              <div className="mt-4">
                <div className="mb-2 text-xs text-muted-foreground">别名</div>
                <div className="flex flex-wrap gap-2">
                  {detail.document.aliases.map((alias) => (
                    <Badge key={alias} variant="outline">
                      {alias}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {Object.keys(detail.document.frontmatter).length > 0 ? (
              <div className="mt-4">
                <div className="mb-2 text-xs text-muted-foreground">Frontmatter</div>
                <pre className="max-h-48 overflow-auto rounded-lg border border-border/70 bg-background p-3 text-xs text-foreground">
                  {JSON.stringify(detail.document.frontmatter, null, 2)}
                </pre>
              </div>
            ) : null}
          </div>

          <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-foreground">切片结果</div>
              <Badge variant="secondary">{detail.chunks.length} 个 Chunk</Badge>
            </div>
            <div className="mt-4 space-y-3">
              {detail.chunks.map((chunk) => (
                <div key={chunk.chunkId} className="rounded-lg border border-border/70 bg-background p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">
                        #{chunk.chunkIndex + 1} {chunk.headingPath || chunk.title}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        预估 Token：{chunk.tokenEstimate ?? "--"}
                      </div>
                    </div>
                    {chunk.tags.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {chunk.tags.map((tag) => (
                          <Badge key={`${chunk.chunkId}-${tag}`} variant="outline">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  {chunk.summary ? (
                    <div className="mt-3 text-sm text-muted-foreground">{chunk.summary}</div>
                  ) : null}
                  <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-muted/20 p-3 text-xs text-foreground">
                    {chunk.content}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function RetrievalLogTable({ items }: { items: KnowledgeRetrievalLog[] }) {
  if (items.length === 0) {
    return (
      <Empty className="min-h-[240px] border border-dashed border-border/70 bg-muted/10">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Clock3 />
          </EmptyMedia>
          <EmptyTitle>暂无检索日志</EmptyTitle>
          <EmptyDescription>当前租户还没有产生知识检索调用记录。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="overflow-auto rounded-lg border border-border/70">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>查询词</TableHead>
            <TableHead>场景</TableHead>
            <TableHead>命中</TableHead>
            <TableHead>来源</TableHead>
            <TableHead>时间</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.retrievalLogId}>
              <TableCell className="max-w-[300px] whitespace-normal">
                <div className="line-clamp-2 text-sm text-foreground">{item.query}</div>
              </TableCell>
              <TableCell>{item.scene}</TableCell>
              <TableCell>
                {item.hitCount} 条
                <div className="text-xs text-muted-foreground">
                  租户 {item.tenantHitCount} / 通用 {item.sharedHitCount}
                </div>
              </TableCell>
              <TableCell>{item.requestSource || "--"}</TableCell>
              <TableCell>{formatTime(item.createdAt)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function ScanPreviewTable({
  result,
  loading,
}: {
  result: KnowledgeVaultScanResult | null
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (!result) {
    return (
      <Empty className="min-h-[240px] border border-dashed border-border/70 bg-muted/10">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HardDrive />
          </EmptyMedia>
          <EmptyTitle>还没有扫描预览结果</EmptyTitle>
          <EmptyDescription>点击右上角“扫描预览”后，这里会展示当前知识仓扫描到的 Markdown 文件。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-border/70 bg-muted/15 px-3 py-3 text-sm">
        <div className="font-medium text-foreground">扫描目录：{result.vaultPath}</div>
        <div className="mt-1 text-muted-foreground">共识别 {result.fileCount} 个 Markdown 文件</div>
      </div>
      <div className="overflow-auto rounded-lg border border-border/70">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>相对路径</TableHead>
              <TableHead>文件名</TableHead>
              <TableHead>大小</TableHead>
              <TableHead>更新时间</TableHead>
              <TableHead>校验和</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.items.map((item) => (
              <TableRow key={`${item.relativePath}:${item.checksum}`}>
                <TableCell className="max-w-[340px] whitespace-normal">
                  <div className="line-clamp-2 break-all">{item.relativePath}</div>
                </TableCell>
                <TableCell>{item.fileName}</TableCell>
                <TableCell>{formatSize(item.sizeBytes)}</TableCell>
                <TableCell>{formatTime(item.updatedAt)}</TableCell>
                <TableCell>{shorten(item.checksum, 16)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function TenantSelectField({
  value,
  onChange,
  tenantOptions,
  disabled = false,
}: {
  value: string
  onChange: (tenantId: string) => void
  tenantOptions: UserTenantOption[]
  disabled?: boolean
}) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger>
        <SelectValue placeholder={tenantOptions.length > 0 ? "请选择租户" : "暂无可选租户"} />
      </SelectTrigger>
      <SelectContent>
        {tenantOptions.map((item) => (
          <SelectItem key={item.id} value={item.id}>
            {item.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export default function KnowledgePage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const vaultsQuery = useKnowledgeVaults()
  const tenantOptionsQuery = useProfileTenants()
  const createVaultMutation = useCreateKnowledgeVault()
  const updateVaultMutation = useUpdateKnowledgeVault()
  const deleteVaultMutation = useDeleteKnowledgeVault()
  const importFilesMutation = useImportKnowledgeVaultFiles()
  const validateSourceMutation = useValidateKnowledgeVaultSource()
  const scanPreviewMutation = useScanKnowledgeVaultPreview()
  const syncVaultMutation = useTriggerKnowledgeVaultSync()

  const [selectedVaultId, setSelectedVaultId] = useState<string | null>(null)
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [panel, setPanel] = useState<KnowledgePanel>("preview")
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [draft, setDraft] = useState<KnowledgeVaultDraft>(initialDraft)
  const [createDraft, setCreateDraft] = useState<KnowledgeVaultDraft>(initialDraft)
  const [previewResult, setPreviewResult] = useState<{
    vaultId: string
    payload: KnowledgeVaultScanResult
  } | null>(null)
  const [lastImportSummary, setLastImportSummary] = useState<{
    vaultId: string
    importedFiles: string[]
    totalFiles: number
    importedAt: string
  } | null>(null)
  const [validationResult, setValidationResult] = useState<KnowledgeVaultValidationResponse | null>(null)

  const deferredSearch = useDeferredValue(search)
  const vaults = useMemo(() => vaultsQuery.data?.items ?? [], [vaultsQuery.data?.items])
  const tenantOptions = useMemo(() => tenantOptionsQuery.data?.items ?? [], [tenantOptionsQuery.data?.items])

  const sortedVaults = useMemo(() => {
    return [...vaults].sort((left, right) => {
      if (left.enabled !== right.enabled) {
        return left.enabled ? -1 : 1
      }
      if (left.vaultType !== right.vaultType) {
        return left.vaultType === "tenant" ? -1 : 1
      }
      return left.vaultName.localeCompare(right.vaultName, "zh-CN")
    })
  }, [vaults])

  const filteredVaults = useMemo(() => {
    const keyword = deferredSearch.trim().toLowerCase()
    return sortedVaults.filter((item) => {
      if (!keyword) return true
      return [
        item.vaultName,
        item.tenantId ?? "",
        item.tenantName ?? "",
        item.localPath,
      ]
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    })
  }, [deferredSearch, sortedVaults])

  const selectedVault = useMemo(
    () => filteredVaults.find((item) => item.vaultId === selectedVaultId) ?? null,
    [filteredVaults, selectedVaultId],
  )

  const syncJobsQuery = useKnowledgeSyncJobs(
    selectedVault ? { vaultId: selectedVault.vaultId, limit: 20 } : undefined,
    Boolean(selectedVault),
  )
  const documentsQuery = useKnowledgeDocuments(
    selectedVault
      ? {
          vaultId: selectedVault.vaultId,
          tenantId: selectedVault.tenantId ?? undefined,
          scope: selectedVault.vaultType,
          status: "active",
          limit: 100,
        }
      : undefined,
    Boolean(selectedVault),
  )
  const retrievalLogsQuery = useKnowledgeRetrievalLogs(
    selectedVault?.tenantId ? { tenantId: selectedVault.tenantId, limit: 20 } : undefined,
    Boolean(selectedVault?.tenantId),
  )
  const documents = useMemo(() => documentsQuery.data?.items ?? [], [documentsQuery.data?.items])
  const selectedDocument = useMemo(
    () => documents.find((item) => item.documentId === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  )
  const documentDetailQuery = useKnowledgeDocumentDetail(selectedDocument?.documentId ?? null, Boolean(selectedDocument))

  useEffect(() => {
    if (filteredVaults.length === 0) {
      setSelectedVaultId(null)
      return
    }
    if (!selectedVaultId || !filteredVaults.some((item) => item.vaultId === selectedVaultId)) {
      startTransition(() => {
        setSelectedVaultId(filteredVaults[0]?.vaultId ?? null)
      })
    }
  }, [filteredVaults, selectedVaultId])

  useEffect(() => {
    if (selectedVault) {
      setDraft(toDraft(selectedVault))
      return
    }
    setDraft(initialDraft)
  }, [selectedVault])

  useEffect(() => {
    if (documents.length === 0) {
      setSelectedDocumentId(null)
      return
    }
    if (!selectedDocumentId || !documents.some((item) => item.documentId === selectedDocumentId)) {
      startTransition(() => {
        setSelectedDocumentId(documents[0]?.documentId ?? null)
      })
    }
  }, [documents, selectedDocumentId])

  function updateDraftTenant(setter: typeof setDraft | typeof setCreateDraft, tenantId: string) {
    const tenantName = resolveTenantName(tenantId, tenantOptions)
    setter((current) => ({
      ...current,
      tenantId,
      tenantName,
    }))
  }

  async function handleCreateVault() {
    const errors = getRequiredErrors(createDraft)
    if (errors.vaultName || errors.tenantId || errors.localPath) {
      toast({
        title: "请先补全必填项",
        description:
          createDraft.sourceType === "external_obsidian_fs"
            ? "请填写知识仓名称、知识仓类型、租户，以及外接目录。"
            : "请填写知识仓名称、知识仓类型和租户。",
        variant: "destructive",
      })
      return
    }

    try {
      const response = await createVaultMutation.mutateAsync(toCreatePayload(createDraft))
      toast({
        title: "知识仓已创建",
        description: response.message,
      })
      setCreateDialogOpen(false)
      setCreateDraft(initialDraft)
      startTransition(() => {
        setSelectedVaultId(response.vault.vaultId)
      })
    } catch (error) {
      toast({
        title: "创建失败",
        description: error instanceof Error ? error.message : "知识仓创建失败。",
        variant: "destructive",
      })
    }
  }

  async function handleSaveVault() {
    if (!selectedVault) return

    const errors = getRequiredErrors(draft)
    if (errors.vaultName || errors.tenantId || errors.localPath) {
      toast({
        title: "请先补全必填项",
        description:
          draft.sourceType === "external_obsidian_fs"
            ? "请填写知识仓名称、知识仓类型、租户，以及外接目录。"
            : "请填写知识仓名称、知识仓类型和租户。",
        variant: "destructive",
      })
      return
    }

    try {
      const response = await updateVaultMutation.mutateAsync({
        vaultId: selectedVault.vaultId,
        payload: toUpdatePayload(draft),
      })
      toast({
        title: "知识仓已保存",
        description: response.message,
      })
    } catch (error) {
      toast({
        title: "保存失败",
        description: error instanceof Error ? error.message : "知识仓更新失败。",
        variant: "destructive",
      })
    }
  }

  async function handleDeleteVault() {
    if (!selectedVault) return
    if (!window.confirm(`确认删除知识仓「${selectedVault.vaultName}」吗？`)) {
      return
    }
    try {
      await deleteVaultMutation.mutateAsync(selectedVault.vaultId)
      toast({
        title: "知识仓已删除",
        description: `已删除 ${selectedVault.vaultName}`,
      })
      setPreviewResult((current) =>
        current?.vaultId === selectedVault.vaultId ? null : current,
      )
      startTransition(() => {
        setSelectedVaultId(null)
      })
    } catch (error) {
      toast({
        title: "删除失败",
        description: error instanceof Error ? error.message : "知识仓删除失败。",
        variant: "destructive",
      })
    }
  }

  async function handleScanPreview() {
    if (!selectedVault) return
    try {
      const response = await scanPreviewMutation.mutateAsync({
        vaultId: selectedVault.vaultId,
        limit: 80,
      })
      setPreviewResult({
        vaultId: selectedVault.vaultId,
        payload: response,
      })
      setPanel("preview")
      toast({
        title: "扫描预览已更新",
        description: `识别到 ${response.fileCount} 个 Markdown 文件。`,
      })
    } catch (error) {
      toast({
        title: "扫描预览失败",
        description: error instanceof Error ? error.message : "知识仓扫描预览失败。",
        variant: "destructive",
      })
    }
  }

  async function scanPreviewForVault(vaultId: string) {
    const response = await scanPreviewMutation.mutateAsync({
      vaultId,
      limit: 80,
    })
    setPreviewResult({
      vaultId,
      payload: response,
    })
    setPanel("preview")
    return response
  }

  async function triggerSync(vaultId: string) {
    const response = await syncVaultMutation.mutateAsync({
      vaultId,
    })
    setPanel("jobs")
    return response
  }

  async function handleSyncVault() {
    if (!selectedVault) return
    try {
      const response = await triggerSync(selectedVault.vaultId)
      toast({
        title: response.ok ? "同步已完成" : "同步执行失败",
        description: response.message,
        variant: response.ok ? "default" : "destructive",
      })
    } catch (error) {
      const description =
        error instanceof ApiError || error instanceof Error ? error.message : "知识仓同步失败。"
      toast({
        title: "同步失败",
        description,
        variant: "destructive",
      })
    }
  }

  async function handleImportFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ""

    if (!selectedVault || files.length === 0) return

    try {
      const payloadFiles = await Promise.all(
        files.map(async (file) => ({
          fileName: file.name,
          content: await file.text(),
        })),
      )

      const importResponse = await importFilesMutation.mutateAsync({
        vaultId: selectedVault.vaultId,
        payload: {
          files: payloadFiles,
        },
      })

      setLastImportSummary({
        vaultId: selectedVault.vaultId,
        importedFiles: importResponse.importedFiles,
        totalFiles: importResponse.totalFiles,
        importedAt: new Date().toISOString(),
      })
      const syncResponse = await triggerSync(selectedVault.vaultId)
      await scanPreviewForVault(selectedVault.vaultId)
      toast({
        title: "导入完成",
        description: `${importResponse.totalFiles} 个文件已导入，并已触发同步。${syncResponse.message}`,
      })
    } catch (error) {
      toast({
        title: "导入失败",
        description: error instanceof Error ? error.message : "知识文件导入失败。",
        variant: "destructive",
      })
    }
  }

  async function handleValidateSource() {
    if (!selectedVault) return
    if (normalizeSourceType(selectedVault.sourceType) !== "external_obsidian_fs") return
    if (
      draft.sourceType !== normalizeSourceType(selectedVault.sourceType) ||
      draft.localPath.trim() !== selectedVault.localPath
    ) {
      toast({
        title: "请先保存当前外接目录",
        description: "连通性校验基于已保存的外接知识仓配置执行。",
        variant: "destructive",
      })
      return
    }

    try {
      const response = await validateSourceMutation.mutateAsync(selectedVault.vaultId)
      setValidationResult(response)
      toast({
        title: response.ok ? "连通性校验通过" : "连通性校验失败",
        description: response.message,
        variant: response.ok ? "default" : "destructive",
      })
    } catch (error) {
      toast({
        title: "连通性校验失败",
        description: error instanceof Error ? error.message : "外接知识仓校验失败。",
        variant: "destructive",
      })
    }
  }

  const previewForSelected =
    selectedVault && previewResult?.vaultId === selectedVault.vaultId ? previewResult.payload : null
  const selectedSourceTypeLabel = selectedVault ? sourceTypeLabelMap[selectedVault.sourceType] ?? "未知类型" : ""
  const canImportToSelectedVault = selectedVault
    ? normalizeSourceType(selectedVault.sourceType) === "managed_fs"
    : false
  const canValidateSelectedVault = selectedVault
    ? normalizeSourceType(selectedVault.sourceType) === "external_obsidian_fs"
    : false
  const selectedImportSummary =
    selectedVault && lastImportSummary?.vaultId === selectedVault.vaultId ? lastImportSummary : null
  const selectedValidationResult =
    selectedVault && validationResult?.vaultId === selectedVault.vaultId ? validationResult : null
  const createManagedPathHint = createDraft.tenantId ? managedDirectoryName(createDraft.tenantId) : "tenantid_<租户ID>"
  const editManagedPathHint = draft.tenantId ? managedDirectoryName(draft.tenantId) : "tenantid_<租户ID>"

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden bg-background">
      <input
        ref={fileInputRef}
        type="file"
        accept=".md,.markdown,text/markdown"
        multiple
        className="sr-only"
        onChange={(event) => void handleImportFiles(event)}
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="text-2xl font-semibold tracking-tight text-foreground">知识库管理</div>
            <div className="text-sm text-muted-foreground">
              按租户维护接待层可注入的知识仓，支持平台托管导入和外部知识目录接入。
            </div>
          </div>
          <Button onClick={() => setCreateDialogOpen(true)} className="gap-2">
            <Plus className="size-4" />
            新建知识仓
          </Button>
        </div>

        <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardHeader className="gap-3 border-b border-border/70 pb-4">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-base">知识仓列表</CardTitle>
                <Badge variant="secondary">{filteredVaults.length}</Badge>
              </div>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索名称、租户、本地路径"
                  className="pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-auto p-3">
              {vaultsQuery.isLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, index) => (
                    <Skeleton key={index} className="h-24 w-full" />
                  ))}
                </div>
              ) : filteredVaults.length === 0 ? (
                <Empty className="min-h-[360px] border border-dashed border-border/70 bg-muted/10">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <LibraryBig />
                    </EmptyMedia>
                    <EmptyTitle>还没有知识仓</EmptyTitle>
                    <EmptyDescription>先创建一个租户知识仓，再选择平台托管或外部接入。</EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    <Button onClick={() => setCreateDialogOpen(true)}>新建知识仓</Button>
                  </EmptyContent>
                </Empty>
              ) : (
                <div className="space-y-3">
                  {filteredVaults.map((item) => {
                    const isSelected = item.vaultId === selectedVault?.vaultId
                    const sourceLabel = sourceTypeLabelMap[item.sourceType] ?? "未知类型"
                    return (
                      <button
                        key={item.vaultId}
                        type="button"
                        onClick={() => {
                          setSelectedVaultId(item.vaultId)
                          setPanel("preview")
                        }}
                        className={cn(
                          "w-full rounded-xl border border-border/70 bg-card p-4 text-left transition-colors hover:bg-muted/30",
                          isSelected && "border-primary bg-primary/5 shadow-sm",
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-foreground">{item.vaultName}</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {item.tenantName || item.tenantId || "平台通用知识仓"}
                            </div>
                          </div>
                          <Switch checked={item.enabled} disabled className="pointer-events-none" />
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Badge className="border-0 bg-secondary text-foreground">{sourceLabel}</Badge>
                          <Badge className={cn("border-0", syncStatusClass(item.lastSyncStatus))}>
                            {syncStatusLabel(item.lastSyncStatus)}
                          </Badge>
                        </div>
                        <div className="mt-3 truncate text-xs text-muted-foreground">{item.localPath}</div>
                      </button>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex min-h-0 flex-col gap-4 overflow-hidden">
            {!selectedVault ? (
              <Card className="flex min-h-0 flex-1 items-center justify-center">
                <CardContent className="w-full p-6">
                      <Empty className="min-h-[520px] border border-dashed border-border/70 bg-muted/10">
                        <EmptyHeader>
                          <EmptyMedia variant="icon">
                            <Database />
                          </EmptyMedia>
                          <EmptyTitle>请选择一个知识仓</EmptyTitle>
                      <EmptyDescription>左侧选中知识仓后，可以编辑配置、导入文件、执行同步，并查看扫描预览、同步文档与检索日志。</EmptyDescription>
                        </EmptyHeader>
                      </Empty>
                    </CardContent>
              </Card>
            ) : (
              <>
                <Card className="flex flex-col overflow-hidden">
                  <CardHeader className="border-b border-border/70 pb-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <CardTitle className="text-lg">{selectedVault.vaultName}</CardTitle>
                          <Badge className="border-0 bg-secondary text-foreground">{selectedSourceTypeLabel}</Badge>
                          <Badge className={cn("border-0", syncStatusClass(selectedVault.lastSyncStatus))}>
                            {syncStatusLabel(selectedVault.lastSyncStatus)}
                          </Badge>
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {selectedVault.tenantName || selectedVault.tenantId || "平台通用知识仓"}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {canImportToSelectedVault ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={importFilesMutation.isPending || syncVaultMutation.isPending}
                          >
                            <Upload className="size-4" />
                            {importFilesMutation.isPending ? "导入中..." : "导入文件"}
                          </Button>
                        ) : null}
                        {canValidateSelectedVault ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={handleValidateSource}
                            disabled={validateSourceMutation.isPending}
                          >
                            <Database className={cn("size-4", validateSourceMutation.isPending && "animate-pulse")} />
                            {validateSourceMutation.isPending ? "校验中..." : "校验连通性"}
                          </Button>
                        ) : null}
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-2"
                          onClick={handleScanPreview}
                          disabled={scanPreviewMutation.isPending}
                        >
                          <RefreshCw className={cn("size-4", scanPreviewMutation.isPending && "animate-spin")} />
                          扫描预览
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-2"
                          onClick={handleSyncVault}
                          disabled={syncVaultMutation.isPending}
                        >
                          <FolderSync className={cn("size-4", syncVaultMutation.isPending && "animate-spin")} />
                          手动同步
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-2"
                          onClick={handleSaveVault}
                          disabled={updateVaultMutation.isPending}
                        >
                          <Save className="size-4" />
                          保存
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={handleDeleteVault}
                          disabled={deleteVaultMutation.isPending}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 p-5">
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="vault-name">
                          知识仓名称 <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          id="vault-name"
                          value={draft.vaultName}
                          onChange={(event) =>
                            setDraft((current) => ({ ...current, vaultName: event.target.value }))
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="vault-source-type">
                          知识仓类型 <span className="text-destructive">*</span>
                        </Label>
                        <Select
                          value={draft.sourceType}
                          onValueChange={(value: KnowledgeSourceMode) =>
                            setDraft((current) => ({
                              ...current,
                              sourceType: value,
                              localPath: value === "managed_fs" ? "" : current.localPath,
                            }))
                          }
                        >
                          <SelectTrigger id="vault-source-type">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="managed_fs">平台托管</SelectItem>
                            <SelectItem value="external_obsidian_fs">外部接入</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    {draft.vaultType === "tenant" ? (
                      <div className="space-y-2">
                        <Label>
                          租户 <span className="text-destructive">*</span>
                        </Label>
                        <TenantSelectField
                          value={draft.tenantId}
                          onChange={(tenantId) => updateDraftTenant(setDraft, tenantId)}
                          tenantOptions={tenantOptions}
                        />
                      </div>
                    ) : (
                      <ReadonlyInfo label="租户" value="平台通用" />
                    )}

                    {draft.sourceType === "managed_fs" ? (
                      <div className="grid gap-4 lg:grid-cols-2">
                        <ReadonlyInfo
                          label="系统托管目录"
                          value={draft.tenantId ? editManagedPathHint : "请先选择租户"}
                        />
                        <ReadonlyInfo
                          label="当前落盘路径"
                          value={selectedVault.localPath || "创建后自动生成"}
                        />
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Label htmlFor="vault-local-path">
                          外接目录 <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          id="vault-local-path"
                          value={draft.localPath}
                          onChange={(event) =>
                            setDraft((current) => ({ ...current, localPath: event.target.value }))
                          }
                          placeholder="/absolute/path/to/obsidian-vault"
                        />
                      </div>
                    )}

                    <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
                      <div className="space-y-2">
                        <Label>启用状态</Label>
                        <div className="flex h-10 items-center rounded-md border border-border/70 px-3">
                          <Switch
                            checked={draft.enabled}
                            onCheckedChange={(checked) =>
                              setDraft((current) => ({ ...current, enabled: checked }))
                            }
                          />
                          <span className="ml-3 text-sm text-muted-foreground">
                            {draft.enabled ? "已启用" : "已停用"}
                          </span>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="vault-remark">备注</Label>
                        <Textarea
                          id="vault-remark"
                          value={draft.remark}
                          onChange={(event) =>
                            setDraft((current) => ({ ...current, remark: event.target.value }))
                          }
                          className="min-h-24"
                        />
                      </div>
                    </div>

                    <div className="grid gap-3 lg:grid-cols-4">
                      <ReadonlyInfo label="最后同步状态" value={syncStatusLabel(selectedVault.lastSyncStatus)} />
                      <ReadonlyInfo label="最后同步时间" value={formatTime(selectedVault.lastSyncAt)} />
                      <ReadonlyInfo label="接入方式" value={selectedSourceTypeLabel} />
                      <ReadonlyInfo label="存储目录" value={selectedVault.localPath} />
                    </div>

                    {selectedImportSummary ? (
                      <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-foreground">最近一次导入</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {formatTime(selectedImportSummary.importedAt)}，共导入 {selectedImportSummary.totalFiles} 个文件
                            </div>
                          </div>
                          <Badge className="border-0 bg-primary/15 text-primary">
                            已导入 {selectedImportSummary.totalFiles}
                          </Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {selectedImportSummary.importedFiles.slice(0, 8).map((filePath) => (
                            <Badge key={filePath} variant="secondary" className="max-w-full truncate">
                              {filePath}
                            </Badge>
                          ))}
                          {selectedImportSummary.importedFiles.length > 8 ? (
                            <Badge variant="secondary">+{selectedImportSummary.importedFiles.length - 8}</Badge>
                          ) : null}
                        </div>
                      </div>
                    ) : null}

                    {selectedValidationResult ? (
                      <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-foreground">最近一次连通性校验</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {formatTime(selectedValidationResult.checkedAt)}
                            </div>
                          </div>
                          <Badge
                            className={cn(
                              "border-0",
                              selectedValidationResult.ok
                                ? "bg-success/15 text-success"
                                : "bg-destructive/15 text-destructive",
                            )}
                          >
                            {selectedValidationResult.ok ? "已通过" : "失败"}
                          </Badge>
                        </div>
                        <div className="mt-3 text-sm text-foreground">{selectedValidationResult.message}</div>
                        <div className="mt-3 grid gap-3 lg:grid-cols-3">
                          <ReadonlyInfo label="外接目录" value={selectedValidationResult.localPath} />
                          <ReadonlyInfo label="Markdown 文件数" value={String(selectedValidationResult.markdownFileCount)} />
                          <ReadonlyInfo
                            label="样例文件"
                            value={selectedValidationResult.sampleFiles.slice(0, 3).join(" / ") || "--"}
                          />
                        </div>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>

                <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
                  <CardHeader className="border-b border-border/70 pb-4">
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="text-base">知识仓运行视图</CardTitle>
                      <Tabs value={panel} onValueChange={(value) => setPanel(value as KnowledgePanel)}>
                        <TabsList>
                          <TabsTrigger value="preview">扫描预览</TabsTrigger>
                          <TabsTrigger value="documents">同步文档</TabsTrigger>
                          <TabsTrigger value="jobs">同步任务</TabsTrigger>
                          <TabsTrigger value="logs">检索日志</TabsTrigger>
                        </TabsList>
                      </Tabs>
                    </div>
                  </CardHeader>
                  <CardContent className="min-h-0 flex-1 overflow-auto p-5">
                    <Tabs value={panel} onValueChange={(value) => setPanel(value as KnowledgePanel)}>
                      <TabsContent value="preview" className="mt-0">
                        <ScanPreviewTable result={previewForSelected} loading={scanPreviewMutation.isPending} />
                      </TabsContent>
                      <TabsContent value="documents" className="mt-0">
                        <KnowledgeDocumentWorkspace
                          items={documents}
                          selectedDocumentId={selectedDocumentId}
                          onSelect={setSelectedDocumentId}
                          detail={documentDetailQuery.data}
                          loadingList={documentsQuery.isLoading}
                          loadingDetail={documentDetailQuery.isLoading}
                        />
                      </TabsContent>
                      <TabsContent value="jobs" className="mt-0">
                        {syncJobsQuery.isLoading ? (
                          <div className="space-y-3">
                            <Skeleton className="h-16 w-full" />
                            <Skeleton className="h-52 w-full" />
                          </div>
                        ) : (
                          <SyncJobTable items={syncJobsQuery.data?.items ?? []} />
                        )}
                      </TabsContent>
                      <TabsContent value="logs" className="mt-0">
                        {selectedVault.vaultType === "shared" ? (
                          <Empty className="min-h-[240px] border border-dashed border-border/70 bg-muted/10">
                            <EmptyHeader>
                              <EmptyMedia variant="icon">
                                <Clock3 />
                              </EmptyMedia>
                              <EmptyTitle>通用知识仓不单独按仓展示检索日志</EmptyTitle>
                              <EmptyDescription>
                                当前检索日志按租户记录。通用知识命中会混在各租户的接待检索日志里。
                              </EmptyDescription>
                            </EmptyHeader>
                          </Empty>
                        ) : retrievalLogsQuery.isLoading ? (
                          <div className="space-y-3">
                            <Skeleton className="h-16 w-full" />
                            <Skeleton className="h-52 w-full" />
                          </div>
                        ) : (
                          <RetrievalLogTable items={retrievalLogsQuery.data?.items ?? []} />
                        )}
                      </TabsContent>
                    </Tabs>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        </div>

        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogContent className="max-h-[85vh] overflow-hidden sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle>新建知识仓</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 overflow-y-auto px-1 py-1">
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="create-vault-name">
                    知识仓名称 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="create-vault-name"
                    value={createDraft.vaultName}
                    onChange={(event) =>
                      setCreateDraft((current) => ({ ...current, vaultName: event.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-vault-source-type">
                    知识仓类型 <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={createDraft.sourceType}
                    onValueChange={(value: KnowledgeSourceMode) =>
                      setCreateDraft((current) => ({
                        ...current,
                        sourceType: value,
                        localPath: value === "managed_fs" ? "" : current.localPath,
                      }))
                    }
                  >
                    <SelectTrigger id="create-vault-source-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="managed_fs">平台托管</SelectItem>
                      <SelectItem value="external_obsidian_fs">外部接入</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label>
                  租户 <span className="text-destructive">*</span>
                </Label>
                <TenantSelectField
                  value={createDraft.tenantId}
                  onChange={(tenantId) => updateDraftTenant(setCreateDraft, tenantId)}
                  tenantOptions={tenantOptions}
                  disabled={tenantOptionsQuery.isLoading}
                />
              </div>

              {createDraft.sourceType === "managed_fs" ? (
                <div className="rounded-lg border border-border/70 bg-muted/15 p-4">
                  <div className="flex items-start gap-3">
                    <Building2 className="mt-0.5 size-4 text-primary" />
                    <div className="space-y-1 text-sm">
                      <div className="font-medium text-foreground">系统自动创建托管目录</div>
                      <div className="text-muted-foreground">
                        当前租户会默认落到前端仓库同级目录下的 <span className="font-medium text-foreground">{createManagedPathHint}</span>
                        ，无需手动填写路径。
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="create-local-path">
                    外接目录 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="create-local-path"
                    value={createDraft.localPath}
                    onChange={(event) =>
                      setCreateDraft((current) => ({ ...current, localPath: event.target.value }))
                    }
                    placeholder="/absolute/path/to/obsidian-vault"
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="create-remark">备注</Label>
                <Textarea
                  id="create-remark"
                  value={createDraft.remark}
                  onChange={(event) =>
                    setCreateDraft((current) => ({ ...current, remark: event.target.value }))
                  }
                  className="min-h-24"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={handleCreateVault} disabled={createVaultMutation.isPending}>
                {createVaultMutation.isPending ? "创建中..." : "保存"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
