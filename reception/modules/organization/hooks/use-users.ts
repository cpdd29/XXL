'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAuthenticatedHeaders } from '@/platform/api'
import { apiRequest } from '@/platform/api/client'
import { API_BASE_URL } from '@/platform/api/config'
import { ApiError } from '@/platform/api/errors'
import { queryKeys } from '@/platform/query/query-keys'
import type {
  CreateUserTenantRequest,
  UpdateUserProfileRequest,
  UserActionResponse,
  UserActivityResponse,
  UserPortraitListResponse,
  UserProfile,
  UserTenantActionResponse,
  UserTenantOptionsResponse,
} from '@/shared/types'

interface UseUsersParams {
  tenantId?: string
  search?: string
  enabled?: boolean
  management?: boolean
}

function buildProfilesSearchParams(params: UseUsersParams = {}) {
  const searchParams = new URLSearchParams()

  if (params.tenantId) {
    searchParams.set('tenantId', params.tenantId)
  }

  if (params.search) {
    searchParams.set('search', params.search)
  }

  if (params.management) {
    searchParams.set('management', 'true')
  }

  return searchParams
}

function buildProfilesPath(params: UseUsersParams = {}) {
  const queryString = buildProfilesSearchParams(params).toString()
  return queryString ? `/api/profiles?${queryString}` : '/api/profiles'
}

function buildProfilesExportPath(params: UseUsersParams = {}) {
  const queryString = buildProfilesSearchParams(params).toString()
  return queryString ? `/api/profiles/export?${queryString}` : '/api/profiles/export'
}

function resolveDownloadFilename(contentDisposition: string | null) {
  if (!contentDisposition) return 'workbot-profiles.csv'

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return filenameMatch?.[1] || 'workbot-profiles.csv'
}

export async function downloadUsers(params: UseUsersParams = {}) {
  const headers = await getAuthenticatedHeaders({ Accept: 'text/csv' })
  const response = await fetch(`${API_BASE_URL}${buildProfilesExportPath(params)}`, {
    method: 'GET',
    headers,
    cache: 'no-store',
  })

  if (!response.ok) {
    const message = (await response.text()) || `Request failed with status ${response.status}`
    throw new ApiError(message, response.status)
  }

  return {
    blob: await response.blob(),
    filename: resolveDownloadFilename(response.headers.get('Content-Disposition')),
  }
}

export function useProfileTenants(enabled = true) {
  return useQuery<UserTenantOptionsResponse>({
    queryKey: queryKeys.users.tenants,
    queryFn: () => apiRequest<UserTenantOptionsResponse>('/api/profiles/tenants'),
    enabled,
  })
}

export const useUserTenants = useProfileTenants

export function useManagedUserTenants(enabled = true) {
  return useQuery<UserTenantOptionsResponse>({
    queryKey: [...queryKeys.users.tenants, 'management'] as const,
    queryFn: () => apiRequest<UserTenantOptionsResponse>('/api/profiles/tenants?management=true'),
    enabled,
  })
}

export function useCreateUserTenant() {
  const queryClient = useQueryClient()

  return useMutation<UserTenantActionResponse, Error, CreateUserTenantRequest>({
    mutationFn: (payload) =>
      apiRequest<UserTenantActionResponse, CreateUserTenantRequest>('/api/profiles/tenants', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.tenants })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list })
    },
  })
}

export function useDeleteUserTenant() {
  const queryClient = useQueryClient()

  return useMutation<UserTenantActionResponse, Error, { tenantId: string }>({
    mutationFn: ({ tenantId }) =>
      apiRequest<UserTenantActionResponse>(`/api/profiles/tenants/${encodeURIComponent(tenantId)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.tenants })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list })
    },
  })
}

export function useUsers(params?: UseUsersParams) {
  return useQuery<UserPortraitListResponse>({
    queryKey: [
      ...queryKeys.users.list,
      params?.tenantId ?? '',
      params?.search ?? '',
      params?.enabled ?? true,
      params?.management ?? false,
    ] as const,
    queryFn: () => apiRequest<UserPortraitListResponse>(buildProfilesPath(params)),
    enabled: params?.enabled ?? true,
  })
}

export function useUserProfile(userId: string) {
  return useQuery<UserProfile>({
    queryKey: queryKeys.users.profile(userId),
    queryFn: () => apiRequest<UserProfile>(`/api/profiles/${encodeURIComponent(userId)}`),
    enabled: Boolean(userId),
  })
}

export function useUserActivity(userId: string) {
  return useQuery<UserActivityResponse>({
    queryKey: queryKeys.users.activity(userId),
    queryFn: () => apiRequest<UserActivityResponse>(`/api/profiles/${encodeURIComponent(userId)}/activity`),
    enabled: Boolean(userId),
  })
}

export function useUpdateUserProfile() {
  const queryClient = useQueryClient()

  return useMutation<
    UserActionResponse,
    Error,
    {
      userId: string
      payload: UpdateUserProfileRequest
    }
  >({
    mutationFn: ({
      userId,
      payload,
    }) =>
      apiRequest<UserActionResponse, UpdateUserProfileRequest>(
        `/api/profiles/${encodeURIComponent(userId)}`,
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: (response, variables) => {
      queryClient.setQueryData(queryKeys.users.profile(variables.userId), response.profile)
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.profile(variables.userId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.activity(variables.userId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.tenants })
    },
  })
}
