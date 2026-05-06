export interface LongTermMemoryItem {
  id: string
  userId: string
  sourceMidTermId: string
  memoryType: string
  subjectType: string | null
  subjectId: string | null
  title: string | null
  source: string | null
  importance: number | null
  summary: string | null
  memoryText: string
  keywords: string[]
  createdAt: string
  updatedAt: string | null
  tenantId: string
  projectId: string
  environment: string
  memoryScope: string
  memoryLayerKind: string
  writeSource: string
  trustLevel: string
  memoryStatus: string
  reviewStatus: string
}

export interface LongTermMemoryListResponse {
  items: LongTermMemoryItem[]
  total: number
  scopeBreakdown: Record<string, number>
}
