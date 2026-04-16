"use client"

import { AlertTriangle, Database, Layers3, ShieldCheck } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useConfigGovernance } from "@/hooks/use-settings"

const sourceLabel: Record<string, string> = {
  database_system_settings: "数据库真源",
  runtime_cache: "运行时缓存",
  deployment_defaults: "部署默认值",
  deployment_env: "部署环境变量",
}

export default function SettingsGovernancePage() {
  const { data, isLoading, error } = useConfigGovernance()
  const sections = data?.sections ?? []
  const audits = data?.recentChangeAudits ?? []

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">配置来源与优先级</h1>
          <p className="text-sm text-muted-foreground">
            把主脑配置按运行时与部署时分层，并明确当前生效来源、读取优先级和风险提示。
          </p>
        </div>
        <Badge variant="secondary" className="bg-primary/10 text-primary">
          warning {data?.summary.warningCount ?? 0}
        </Badge>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          配置视图加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">配置分区</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{data?.summary.totalSections ?? 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">运行时可变</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {data?.summary.runtimeMutableSections ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">部署时固定</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {data?.summary.deploymentImmutableSections ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground">优先级模型</div>
            <div className="mt-2 text-sm font-medium text-foreground">
              {data?.readPriorityModel.runtimeMutable.join(" -> ") ?? "--"}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_420px]">
        <div className="space-y-4">
          {isLoading ? (
            <Card className="bg-card">
              <CardContent className="p-6 text-sm text-muted-foreground">正在加载配置来源与优先级视图...</CardContent>
            </Card>
          ) : null}
          {sections.map((section) => (
            <Card key={section.key} className="bg-card">
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-base">{section.label}</CardTitle>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      <span>{section.category}</span>
                      <span>{section.mutability}</span>
                      <span>source: {sourceLabel[section.effectiveSource] ?? section.effectiveSource}</span>
                    </div>
                  </div>
                  <Badge
                    variant="secondary"
                    className={
                      section.riskLevel === "warning"
                        ? "bg-warning/20 text-warning-foreground"
                        : "bg-success/15 text-success"
                    }
                  >
                    {section.riskLevel}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2 text-xs">
                  {section.readPriority.map((item) => (
                    <Badge key={`${section.key}-${item}`} variant="outline">
                      {item}
                    </Badge>
                  ))}
                </div>
                {section.warnings.length > 0 ? (
                  <div className="rounded-lg border border-warning/30 bg-warning/10 p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                      <AlertTriangle className="size-4" />
                      风险提示
                    </div>
                    <div className="space-y-1 text-sm text-muted-foreground">
                      {section.warnings.map((warning) => (
                        <div key={warning}>{warning}</div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-border bg-secondary/20 p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                      <ShieldCheck className="size-4" />
                      当前生效值
                    </div>
                    <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-muted-foreground">
                      {JSON.stringify(section.current, null, 2)}
                    </pre>
                  </div>
                  <div className="rounded-lg border border-border bg-secondary/20 p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                      <Layers3 className="size-4" />
                      默认基线
                    </div>
                    <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-muted-foreground">
                      {JSON.stringify(section.defaults, null, 2)}
                    </pre>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="space-y-4">
          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">读取优先级</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <div className="rounded-lg border border-border bg-secondary/20 p-3">
                <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
                  <Database className="size-4" />
                  运行时可变配置
                </div>
                <div>{data?.readPriorityModel.runtimeMutable.join(" -> ") ?? "--"}</div>
              </div>
              <div className="rounded-lg border border-border bg-secondary/20 p-3">
                <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
                  <Database className="size-4" />
                  部署时固定配置
                </div>
                <div>{data?.readPriorityModel.deploymentImmutable.join(" -> ") ?? "--"}</div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">最近变更审计</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[520px] pr-4">
                <div className="space-y-3">
                  {audits.map((audit) => (
                    <div key={audit.id} className="rounded-lg border border-border bg-secondary/20 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-medium text-foreground">{audit.action}</div>
                        <Badge variant="outline">{audit.status}</Badge>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {audit.timestamp} · {audit.user}
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">{audit.details}</div>
                    </div>
                  ))}
                  {!isLoading && audits.length === 0 ? (
                    <div className="text-sm text-muted-foreground">当前还没有配置变更审计记录。</div>
                  ) : null}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
