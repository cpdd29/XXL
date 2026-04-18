"use client"

import { useEffect, useState } from "react"
import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  SkyscraperPixiScene,
  type SkyscraperPixiMode,
} from "@/components/skyscraper/skyscraper-pixi-scene"

type SceneMode = "auto" | "day" | "night"

function layerButtonClass(isActive: boolean) {
  return isActive ? "bg-primary text-primary-foreground hover:bg-primary/90" : ""
}

export function SkyscraperScenePreview() {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  const [sceneMode, setSceneMode] = useState<SceneMode>("auto")
  const [showGlass, setShowGlass] = useState(true)
  const [showGlow, setShowGlow] = useState(true)
  const [showStreet, setShowStreet] = useState(true)
  const [showOccluders, setShowOccluders] = useState(true)

  useEffect(() => {
    setMounted(true)
  }, [])

  const resolvedMode: SkyscraperPixiMode =
    sceneMode === "auto" ? (resolvedTheme === "dark" ? "night" : "day") : sceneMode

  const isNight = resolvedMode === "night"

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_340px]">
      <div className="rounded-[28px] border border-border bg-card p-4 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">PixiJS Hero Scene V2</div>
            <div className="mt-1 text-sm text-muted-foreground">
              当前已切到参考图母版重建方案，先把转角楼体、屋顶和街区氛围重建出来，再逐步拆成正式可交互资源。
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={sceneMode === "auto" ? "default" : "outline"}
              className={layerButtonClass(sceneMode === "auto")}
              onClick={() => setSceneMode("auto")}
            >
              <Monitor className="size-4" />
              跟随主题
            </Button>
            <Button
              size="sm"
              variant={sceneMode === "day" ? "default" : "outline"}
              className={layerButtonClass(sceneMode === "day")}
              onClick={() => setSceneMode("day")}
            >
              <Sun className="size-4" />
              白天
            </Button>
            <Button
              size="sm"
              variant={sceneMode === "night" ? "default" : "outline"}
              className={layerButtonClass(sceneMode === "night")}
              onClick={() => setSceneMode("night")}
            >
              <Moon className="size-4" />
              夜晚
            </Button>
          </div>
        </div>

        <div className="mt-4 relative overflow-hidden rounded-[24px] border border-border bg-secondary/30">
          <div className="relative mx-auto aspect-[2/3] w-full max-w-[640px] overflow-hidden">
            <SkyscraperPixiScene
              className="absolute inset-0"
              mode={resolvedMode}
              showGlass={showGlass}
              showGlow={showGlow}
              showStreet={showStreet}
              showOccluders={showOccluders}
            />

            {mounted ? (
              <div className="absolute left-4 top-4 flex gap-2">
                <Badge variant="secondary">{sceneMode === "auto" ? "跟随主题" : sceneMode}</Badge>
                <Badge variant="secondary">{isNight ? "夜景" : "日景"}</Badge>
                <Badge variant="secondary">Pixi Runtime</Badge>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-[24px] border border-border bg-card p-4 shadow-sm">
          <div className="text-sm font-medium text-foreground">图层控制</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={showGlass ? "default" : "outline"}
              className={layerButtonClass(showGlass)}
              onClick={() => setShowGlass((value) => !value)}
            >
              玻璃反射
            </Button>
            <Button
              size="sm"
              variant={showGlow ? "default" : "outline"}
              className={layerButtonClass(showGlow)}
              onClick={() => setShowGlow((value) => !value)}
            >
              室内发光
            </Button>
            <Button
              size="sm"
              variant={showStreet ? "default" : "outline"}
              className={layerButtonClass(showStreet)}
              onClick={() => setShowStreet((value) => !value)}
            >
              街道层
            </Button>
            <Button
              size="sm"
              variant={showOccluders ? "default" : "outline"}
              className={layerButtonClass(showOccluders)}
              onClick={() => setShowOccluders((value) => !value)}
            >
              前景遮挡
            </Button>
          </div>
        </div>

        <div className="rounded-[24px] border border-border bg-card p-4 shadow-sm">
          <div className="text-sm font-medium text-foreground">V2 已接管内容</div>
          <div className="mt-3 space-y-2 text-sm text-muted-foreground">
            <div>主视觉：已换成按 `bright.png / dark.png` 重建的 SVG scene plates。</div>
            <div>视角：从正立面模块楼体切到 `3/4` 转角主楼构图。</div>
            <div>动态：镜头漂移、玻璃反射、夜间窗光、车流光带和前景遮挡已接入。</div>
            <div>交互：支持主题跟随、昼夜切换和鼠标轻量视差。</div>
          </div>
        </div>

        <div className="rounded-[24px] border border-dashed border-border bg-card/70 p-4">
          <div className="text-sm font-medium text-foreground">下一步替换重点</div>
          <div className="mt-3 space-y-2 text-sm text-muted-foreground">
            <div>把 scene plates 继续拆成楼体、屋顶、logo、窗户、街道等正式图层。</div>
            <div>把当前近似发光区替换成真实窗户 mask，而不是宽矩形覆盖。</div>
            <div>接口接入前，这一版先追求相似度和构图完成度，不急着做状态映射。</div>
          </div>
        </div>
      </div>
    </div>
  )
}
