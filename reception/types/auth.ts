export type AuthRole =
  | 'super_admin'
  | 'admin'
  | 'operator'
  | 'power_user'
  | 'viewer'
  | 'user'
  | 'blocked'
  | 'external'

export interface LoginRequest {
  email: string
  password: string
}

export interface AuthUser {
  id: string
  name: string
  email: string
  role: AuthRole
  status?: string | null
}

export interface AuthRoleSummary {
  key: string
  label: string
  tier: string
  description: string
}

export interface AuthPermissionGroup {
  key: string
  label: string
  permissions: string[]
}

export interface LoginResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  user: AuthUser
}

export interface AuthSessionResponse {
  user: AuthUser
  roleSummary: AuthRoleSummary
  permissions: string[]
  permissionGroups: AuthPermissionGroup[]
}
