export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') || 'http://localhost:8080'

export const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_BASE_URL?.replace(/\/+$/, '') || 'ws://localhost:8080'

export const REQUEST_TIMEOUT_MS = 15_000

export const AUTH_TOKEN_KEY = 'workbot_access_token'
export const REFRESH_TOKEN_KEY = 'workbot_refresh_token'
export const AUTH_REFRESH_TOKEN_KEY = 'workbot_refresh_token'
