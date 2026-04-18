export interface BrainSkillItem {
  id: string
  name: string
  fileName: string
  format: string
  description?: string | null
  enabled: boolean
  tags: string[]
  capabilities: string[]
  uploadedAt?: string | null
}

export interface BrainSkillListResponse {
  items: BrainSkillItem[]
  total: number
}

export interface BrainSkillUploadRequest {
  fileName: string
  content: string
}

export interface BrainSkillActionResponse {
  ok: boolean
  message: string
  skill: BrainSkillItem
}

export interface BrainSkillDeleteResponse {
  ok: boolean
  message: string
  skillId: string
}
