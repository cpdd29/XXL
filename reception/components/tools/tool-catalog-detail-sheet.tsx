'use client'

import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import type { Tool, ToolHealthStatus, ToolSource } from '@/types'

const healthLabels: Record<ToolHealthStatus, string> = {
  healthy: '健康',
  degraded: '降级',
  unhealthy: '异常',
  unknown: '未知',
}

const healthClasses: Record<ToolHealthStatus, string> = {
  healthy: 'bg-success/20 text-success',
  degraded: 'bg-warning/20 text-warning-foreground',
  unhealthy: 'bg-destructive/20 text-destructive',
  unknown: 'bg-muted-foreground/20 text-muted-foreground',
}

const sourceTypeLabels: Record<ToolSource['type'], string> = {
  internal: '内部',
  local_tool: '本地兜底',
  external_repo: '外部仓库',
  mcp_server: 'MCP 服务',
  unknown: '未知来源',
}

const toolTypeLabels: Record<Tool['type'], string> = {
  skill: '技能',
  tool: '工具',
  mcp: 'MCP',
  unknown: '未分类',
}

const sourceModeLabels: Record<string, string> = {
  external_only: '全外接',
  hybrid: '混合接入',
  local_only: '本地主导',
  unknown: '未识别',
}

const sourceModeClasses: Record<string, string> = {
  external_only: 'bg-primary/15 text-primary',
  hybrid: 'bg-warning/20 text-warning-foreground',
  local_only: 'bg-secondary text-foreground',
  unknown: 'bg-muted text-muted-foreground',
}

function toDisplayDate(value: string | null) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function normalizeSourceModeValue(value: string | null): string | null {
  if (!value) return null
  const normalized = value.trim().toLowerCase().replace(/-/g, '_')
  if (!normalized) return null
  if (normalized === 'external_only' || normalized === 'hybrid' || normalized === 'local_only') return normalized
  return value
}

function boolLabel(value: boolean) {
  return value ? '是' : '否'
}

function MultiBadge({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <div className="text-xs text-muted-foreground">{empty}</div>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item} variant="secondary" className="text-xs">
          {item}
        </Badge>
      ))}
    </div>
  )
}

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-2 rounded-lg border border-border/70 bg-secondary/10 p-4">
      <div>
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  )
}

