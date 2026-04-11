export interface ScheduledTask {
  workflowId: string
  workflowName: string
  description: string
  status: string
  cron: string
  priority: number
  channels: string[]
  preferredLanguage: string | null
  nextAction: string
  dispatchState: string | null
  latestRunStatus: string | null
  latestRunId: string | null
  latestRunUpdatedAt: string | null
  monitorState: string | null
}

export interface ScheduledTaskListResponse {
  items: ScheduledTask[]
  total: number
}
