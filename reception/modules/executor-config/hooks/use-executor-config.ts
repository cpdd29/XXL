"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiRequest } from "@/platform/api/client"
import { queryKeys } from "@/platform/query/query-keys"
import type {
  ExecutorActionResponse,
  ExecutorCheckResponse,
  ExecutorCreateRequest,
  ExecutorDeleteResponse,
  ExecutorListResponse,
  ExecutorRuntimeInstallRequest,
  ExecutorRuntimeInstallResponse,
  ExecutorRuntimeCapabilitiesResponse,
  ExecutorUpdateRequest,
} from "@/shared/types"

export function useExecutors() {
  return useQuery({
    queryKey: queryKeys.executors.list,
    queryFn: () => apiRequest<ExecutorListResponse>("/api/executors"),
  })
}

export function useExecutorRuntimeCapabilities() {
  return useQuery({
    queryKey: queryKeys.executors.runtimeCapabilities,
    queryFn: () =>
      apiRequest<ExecutorRuntimeCapabilitiesResponse>("/api/executors/runtime/capabilities"),
  })
}

export function useInstallMissingExecutorDrivers() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload?: ExecutorRuntimeInstallRequest) =>
      apiRequest<ExecutorRuntimeInstallResponse, ExecutorRuntimeInstallRequest>(
        "/api/executors/runtime/install-missing",
        {
          method: "POST",
          body: payload ?? {},
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.runtimeCapabilities })
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.list })
    },
  })
}

export function useCreateExecutor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ExecutorCreateRequest) =>
      apiRequest<ExecutorActionResponse, ExecutorCreateRequest>("/api/executors", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.list })
    },
  })
}

export function useUpdateExecutor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ executorId, payload }: { executorId: string; payload: ExecutorUpdateRequest }) =>
      apiRequest<ExecutorActionResponse, ExecutorUpdateRequest>(`/api/executors/${encodeURIComponent(executorId)}`, {
        method: "PUT",
        body: payload,
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.detail(variables.executorId) })
    },
  })
}

export function useDeleteExecutor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (executorId: string) =>
      apiRequest<ExecutorDeleteResponse>(`/api/executors/${encodeURIComponent(executorId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.list })
    },
  })
}

export function useValidateExecutor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (executorId: string) =>
      apiRequest<ExecutorCheckResponse>(`/api/executors/${encodeURIComponent(executorId)}/validate`, {
        method: "POST",
      }),
    onSuccess: (_, executorId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.detail(executorId) })
    },
  })
}

export function useHealthCheckExecutor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (executorId: string) =>
      apiRequest<ExecutorCheckResponse>(`/api/executors/${encodeURIComponent(executorId)}/health-check`, {
        method: "POST",
      }),
    onSuccess: (_, executorId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.executors.detail(executorId) })
    },
  })
}