function JsonPreview({ value, empty }: { value: Record<string, unknown> | null; empty: string }) {
  if (!value) return <div className="text-xs text-muted-foreground">{empty}</div>
  return (
    <pre className="max-h-56 overflow-auto rounded-md border border-border/70 bg-background/60 p-3 text-xs leading-5 text-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

const migrationStageLabel: Record<string, string> = {
  retained: '保留中',
  bridging: '接入过渡中',
  externalized: '已外接',
  pending_removal: '待删除',
  deprecated: '已弃用',
  unknown: '未知',
}

export function ToolDetailSheet({
  open,
  onOpenChange,
  tool,
  source,
  loading,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  tool: Tool | null
  source: ToolSource | null
  loading: boolean
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
        <SheetHeader className="border-b border-border/70 p-5 pr-12">
          <SheetTitle>{tool?.name ?? '能力详情'}</SheetTitle>
          <SheetDescription>
            展示能力基本信息、输入输出、关联主脑流程、权限要求与最近调用摘要。
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-5.5rem)]">
          <div className="space-y-4 p-5">
            {!tool && !loading ? (
              <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                当前未选择能力，请从表格中点击“详情”查看。
              </div>
            ) : null}
            {loading && !tool ? (
              <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                正在加载能力详情...
              </div>
            ) : null}
            {tool ? (
              <>
                <Section title="基本信息">
                  <div className="grid gap-3 text-sm md:grid-cols-2">
                    <div>
                      <div className="text-xs text-muted-foreground">类型</div>
                      <div className="mt-1">
                        <Badge variant="secondary">{toolTypeLabels[tool.type]}</Badge>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">状态</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <Badge variant="secondary" className={cn('text-xs', healthClasses[tool.healthStatus])}>
                          {healthLabels[tool.healthStatus]}
                        </Badge>
                        <Badge
                          variant="secondary"
                          className={tool.enabled ? 'bg-success/20 text-success' : 'text-muted-foreground'}
                        >
                          {tool.enabled ? '已启用' : '已停用'}
                        </Badge>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">来源</div>
                      <div className="mt-1 text-sm text-foreground">{tool.sourceName}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">接入阶段</div>
                      <div className="mt-1">
                        <Badge variant="secondary">{migrationStageLabel[tool.migrationStage] ?? tool.migrationStage}</Badge>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">接入方式</div>
                      <div className="mt-1 text-sm text-foreground">{tool.bridgeMode || '-'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">最近扫描</div>
                      <div className="mt-1 text-sm text-foreground">{toDisplayDate(tool.lastScannedAt)}</div>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">{tool.description || '暂无描述'}</div>
                </Section>

                <Section title="输入输出" description="用于判断这项能力接收什么、返回什么。">
                  <div className="space-y-3">
                    <div>
                      <div className="mb-1 text-xs font-medium text-foreground">输入结构</div>
                      <JsonPreview value={tool.inputSchema} empty="暂无输入结构定义" />
                    </div>
                    <div>
                      <div className="mb-1 text-xs font-medium text-foreground">输出结构</div>
                      <JsonPreview value={tool.outputSchema} empty="暂无输出结构定义" />
                    </div>
                  </div>
                </Section>

                <Section title="关联主脑流程">
                  <div className="space-y-3">
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">关联执行角色</div>
                      <MultiBadge items={tool.linkedAgents} empty="未关联执行角色" />
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">关联工作流</div>
                      <MultiBadge items={tool.linkedWorkflows} empty="未关联工作流" />
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">能力标签</div>
                      <MultiBadge items={tool.requiredCapabilities} empty="未定义能力要求" />
                    </div>
                  </div>
                </Section>

                <Section title="权限与配置">
                  <div className="space-y-3">
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">权限要求</div>
                      <MultiBadge items={tool.requiredPermissions} empty="当前未声明权限要求" />
                      <div className="mt-2 rounded-md border border-border/70 bg-background/60 p-3 text-xs text-muted-foreground">
                        需要权限控制: {boolLabel(tool.permissions.requiresPermission)} | 需要人工审批:{' '}
                        {boolLabel(tool.permissions.approvalRequired)} | 生效范围:{' '}
                        {tool.permissions.executionScope || '-'}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">接入说明</div>
                      <div className="mt-1 space-y-1 text-sm">
                        <div className="text-foreground">{tool.providerSummary || '-'}</div>
                        <div className="text-xs leading-5 text-muted-foreground">{tool.configSummary || '-'}</div>
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">配置详情</div>
                      <JsonPreview value={tool.configDetail} empty="暂无结构化配置详情" />
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">流量与回滚</div>
                      <JsonPreview value={tool.trafficPolicy} empty="暂无双跑/灰度策略" />
                      <div className="mt-2" />
                      <JsonPreview value={tool.rollbackSummary} empty="暂无回滚摘要" />
                    </div>
                  </div>
                </Section>

                <Section title="最近调用摘要">
                  <div className="grid gap-3 text-sm md:grid-cols-2">
                    <div>
                      <div className="text-xs text-muted-foreground">最近调用时间</div>
                      <div className="mt-1 text-foreground">{toDisplayDate(tool.invocationSummary.lastCalledAt)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">累计调用次数</div>
                      <div className="mt-1 text-foreground">{tool.invocationSummary.callCount}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">成功 / 失败</div>
                      <div className="mt-1 text-foreground">
                        {tool.invocationSummary.successCalls} / {tool.invocationSummary.failedCalls}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">最近状态</div>
                      <div className="mt-1 text-foreground">{tool.invocationSummary.lastStatus}</div>
                    </div>
                  </div>
                  <div className="rounded-md border border-border/70 bg-background/60 p-3 text-xs leading-5 text-muted-foreground">
                    {tool.invocationSummary.summary}
                  </div>
                  {tool.invocationSummary.lastError ? (
                    <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
                      最近错误: {tool.invocationSummary.lastError}
                    </div>
                  ) : null}
                </Section>

                {source ? (
                  <Section title="关联来源健康">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className={cn('text-xs', healthClasses[source.healthStatus])}>
                        {healthLabels[source.healthStatus]}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        {sourceTypeLabels[source.type]}
                      </Badge>
                    </div>
                    <div className="text-xs leading-5 text-muted-foreground">
                      {source.healthMessage || '暂无来源健康说明'}
                    </div>
                  </Section>
                ) : null}
              </>
            ) : null}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

export function ToolSourceDetailSheet({
  open,
  onOpenChange,
  source,
  relatedToolNames,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  source: ToolSource | null
  relatedToolNames: string[]
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-xl">
        <SheetHeader className="border-b border-border/70 p-5 pr-12">
          <SheetTitle>{source?.name ?? '来源详情'}</SheetTitle>
          <SheetDescription>展示来源健康状态、扫描信息、绑定能力与接入说明。</SheetDescription>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-5.5rem)]">
          <div className="space-y-4 p-5">
            {!source ? (
              <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                当前未选择来源，请从表格中点击“详情”查看。
              </div>
            ) : (
              <>
                <Section title="基本信息">
                  <div className="grid gap-3 text-sm md:grid-cols-2">
                    <div>
                      <div className="text-xs text-muted-foreground">来源类型</div>
                      <div className="mt-1">
                        <Badge variant="secondary">{sourceTypeLabels[source.type]}</Badge>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">可用状态</div>
                      <div className="mt-1">
                        <Badge
                          variant="secondary"
                          className={source.enabled ? 'bg-success/20 text-success' : 'text-muted-foreground'}
                        >
                          {source.enabled ? '已启用' : '已停用'}
                        </Badge>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">来源路径</div>
                      <div className="mt-1 break-all text-xs text-foreground">{source.path || '-'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">扫描能力总数</div>
                      <div className="mt-1 text-foreground">{source.scannedCapabilityCount}</div>
                    </div>
                    <div className="md:col-span-2">
                      <div className="text-xs text-muted-foreground">接入策略</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        {source.sourceMode ? (
                          <Badge
                            variant="secondary"
                            className={cn(
                              'text-xs',
                              sourceModeClasses[normalizeSourceModeValue(source.sourceMode) ?? 'unknown'] ??
                                sourceModeClasses.unknown,
                            )}
                          >
                            当前模式:{' '}
                            {sourceModeLabels[normalizeSourceModeValue(source.sourceMode) ?? source.sourceMode] ??
                              source.sourceMode}
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-xs text-muted-foreground">
                            当前模式: 未声明
                          </Badge>
                        )}
                        {source.activationMode ? (
                          <Badge variant="secondary" className="text-xs">
                            启用方式: {source.activationMode}
                          </Badge>
                        ) : null}
                        {source.legacyFallback ? (
                          <Badge variant="secondary" className="bg-warning/20 text-xs text-warning-foreground">
                            本地兜底
                          </Badge>
                        ) : null}
                        {source.deprecated ? (
                          <Badge variant="secondary" className="bg-destructive/15 text-xs text-destructive">
                            已弃用
                          </Badge>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">{source.description || '暂无描述'}</div>
                </Section>

                <Section title="来源健康状态">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary" className={cn('text-xs', healthClasses[source.healthStatus])}>
                      {healthLabels[source.healthStatus]}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      status: {source.status}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      scan: {source.scanStatus}
                    </Badge>
                  </div>
                  <div className="text-xs leading-5 text-muted-foreground">
                    {source.healthMessage || '暂无健康状态说明'}
                  </div>
                  <div className="grid gap-3 text-sm md:grid-cols-2">
                    <div>
                      <div className="text-xs text-muted-foreground">最近检查</div>
                      <div className="mt-1 text-foreground">{toDisplayDate(source.lastCheckedAt)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">最近扫描</div>
                      <div className="mt-1 text-foreground">{toDisplayDate(source.lastScannedAt)}</div>
                    </div>
                  </div>
                  {source.notes.length > 0 ? (
                    <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                      {source.notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  ) : null}
                </Section>

                <Section title="来源关联关系">
                  <div>
                    <div className="mb-1 text-xs text-muted-foreground">关联执行角色</div>
                    <MultiBadge items={source.linkedAgents} empty="未关联执行角色" />
                  </div>
                  <div className="pt-2">
                    <div className="mb-1 text-xs text-muted-foreground">来源下能力</div>
                    <MultiBadge items={relatedToolNames} empty="当前未发现关联能力" />
                  </div>
                </Section>

                <Section title="接入说明">
                  <div className="space-y-2 text-sm">
                    <div>
                      <div className="text-xs text-muted-foreground">接入摘要</div>
                      <div className="mt-1 text-foreground">{source.providerSummary || '-'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">配置摘要</div>
                      <div className="mt-1 text-xs leading-5 text-muted-foreground">{source.configSummary || '-'}</div>
                    </div>
                  </div>
                </Section>
                <Section title="治理与接入摘要">
                  <div className="space-y-3">
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">注册信息</div>
                      <JsonPreview value={source.registrySummary} empty="暂无注册信息摘要" />
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">接入桥接</div>
                      <JsonPreview value={source.bridgeSummary} empty="暂无桥接摘要" />
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-muted-foreground">诊断摘要</div>
                      <JsonPreview value={source.doctorSummary} empty="暂无诊断摘要" />
                    </div>
                  </div>
                </Section>
              </>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
