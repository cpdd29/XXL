'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/lib/api/client'
import {
  clearAuthSession,
  getAccessToken,
  hasStoredSession,
  setAuthSession,
  subscribeAuthSession,
} from '@/lib/api/auth-storage'
import { queryKeys } from '@/lib/api/query-keys'
import type { LoginRequest, LoginResponse } from '@/types'

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

  return {
    token,
    isAuthenticated,
    login: loginMutation.mutateAsync,
    loginMutation,
    logout,
  }
}
