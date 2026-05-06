"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiRequest } from "@/platform/api/client"
import { queryKeys } from "@/platform/query/query-keys"
import type {
  CreateKnowledgeVaultFolderRequest,
  CreateKnowledgeSyncJobRequest,
  DeleteKnowledgeVaultEntryRequest,
  ImportKnowledgeVaultRequest,
  CreateKnowledgeVaultRequest,
  KnowledgeDocumentDetailResponse,
  KnowledgeDocumentListResponse,
  KnowledgeRetrievalLogListResponse,
  KnowledgeSyncJobActionResponse,
  KnowledgeSyncJobListResponse,
  KnowledgeVaultEntryActionResponse,
  KnowledgeVaultImportResponse,
  KnowledgeVaultValidationResponse,
  KnowledgeVaultActionResponse,
  KnowledgeVaultDeleteResponse,
  KnowledgeVaultListResponse,
  KnowledgeVaultScanResult,
  RenameKnowledgeVaultEntryRequest,
  UpdateKnowledgeVaultRequest,
} from "@/shared/types"

function buildSearchParams(
  values: Record<string, string | number | boolean | null | undefined>,
) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") continue
    params.set(key, String(value))
  }
  const queryString = params.toString()
  return queryString ? `?${queryString}` : ""
}

export function useKnowledgeVaults(params?: {
  vaultType?: string
  tenantId?: string
  enabled?: boolean | null
}) {
  const enabledValue =
    params?.enabled === null || params?.enabled === undefined ? undefined : String(params.enabled)
  return useQuery({
    queryKey: queryKeys.knowledge.vaultList({
      vaultType: params?.vaultType,
      tenantId: params?.tenantId,
      enabled: enabledValue,
    }),
    queryFn: () =>
      apiRequest<KnowledgeVaultListResponse>(
        `/api/knowledge/vaults${buildSearchParams({
          vaultType: params?.vaultType,
          tenantId: params?.tenantId,
          enabled: enabledValue,
        })}`,
      ),
  })
}

export function useCreateKnowledgeVault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateKnowledgeVaultRequest) =>
      apiRequest<KnowledgeVaultActionResponse, CreateKnowledgeVaultRequest>("/api/knowledge/vaults", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
    },
  })
}

export function useUpdateKnowledgeVault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ vaultId, payload }: { vaultId: string; payload: UpdateKnowledgeVaultRequest }) =>
      apiRequest<KnowledgeVaultActionResponse, UpdateKnowledgeVaultRequest>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}`,
        {
          method: "PUT",
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.syncJobList({ vaultId: variables.vaultId }),
      })
    },
  })
}

export function useDeleteKnowledgeVault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vaultId: string) =>
      apiRequest<KnowledgeVaultDeleteResponse>(`/api/knowledge/vaults/${encodeURIComponent(vaultId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.syncJobs })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.retrievalLogs })
    },
  })
}

export function useImportKnowledgeVaultFiles() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      vaultId,
      payload,
    }: {
      vaultId: string
      payload: ImportKnowledgeVaultRequest
    }) =>
      apiRequest<KnowledgeVaultImportResponse, ImportKnowledgeVaultRequest>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/import`,
        {
          method: "POST",
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.syncJobList({ vaultId: variables.vaultId }),
      })
    },
  })
}

export function useCreateKnowledgeVaultFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      vaultId,
      payload,
    }: {
      vaultId: string
      payload: CreateKnowledgeVaultFolderRequest
    }) =>
      apiRequest<KnowledgeVaultEntryActionResponse, CreateKnowledgeVaultFolderRequest>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/entries/folders`,
        {
          method: "POST",
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.syncJobList({ vaultId: variables.vaultId }),
      })
    },
  })
}

export function useRenameKnowledgeVaultEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      vaultId,
      payload,
    }: {
      vaultId: string
      payload: RenameKnowledgeVaultEntryRequest
    }) =>
      apiRequest<KnowledgeVaultEntryActionResponse, RenameKnowledgeVaultEntryRequest>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/entries/rename`,
        {
          method: "POST",
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.syncJobList({ vaultId: variables.vaultId }),
      })
    },
  })
}

export function useDeleteKnowledgeVaultEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      vaultId,
      payload,
    }: {
      vaultId: string
      payload: DeleteKnowledgeVaultEntryRequest
    }) =>
      apiRequest<KnowledgeVaultEntryActionResponse, DeleteKnowledgeVaultEntryRequest>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/entries`,
        {
          method: "DELETE",
          body: payload,
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.syncJobList({ vaultId: variables.vaultId }),
      })
    },
  })
}

export function useValidateKnowledgeVaultSource() {
  return useMutation({
    mutationFn: (vaultId: string) =>
      apiRequest<KnowledgeVaultValidationResponse>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/validate-source`,
        {
          method: "POST",
        },
      ),
  })
}

export function useScanKnowledgeVaultPreview() {
  return useMutation({
    mutationFn: ({ vaultId, limit = 50 }: { vaultId: string; limit?: number }) =>
      apiRequest<KnowledgeVaultScanResult>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/scan-preview${buildSearchParams({
          limit,
        })}`,
        {
          method: "POST",
        },
      ),
  })
}

export function useTriggerKnowledgeVaultSync() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      vaultId,
      payload,
    }: {
      vaultId: string
      payload?: Omit<CreateKnowledgeSyncJobRequest, "vaultId">
    }) =>
      apiRequest<KnowledgeSyncJobActionResponse, CreateKnowledgeSyncJobRequest>(
        `/api/knowledge/vaults/${encodeURIComponent(vaultId)}/sync`,
        {
          method: "POST",
          body: {
            vaultId,
            triggerType: payload?.triggerType ?? "manual",
            forceFullScan: payload?.forceFullScan ?? false,
            metadata: payload?.metadata ?? {},
          },
        },
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.vaults })
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.documents })
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.syncJobList({ vaultId: variables.vaultId }),
      })
    },
  })
}

export function useKnowledgeDocuments(
  params?: {
    vaultId?: string
    tenantId?: string
    scope?: string
    status?: string
    category?: string
    search?: string
    limit?: number
    offset?: number
  },
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.knowledge.documentList(params),
    queryFn: () =>
      apiRequest<KnowledgeDocumentListResponse>(
        `/api/knowledge/documents${buildSearchParams({
          vaultId: params?.vaultId,
          tenantId: params?.tenantId,
          scope: params?.scope,
          status: params?.status ?? "active",
          category: params?.category,
          search: params?.search,
          limit: params?.limit ?? 50,
          offset: params?.offset ?? 0,
        })}`,
      ),
    enabled,
  })
}

export function useKnowledgeDocumentDetail(documentId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.knowledge.documentDetail(documentId),
    queryFn: () =>
      apiRequest<KnowledgeDocumentDetailResponse>(
        `/api/knowledge/documents/${encodeURIComponent(String(documentId))}`,
      ),
    enabled: enabled && Boolean(documentId),
  })
}

export function useKnowledgeSyncJobs(
  params?: {
    vaultId?: string
    tenantId?: string
    status?: string
    limit?: number
    offset?: number
  },
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.knowledge.syncJobList(params),
    queryFn: () =>
      apiRequest<KnowledgeSyncJobListResponse>(
        `/api/knowledge/sync-jobs${buildSearchParams({
          vaultId: params?.vaultId,
          tenantId: params?.tenantId,
          status: params?.status,
          limit: params?.limit ?? 50,
          offset: params?.offset ?? 0,
        })}`,
      ),
    enabled,
  })
}

export function useKnowledgeRetrievalLogs(
  params?: {
    tenantId?: string
    scene?: string
    requestSource?: string
    traceId?: string
    limit?: number
    offset?: number
  },
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.knowledge.retrievalLogList(params),
    queryFn: () =>
      apiRequest<KnowledgeRetrievalLogListResponse>(
        `/api/knowledge/retrieval-logs${buildSearchParams({
          tenantId: params?.tenantId,
          scene: params?.scene,
          requestSource: params?.requestSource,
          traceId: params?.traceId,
          limit: params?.limit ?? 100,
          offset: params?.offset ?? 0,
        })}`,
      ),
    enabled,
  })
}
