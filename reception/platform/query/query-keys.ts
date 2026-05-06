export const queryKeys = {
  auth: {
    session: ['auth', 'session'] as const,
  },
  dashboard: {
    stats: ['dashboard', 'stats'] as const,
    logs: (limit?: number) => ['dashboard', 'logs', limit ?? null] as const,
  },
  intake: {
    overview: ['intake', 'overview'] as const,
    filteredOverview: (params?: { tenantId?: string; channel?: string }) =>
      ['intake', 'overview', params?.tenantId ?? '', params?.channel ?? ''] as const,
    trace: (traceId: string | null) => ['intake', 'trace', traceId ?? null] as const,
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
    customerAccess: ['settings', 'customer-access'] as const,
    wecomBindingState: (tenantId?: string) =>
      ['settings', 'wecom-binding-state', tenantId ?? ''] as const,
    wecomPublicBindSession: (token?: string | null) =>
      ['settings', 'wecom-public-bind-session', token ?? null] as const,
    protocolBindings: (params?: { tenantId?: string; agentId?: string }) =>
      ['settings', 'protocol-bindings', params?.tenantId ?? '', params?.agentId ?? ''] as const,
  },
  executors: {
    list: ['executors'] as const,
    detail: (executorId: string | null) => ['executors', executorId ?? null] as const,
    runtimeCapabilities: ['executors', 'runtime-capabilities'] as const,
  },
  knowledge: {
    vaults: ['knowledge', 'vaults'] as const,
    vaultList: (params?: { vaultType?: string; tenantId?: string; enabled?: string }) =>
      ['knowledge', 'vaults', params?.vaultType ?? 'all', params?.tenantId ?? '', params?.enabled ?? 'all'] as const,
    documents: ['knowledge', 'documents'] as const,
    documentList: (params?: {
      vaultId?: string
      tenantId?: string
      scope?: string
      status?: string
      category?: string
      search?: string
      limit?: number
      offset?: number
    }) =>
      [
        'knowledge',
        'documents',
        params?.vaultId ?? '',
        params?.tenantId ?? '',
        params?.scope ?? 'all',
        params?.status ?? 'active',
        params?.category ?? '',
        params?.search ?? '',
        params?.limit ?? 50,
        params?.offset ?? 0,
      ] as const,
    documentDetail: (documentId: string | null) => ['knowledge', 'documents', documentId ?? null] as const,
    syncJobs: ['knowledge', 'sync-jobs'] as const,
    syncJobList: (params?: {
      vaultId?: string
      tenantId?: string
      status?: string
      limit?: number
      offset?: number
    }) =>
      [
        'knowledge',
        'sync-jobs',
        params?.vaultId ?? '',
        params?.tenantId ?? '',
        params?.status ?? 'all',
        params?.limit ?? 50,
        params?.offset ?? 0,
      ] as const,
    retrievalLogs: ['knowledge', 'retrieval-logs'] as const,
    retrievalLogList: (params?: {
      tenantId?: string
      scene?: string
      requestSource?: string
      traceId?: string
      limit?: number
      offset?: number
    }) =>
      [
        'knowledge',
        'retrieval-logs',
        params?.tenantId ?? '',
        params?.scene ?? 'all',
        params?.requestSource ?? 'all',
        params?.traceId ?? '',
        params?.limit ?? 100,
        params?.offset ?? 0,
      ] as const,
  },
  memory: {
    longTerm: (params?: {
      tenantId?: string
      subjectType?: string
      subjectId?: string
      memoryType?: string
      query?: string
      memoryScope?: string
      limit?: number
    }) =>
      [
        'memory',
        'long-term',
        params?.tenantId ?? '',
        params?.subjectType ?? '',
        params?.subjectId ?? '',
        params?.memoryType ?? '',
        params?.query ?? '',
        params?.memoryScope ?? '',
        params?.limit ?? 20,
      ] as const,
  },
  external: {
    health: ['external', 'health'] as const,
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
