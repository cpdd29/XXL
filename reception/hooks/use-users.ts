'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAuthenticatedHeaders } from '@/lib/api'
import { apiRequest } from '@/lib/api/client'
import { API_BASE_URL } from '@/lib/api/config'
import { ApiError } from '@/lib/api/errors'
import { queryKeys } from '@/lib/api/query-keys'
import type {
  UserActionResponse,
  UserActivityResponse,
  UserListResponse,
  UserProfile,
  UpdateUserProfileRequest,
  UserRole,
} from '@/types'

interface UseUsersParams {
  search?: string
  role?: string
  status?: string
}

function buildUsersSearchParams(params: UseUsersParams = {}) {
  const searchParams = new URLSearchParams()

  if (params.search) {
    searchParams.set('search', params.search)
  }
  if (params.role && params.role !== 'all') {
    searchParams.set('role', params.role)
  }
  if (params.status && params.status !== 'all') {
    searchParams.set('status', params.status)
  }

  return searchParams
}

function buildUsersPath(params: UseUsersParams = {}) {
  const queryString = buildUsersSearchParams(params).toString()
  return queryString ? `/api/users?${queryString}` : '/api/users'
}

function buildUsersExportPath(params: UseUsersParams = {}) {
  const queryString = buildUsersSearchParams(params).toString()
  return queryString ? `/api/users/export?${queryString}` : '/api/users/export'
}

function resolveDownloadFilename(contentDisposition: string | null) {
  if (!contentDisposition) return 'workbot-users.csv'

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return filenameMatch?.[1] || 'workbot-users.csv'
}

export async function downloadUsers(params: UseUsersParams = {}) {
  const headers = await getAuthenticatedHeaders({ Accept: 'text/csv' })
  const response = await fetch(`${API_BASE_URL}${buildUsersExportPath(params)}`, {
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

export function useUsers(params?: UseUsersParams) {
  return useQuery({
    queryKey: [
      ...queryKeys.users.list,
      params?.search ?? '',
      params?.role ?? 'all',
      params?.status ?? 'all',
    ] as const,
    queryFn: () => apiRequest<UserListResponse>(buildUsersPath(params)),
  })
}

export function useUserProfile(userId: string) {
  return useQuery({
    queryKey: queryKeys.users.profile(userId),
    queryFn: () => apiRequest<UserProfile>(`/api/users/${encodeURIComponent(userId)}/profile`),
    enabled: Boolean(userId),
  })
}

export function useUserActivity(userId: string) {
  return useQuery({
    queryKey: queryKeys.users.activity(userId),
    queryFn: () => apiRequest<UserActivityResponse>(`/api/users/${encodeURIComponent(userId)}/activity`),
    enabled: Boolean(userId),
  })
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      apiRequest<UserActionResponse>(`/api/users/${encodeURIComponent(userId)}/role`, {
        method: 'PUT',
        body: { role },
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.profile(variables.userId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.activity(variables.userId) })
    },
  })
}

export function useUpdateUserProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string
      payload: UpdateUserProfileRequest
    }) =>
      apiRequest<UserActionResponse, UpdateUserProfileRequest>(
        `/api/users/${encodeURIComponent(userId)}/profile`,
        {
          method: 'PUT',
          body: payload,
        },
      ),
    onSuccess: (response, variables) => {
      queryClient.setQueryData(
        queryKeys.users.profile(variables.userId),
        response.user as UserProfile,
      )
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.profile(variables.userId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.activity(variables.userId) })
    },
  })
}

export function useBlockUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (userId: string) =>
      apiRequest<UserActionResponse>(`/api/users/${encodeURIComponent(userId)}/block`, {
        method: 'POST',
      }),
    onSuccess: (_, userId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.profile(userId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.users.activity(userId) })
    },
  })
}
