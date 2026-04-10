export const queryKeys = {
  auth: {
    session: ['auth', 'session'] as const,
  },
  dashboard: {
    stats: ['dashboard', 'stats'] as const,
    logs: (limit?: number) => ['dashboard', 'logs', limit ?? null] as const,
  },
  collaboration: {
    overview: (taskId?: string) => ['collaboration', 'overview', taskId ?? null] as const,
  },
  tasks: {
    list: ['tasks'] as const,
    detail: (taskId: string) => ['tasks', taskId] as const,
    steps: (taskId: string) => ['tasks', taskId, 'steps'] as const,
  },
  agents: {
    list: ['agents'] as const,
    status: (agentId: string) => ['agents', agentId, 'status'] as const,
  },
  users: {
    list: ['users'] as const,
    profile: (userId: string) => ['users', userId, 'profile'] as const,
    activity: (userId: string) => ['users', userId, 'activity'] as const,
  },
  security: {
    report: (windowHours?: number) => ['security', 'report', windowHours ?? 24] as const,
    policy: ['security', 'policy'] as const,
    penalties: ['security', 'penalties'] as const,
    logs: (params?: {
      search?: string
      status?: string
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
  workflows: {
    list: ['workflows'] as const,
    monitor: (workflowId: string) => ['workflows', workflowId, 'monitor'] as const,
    runs: (workflowId: string) => ['workflows', workflowId, 'runs'] as const,
    run: (runId: string) => ['workflows', 'runs', runId] as const,
  },
}
