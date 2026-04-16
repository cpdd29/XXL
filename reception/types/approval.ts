export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled'
export type ApprovalRequestType =
  | 'settings_change'
  | 'security_release'
  | 'manual_handoff'
  | 'external_capability_release'

export interface ApprovalItem {
  id: string
  requestType: ApprovalRequestType
  status: ApprovalStatus
  title: string
  resource: string
  requestedBy: string
  requestedAt: string
  reviewedBy?: string | null
  reviewedAt?: string | null
  reason?: string | null
  note?: string | null
  payload: Record<string, unknown>
}

export interface ApprovalListResponse {
  items: ApprovalItem[]
  total: number
}

export interface CreateApprovalRequest {
  requestType: ApprovalRequestType
  title: string
  resource: string
  reason?: string
  note?: string
  payload?: Record<string, unknown>
}

export interface ProcessApprovalRequest {
  note?: string
}

export interface ApprovalActionResponse {
  ok: boolean
  message: string
  approval: ApprovalItem
}
