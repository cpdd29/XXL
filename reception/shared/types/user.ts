export type UserPreferredLanguage = 'zh' | 'en'
export type UserTenantStatus = 'active' | 'inactive' | 'archived' | string
export type UserActivityType = string

export interface UserTenantOption {
  id: string
  name: string
  status: UserTenantStatus
  profileCount: number
  description: string
}

export interface UserPlatformAccount {
  platform: string
  accountId: string
}

export interface UserPortrait {
  id: string
  tenantId: string
  tenantName: string
  tenantStatus: UserTenantStatus
  name: string
  sourceChannels: string[]
  platformAccounts: UserPlatformAccount[]
  tags: string[]
  preferredLanguage: UserPreferredLanguage
  lastActiveAt: string
  totalInteractions: number
  notes: string
  interactionSummary: string
  lastLogin?: string
  email?: string
  createdAt?: string
}

export interface UserProfile extends UserPortrait {
  identityMappingStatus: string
  identityMappingSource: string
  identityMappingConfidence: number
  lastIdentitySyncAt: string | null
}

export interface UserActivityItem {
  id: string
  timestamp: string
  type: UserActivityType
  title: string
  description: string
  source: string
}

export interface UserPortraitListResponse {
  items: UserPortrait[]
  total: number
  appliedTenantId?: string | null
  canViewAllTenants: boolean
}

export interface UserTenantOptionsResponse {
  items: UserTenantOption[]
  total: number
  canViewAllTenants: boolean
  defaultTenantId?: string | null
}

export interface CreateUserTenantRequest {
  name: string
  description: string
}

export interface UserTenantActionResponse {
  ok: boolean
  message: string
  tenant?: UserTenantOption | null
  deletedTenantId?: string | null
}

export interface UserActivityResponse {
  items: UserActivityItem[]
  total: number
}

export interface UserActionResponse {
  ok: boolean
  message: string
  profile: UserProfile
}

export interface UpdateUserProfileRequest {
  tags: string[]
  notes: string
  preferredLanguage: UserPreferredLanguage
}
