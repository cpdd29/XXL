export const queryKeys = {
  auth: {
    session: ['auth', 'session'] as const,
  },
  dashboard: {
    stats: ['dashboard', 'stats'] as const,
    logs: (limit?: number) => ['dashboard', 'logs', limit ?? null] as const,
  },
  tasks: {
    list: ['tasks'] as const,
    detail: (taskId: string) => ['tasks', taskId] as const,
    steps: (taskId: string) => ['tasks', taskId, 'steps'] as const,
  },
  agents: {
    list: ['agents'] as const,
    status: (agentId: string) => ['agents', agentId, 'status'] as const,
    brainSkills: ['agents', 'brain-skills'] as const,
  },
  tools: {
    list: ['tools'] as const,
    sources: ['tools', 'sources'] as const,
    detail: (toolId: string | null) => ['tools', 'detail', toolId ?? null] as const,
    sourceDetail: (sourceId: string | null) => ['tools', 'source-detail', sourceId ?? null] as const,
  },
  users: {
    tenants: ['users', 'tenants'] as const,
    list: ['users'] as const,
    profile: (userId: string) => ['users', userId, 'profile'] as const,
    activity: (userId: string) => ['users', userId, 'activity'] as const,
  },
  security: {
    report: (windowHours?: number) => ['security', 'report', windowHours ?? 24] as const,
    alerts: (params?: {
      search?: string
      status?: string
      severity?: string
      source?: string
      limit?: number
      offset?: number
    }) =>
      [
        'security',
        'alerts',
        params?.search ?? '',
        params?.status ?? 'all',
        params?.severity ?? 'all',
        params?.source ?? 'all',
        params?.limit ?? 50,
        params?.offset ?? 0,
      ] as const,
    policy: ['security', 'policy'] as const,
    guardian: ['security', 'guardian'] as const,
    penalties: ['security', 'penalties'] as const,
    logs: (params?: {
      search?: string
      status?: string
      layer?: string
      user?: string
      resource?: string
      limit?: number
      offset?: number
    }) =>
      [
        'security',
        'logs',
        params?.search ?? '',
        params?.status ?? 'all',
        params?.layer ?? 'all',
        params?.user ?? '',
        params?.resource ?? '',
        params?.limit ?? 20,
        params?.offset ?? 0,
      ] as const,
    rules: ['security', 'rules'] as const,
  },
  settings: {
    general: ['settings', 'general'] as const,
    agentApi: ['settings', 'agent-api'] as const,
    channelIntegration: ['settings', 'channel-integration'] as const,
  },
  external: {
    governance: (auditLimit?: number) => ['external', 'governance', auditLimit ?? 20] as const,
    agentVersions: (family?: string | null) => ['external', 'agent-versions', family ?? null] as const,
    skillVersions: (family?: string | null) => ['external', 'skill-versions', family ?? null] as const,
    audits: (params?: {
      capabilityType?: string | null
      limit?: number
      status?: string | null
    }) =>
      [
        'external',
        'audits',
        params?.capabilityType ?? 'all',
        params?.limit ?? 50,
        params?.status ?? 'all',
      ] as const,
  },
}
