import { AUTH_REFRESH_TOKEN_KEY, AUTH_TOKEN_KEY } from '@/platform/api/config'

const WS_TOKEN_QUERY_KEYS = ['token', 'access_token'] as const
const AUTH_SESSION_EVENT = 'workbot:auth-session'

type AuthSession = {
  accessToken: string | null
  refreshToken: string | null
}

function canUseStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function emitAuthSessionEvent() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new Event(AUTH_SESSION_EVENT))
}

function setStorageValue(key: string, value: string | null) {
  if (!canUseStorage()) return

  if (value) {
    window.localStorage.setItem(key, value)
    return
  }

  window.localStorage.removeItem(key)
}

function decodeJwtPayload(token: string): { exp?: number } | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null

  try {
    const normalizedValue = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padding = normalizedValue.length % 4
    const base64Value =
      padding === 0 ? normalizedValue : `${normalizedValue}${'='.repeat(4 - padding)}`
    const decodedValue =
      typeof window !== 'undefined' && typeof window.atob === 'function'
        ? window.atob(base64Value)
        : Buffer.from(base64Value, 'base64').toString('binary')

    return JSON.parse(decodedValue) as { exp?: number }
  } catch {
    return null
  }
}

export function getAccessToken(): string | null {
  if (!canUseStorage()) return null
  return window.localStorage.getItem(AUTH_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  if (!canUseStorage()) return null
  return window.localStorage.getItem(AUTH_REFRESH_TOKEN_KEY)
}

export function hasStoredSession() {
  return Boolean(getAccessToken() || getRefreshToken())
}

export function isJwtExpired(token: string, skewMs = 30_000) {
  const payload = decodeJwtPayload(token)
  if (!payload?.exp) return false
  return payload.exp * 1000 <= Date.now() + skewMs
}

export function setAccessToken(token: string) {
  setStorageValue(AUTH_TOKEN_KEY, token)
  emitAuthSessionEvent()
}

export function setRefreshToken(token: string) {
  setStorageValue(AUTH_REFRESH_TOKEN_KEY, token)
  emitAuthSessionEvent()
}

export function setAuthSession(session: AuthSession) {
  setStorageValue(AUTH_TOKEN_KEY, session.accessToken)
  setStorageValue(AUTH_REFRESH_TOKEN_KEY, session.refreshToken)
  emitAuthSessionEvent()
}

export function clearAccessToken() {
  setStorageValue(AUTH_TOKEN_KEY, null)
  emitAuthSessionEvent()
}

export function clearRefreshToken() {
  setStorageValue(AUTH_REFRESH_TOKEN_KEY, null)
  emitAuthSessionEvent()
}

export function clearAuthSession() {
  if (!canUseStorage()) return
  window.localStorage.removeItem(AUTH_TOKEN_KEY)
  window.localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY)
  emitAuthSessionEvent()
}

export function subscribeAuthSession(listener: () => void) {
  if (typeof window === 'undefined') {
    return () => {}
  }

  const handleStorage = (event: StorageEvent) => {
    if (!event.key) return
    if (event.key !== AUTH_TOKEN_KEY && event.key !== AUTH_REFRESH_TOKEN_KEY) return
    listener()
  }
  const handleSessionEvent = () => {
    listener()
  }

  window.addEventListener('storage', handleStorage)
  window.addEventListener(AUTH_SESSION_EVENT, handleSessionEvent)

  return () => {
    window.removeEventListener('storage', handleStorage)
    window.removeEventListener(AUTH_SESSION_EVENT, handleSessionEvent)
  }
}

export function buildAuthenticatedWebSocketUrl(pathname: string, baseUrl: string) {
  const token = getAccessToken()
  if (!token || isJwtExpired(token)) return null

  try {
    const normalizedPathname = pathname.startsWith('/') ? pathname : `/${pathname}`
    const url = new URL(baseUrl)

    url.pathname = `${url.pathname.replace(/\/+$/, '')}${normalizedPathname}`

    for (const key of WS_TOKEN_QUERY_KEYS) {
      url.searchParams.set(key, token)
    }

    return url.toString()
  } catch {
    return null
  }
}
