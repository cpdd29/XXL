"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { useGeneralSettings, useUpdateGeneralSettings } from "@/hooks/use-settings"
import { toast } from "@/hooks/use-toast"
import type { GeneralSettings } from "@/types"

const defaultSettings: GeneralSettings = {
  dashboardAutoRefresh: true,
  showSystemStatus: true,
}

export default function GeneralSettingsPage() {
  const { data, isLoading, isFetching, error, refetch } = useGeneralSettings()
  const updateGeneralSettings = useUpdateGeneralSettings()
  const [draft, setDraft] = useState<GeneralSettings>(defaultSettings)

  useEffect(() => {
    if (data?.settings) {
      setDraft(data.settings)
    }
  }, [data])

  const savedSettings = data?.settings ?? defaultSettings
  const hasLoadedSettings = Boolean(data?.settings)
  const isSaving = updateGeneralSettings.isPending
  const isDirty =
    draft.dashboardAutoRefresh !== savedSettings.dashboardAutoRefresh ||
    draft.showSystemStatus !== savedSettings.showSystemStatus

  const handleSave = async () => {
    try {
      const response = await updateGeneralSettings.mutateAsync(draft)
      setDraft(response.settings)
      toast({
        title: "通用设置已保存",
        description: "新的界面行为配置已经写入后端。",
      })
    } catch (saveError) {
      toast({
        title: "保存失败",
        description: saveError instanceof Error ? saveError.message : "未知错误",
      })
    }
  }

  const resetToSaved = () => {
    setDraft(savedSettings)
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-2xl font-bold text-foreground">通用设置</h1>
        <div className="space-y-1 text-right">
          <p className="text-sm text-muted-foreground">
            管理系统的基础显示和交互行为
          </p>
          <p className="text-xs text-muted-foreground">
            {hasLoadedSettings
              ? data?.updatedAt
                ? `最近保存：${data.updatedAt}`
                : "当前为默认配置"
              : isLoading
                ? "正在读取配置..."
                : "尚未加载到可编辑配置"}
          </p>
        </div>
      </div>

      <Card className="bg-card">
        <CardHeader>
          <CardTitle className="text-base">界面选项</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">实时刷新控制台</p>
              <p className="text-sm text-muted-foreground">
                启用后会持续刷新 Dashboard 数据
              </p>
            </div>
            <Switch
              checked={draft.dashboardAutoRefresh}
              disabled={!hasLoadedSettings || isLoading || isSaving}
              onCheckedChange={(checked) =>
                setDraft((current) => ({ ...current, dashboardAutoRefresh: checked }))
              }
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">显示系统提示</p>
              <p className="text-sm text-muted-foreground">
                页面顶部展示系统运行状态
              </p>
            </div>
            <Switch
              checked={draft.showSystemStatus}
              disabled={!hasLoadedSettings || isLoading || isSaving}
              onCheckedChange={(checked) =>
                setDraft((current) => ({ ...current, showSystemStatus: checked }))
              }
            />
          </div>
          {error ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              配置加载失败：{error instanceof Error ? error.message : "未知错误"}
            </div>
          ) : null}
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={() => void refetch()}
              disabled={isSaving || isFetching}
            >
              {isFetching ? "刷新中..." : "重新加载"}
            </Button>
            <Button
              variant="outline"
              onClick={resetToSaved}
              disabled={!hasLoadedSettings || !isDirty || isSaving}
            >
              撤销修改
            </Button>
            <Button
              onClick={() => void handleSave()}
              disabled={!hasLoadedSettings || !isDirty || isSaving}
            >
              {isSaving ? "保存中..." : "保存设置"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
