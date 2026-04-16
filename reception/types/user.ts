export type UserRole = 'admin' | 'operator' | 'viewer' | 'external'
export type UserStatus = 'active' | 'inactive' | 'suspended'

export interface UserPlatformAccount {
  platform: string
  accountId: string
}

export interface User {
  id: string
  name: string
  email: string
  role: UserRole
  status: UserStatus
  lastLogin: string
  totalInteractions: number
  createdAt: string
}

export interface UserProfile extends User {
  tags: string[]
  sourceChannels: string[]
  platformAccounts: UserPlatformAccount[]
  preferredLanguage: 'zh' | 'en'
  notes: string
  identityMappingStatus?: string
  identityMappingSource?: string
  identityMappingConfidence?: number
  lastIdentitySyncAt?: string | null
}

export interface UserActivityItem {
  id: string
  timestamp: string
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  description: string
  source: string
}

export interface UserListResponse {
  items: User[]
  total: number
}

export interface UserActivityResponse {
  items: UserActivityItem[]
  total: number
}

export interface UserActionResponse {
  ok: boolean
  message: string
  user: User | UserProfile
}

export interface UpdateUserProfileRequest {
  tags: string[]
  notes: string
  preferredLanguage: 'zh' | 'en'
}
