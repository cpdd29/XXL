import { API_BASE_URL, REQUEST_TIMEOUT_MS } from '@/lib/api/config'
import {
  clearAuthSession,
  getAccessToken,
  getRefreshToken,
  isJwtExpired,
  setAuthSession,
} from '@/lib/api/auth-storage'
import { ApiError } from '@/lib/api/errors'
import type { LoginResponse } from '@/types'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions<TBody = unknown> {
  method?: HttpMethod
  body?: TBody
  signal?: AbortSignal
  headers?: HeadersInit
}

function buildUrl(path: string) {
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}

function isAuthPath(path: string) {
  return path.includes('/api/auth/login') || path.includes('/api/auth/refresh')
}

let refreshPromise: Promise<string | null> | null = null

async function parseJsonSafely(response: Response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

async function fetchJson<TBody = unknown>(
  path: string,
  options: RequestOptions<TBody>,
  tokenOverride?: string | null,
  forceAuthorizationOverride = false,
) {
  const headers = new Headers(options.headers)

  if (!headers.has('Content-Type') && options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  if (forceAuthorizationOverride) {
    headers.delete('Authorization')
  }

  if (tokenOverride && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${tokenOverride}`)
  }

  const response = await fetch(buildUrl(path), {
    method: options.method || 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    cache: 'no-store',
  })
  const payload = await parseJsonSafely(response)

  return { response, payload }
}

async function refreshAccessToken(signal?: AbortSignal): Promise<string | null> {
  if (refreshPromise) return refreshPromise

  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    clearAuthSession()
    return null
  }

  refreshPromise = (async () => {
    try {
      const { response, payload } = await fetchJson('/api/auth/refresh', {
        method: 'POST',
        body: { refreshToken },
        signal,
      })

      if (!response.ok || !payload || typeof payload !== 'object') {
        clearAuthSession()
        return null
      }

      const session = payload as LoginResponse
      if (!session.accessToken || !session.refreshToken) {
        clearAuthSession()
        return null
      }

      setAuthSession({
        accessToken: session.accessToken,
        refreshToken: session.refreshToken,
      })

      return session.accessToken
    } catch {
      clearAuthSession()
      return null
    } finally {
      refreshPromise = null
    }
  })()

  return refreshPromise
}

export async function ensureActiveAccessToken(signal?: AbortSignal): Promise<string | null> {
  const accessToken = getAccessToken()
  if (accessToken && !isJwtExpired(accessToken)) {
    return accessToken
  }

  if (getRefreshToken()) {
    return refreshAccessToken(signal)
  }

  if (accessToken) {
    clearAuthSession()
  }

  return null
}

export async function getAuthenticatedHeaders(
  headers?: HeadersInit,
  signal?: AbortSignal,
): Promise<Headers> {
  const nextHeaders = new Headers(headers)
  const token = await ensureActiveAccessToken(signal)

  if (token && !nextHeaders.has('Authorization')) {
    nextHeaders.set('Authorization', `Bearer ${token}`)
  }

  return nextHeaders
}

export async function apiRequest<TResponse, TBody = unknown>(
  path: string,
  options: RequestOptions<TBody> = {},
): Promise<TResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const signal = options.signal || controller.signal
    let token = isAuthPath(path) ? null : await ensureActiveAccessToken(signal)
    let { response, payload } = await fetchJson(path, { ...options, signal }, token)

    if (!response.ok && response.status === 401 && !isAuthPath(path)) {
      const refreshedToken = await refreshAccessToken(signal)

      if (refreshedToken) {
        token = refreshedToken
        const retriedResult = await fetchJson(path, { ...options, signal }, token, true)
        response = retriedResult.response
        payload = retriedResult.payload
      } else {
        clearAuthSession()
      }
    }

    if (!response.ok) {
      let message = `Request failed with status ${response.status}`

      if (payload && typeof payload === 'object') {
        if ('detail' in payload && typeof payload.detail === 'string') {
          message = payload.detail
        } else if ('message' in payload && typeof payload.message === 'string') {
          message = payload.message
        }
      }

      throw new ApiError(message, response.status, payload)
    }

    return payload as TResponse
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('Request timeout', 408)
    }
    throw new ApiError(error instanceof Error ? error.message : 'Network error', 0)
  } finally {
    clearTimeout(timeout)
  }
}
