'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/platform/api/client'
import {
  clearAuthSession,
  getAccessToken,
  hasStoredSession,
  setAuthSession,
  subscribeAuthSession,
} from '@/platform/api/auth-storage'
import { queryKeys } from '@/platform/query/query-keys'
import type { AuthSessionResponse, LoginRequest, LoginResponse } from '@/shared/types'

export function useAuth() {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    setToken(getAccessToken())
    setIsAuthenticated(hasStoredSession())

    return subscribeAuthSession(() => {
      setToken(getAccessToken())
      setIsAuthenticated(hasStoredSession())
    })
  }, [])

  const sessionQuery = useQuery({
    queryKey: queryKeys.auth.session,
    queryFn: () => apiRequest<AuthSessionResponse>('/api/auth/session'),
    enabled: isAuthenticated,
    staleTime: 30_000,
  })

  const loginMutation = useMutation({
    mutationFn: (payload: LoginRequest) =>
      apiRequest<LoginResponse>('/api/auth/login', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: (result) => {
      setAuthSession({
        accessToken: result.accessToken,
        refreshToken: result.refreshToken,
      })
      setToken(result.accessToken)
      setIsAuthenticated(true)
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.session })
    },
  })

  const logout = () => {
    clearAuthSession()
    setToken(null)
    setIsAuthenticated(false)
    queryClient.clear()
  }

  const permissions = sessionQuery.data?.permissions ?? []
  const hasPermission = (permission: string) =>
    permissions.includes('*') || permissions.includes(permission)

  return {
    token,
    isAuthenticated,
    session: sessionQuery.data ?? null,
    currentUser: sessionQuery.data?.user ?? null,
    permissions,
    hasPermission,
    isSessionLoading: sessionQuery.isLoading,
    login: loginMutation.mutateAsync,
    loginMutation,
    logout,
  }
}
