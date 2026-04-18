import Link from "next/link"
import {
  Building2,
  ExternalLink,
  Layers3,
  Lightbulb,
  MoonStar,
  Palette,
  Route,
  Sparkles,
  SunMedium,
  Trees,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { SkyscraperScenePreview } from "@/components/skyscraper/skyscraper-scene-preview"

const skylineFloors = [
  { id: "roof", label: "屋顶层", title: "停机坪 + 设备塔", mood: "双态差异最大", detail: "直升机、通信塔、屋顶花园、夜间告警灯" },
  { id: "l7", label: "L7", title: "高管办公层", mood: "夜景主灯层", detail: "大面积玻璃、长条办公区、夜间暖灯明显" },
  { id: "l6", label: "L6", title: "协作与会议层", mood: "白天通透", detail: "会议桌、协作区、玻璃隔断和屏幕墙" },
  { id: "l5", label: "L5", title: "研发工作层", mood: "模块轮换", detail: "工位、边柜、绿植、屏幕群作为主要重复模块" },
  { id: "l4", label: "L4", title: "运营与监控层", mood: "状态映射层", detail: "后续适合映射 workflow / alerts / tools 等业务状态" },
  { id: "l3", label: "L3", title: "任务调度层", mood: "发光层重点", detail: "夜间窗口发光、离线窗口、告警窗口都适合从这里验证" },
  { id: "l2", label: "L2", title: "接待与门厅层", mood: "近景识别层", detail: "门厅和街道连接，最能体现人流和入口质感" },
]

const layerChecklist = [
  { title: "结构层", description: "楼体外框、梁柱、门厅、电梯井，共用白天 / 夜晚结构。", icon: Building2 },
  { title: "反射层", description: "白天高光玻璃与夜晚暗反射分离，避免整张图硬切换。", icon: SunMedium },
  { title: "灯光层", description: "室内暖光、logo 发光、屏幕亮区单独开关。", icon: Lightbulb },
  { title: "环境层", description: "天空、远景楼群、月亮、云层、街道和树阵单独管理。", icon: Trees },
]

const preparationChecklist = [
  { title: "前端样式页", status: "已完成", tone: "bg-success/10 text-success", detail: "完成静态预览、图层开关和完整展示壳。" },
  { title: "静态资源首批", status: "已完成", tone: "bg-success/10 text-success", detail: "日景 / 夜景 SVG 母版、背景、楼体、玻璃、室内、街道和特效层已生成。" },
  { title: "PixiJS 场景接管", status: "已完成", tone: "bg-success/10 text-success", detail: "场景已改为 Pixi canvas，并完成 V2 hero scene 接管。" },
  { title: "V2 主视觉重构", status: "已完成", tone: "bg-success/10 text-success", detail: "使用参考母版重建 3/4 视角主楼、屋顶和街区环境基线。" },
  { title: "正式美术拆层", status: "下一步", tone: "bg-warning/10 text-warning-foreground", detail: "从重建 scene plates 继续拆出屋顶、窗光、logo、街道等正式交互资源。" },
]

export default function VisualizationSkyscraperPage() {
  return (
    <div className="min-h-full bg-background px-6 py-8 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <div className="relative overflow-hidden rounded-3xl border border-border bg-card px-6 py-8 shadow-sm lg:px-8 lg:py-10">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(121,207,255,0.18),transparent_28%),radial-gradient(circle_at_75%_10%,rgba(255,194,107,0.12),transparent_22%),radial-gradient(circle_at_bottom,rgba(87,115,255,0.1),transparent_34%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(78,123,255,0.2),transparent_28%),radial-gradient(circle_at_78%_16%,rgba(255,175,83,0.16),transparent_24%),radial-gradient(circle_at_bottom,rgba(26,39,74,0.42),transparent_36%)]" />
          <div className="relative">
            <Badge variant="secondary">可视视图 / 摩天大厦</Badge>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground lg:text-5xl">
              PixiJS Hero Scene 摩天大厦
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground lg:text-base">
              当前页面已经切到 V2 主视觉重构方案，先根据参考图母版重建转角摩天楼、屋顶设备和街区氛围，再继续拆成正式可交互的 Pixi 图层。
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button asChild variant="outline">
                <Link href="/skyscraper-assets-v2/meta/manifest.json" target="_blank">
                  查看 V2 manifest
                  <ExternalLink className="size-4" />
                </Link>
              </Button>
              <Badge variant="secondary" className="px-3 py-2 text-xs font-normal">
                方案文档：`/Users/xiaoyuge/Documents/XXL/SKYSCRAPER_PIXEL_IMPLEMENTATION_PLAN.md`
              </Badge>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card className="border-border bg-card/80">
            <CardContent className="flex items-start gap-4 p-5">
              <div className="rounded-2xl bg-primary/10 p-3 text-primary">
                <Route className="size-5" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground">路由挂载</div>
                <div className="mt-2 text-sm leading-6 text-muted-foreground">`/visualization/skyscraper`</div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border bg-card/80">
            <CardContent className="flex items-start gap-4 p-5">
              <div className="rounded-2xl bg-sky-500/10 p-3 text-sky-600 dark:text-sky-300">
                <Layers3 className="size-5" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground">首批资源层</div>
                <div className="mt-2 text-sm leading-6 text-muted-foreground">scene plates、昼夜底板、玻璃高光、窗光覆盖、街道光带、前景遮挡</div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border bg-card/80">
            <CardContent className="flex items-start gap-4 p-5">
              <div className="rounded-2xl bg-amber-500/10 p-3 text-amber-600 dark:text-amber-300">
                <SunMedium className="size-5" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground">日景基线</div>
                <div className="mt-2 text-sm leading-6 text-muted-foreground">蓝天、玻璃转角主楼、通透办公室、明亮街区和轻量镜头漂移</div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border bg-card/80">
            <CardContent className="flex items-start gap-4 p-5">
              <div className="rounded-2xl bg-indigo-500/10 p-3 text-indigo-600 dark:text-indigo-300">
                <MoonStar className="size-5" />
              </div>
              <div>
                <div className="text-sm font-medium text-foreground">夜景基线</div>
                <div className="mt-2 text-sm leading-6 text-muted-foreground">暖光办公室、夜色楼体、logo 发光、街道车灯和前景遮挡</div>
              </div>
            </CardContent>
          </Card>
        </div>

        <SkyscraperScenePreview />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <Card className="border-border bg-card/80">
              <CardHeader>
                <CardTitle>楼层编排</CardTitle>
                <CardDescription>当前先保留楼层职能设定，后续等主视觉拆层完成后再接业务映射。</CardDescription>
              </CardHeader>
            <CardContent className="grid gap-3">
              {skylineFloors.map((floor) => (
                <div
                  key={floor.id}
                  className="grid gap-3 rounded-2xl border border-border bg-secondary/20 p-4 md:grid-cols-[92px_minmax(0,1fr)_160px]"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{floor.label}</Badge>
                    <div className="text-xs text-muted-foreground">场景层</div>
                  </div>
                  <div>
                    <div className="text-sm font-medium text-foreground">{floor.title}</div>
                    <div className="mt-1 text-sm leading-6 text-muted-foreground">{floor.detail}</div>
                  </div>
                  <div className="rounded-xl bg-background/70 px-3 py-2 text-sm text-muted-foreground">
                    视觉重点：{floor.mood}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="border-border bg-card/80">
              <CardHeader>
                <CardTitle>资源拆层重点</CardTitle>
                <CardDescription>参考 `bright.png` / `dark.png` 的细节来源，但运行时使用重建资产。</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3">
                {layerChecklist.map((item) => (
                  <div key={item.title} className="rounded-2xl border border-border bg-secondary/20 p-4">
                    <div className="flex items-center gap-3">
                      <div className="rounded-xl bg-primary/10 p-2 text-primary">
                        <item.icon className="size-4" />
                      </div>
                      <div className="text-sm font-medium text-foreground">{item.title}</div>
                    </div>
                    <div className="mt-3 text-sm leading-6 text-muted-foreground">{item.description}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="border-border bg-card/80">
              <CardHeader>
                <CardTitle>开发状态</CardTitle>
                <CardDescription>这轮先把构图和相似度拉上来，不对接口。</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3">
                {preparationChecklist.map((item) => (
                  <div key={item.title} className="rounded-2xl border border-border bg-secondary/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-foreground">{item.title}</div>
                      <Badge variant="secondary" className={item.tone}>
                        {item.status}
                      </Badge>
                    </div>
                    <div className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>

        <Card className="border-dashed border-border bg-card/70">
          <CardHeader>
            <CardTitle>页面当前性质</CardTitle>
            <CardDescription>这已经不是旧的模块验证版，而是一版以参考图母版重建的 Pixi hero scene。</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-4">
            <div className="rounded-2xl border border-border bg-secondary/20 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Palette className="size-4 text-primary" />
                视觉方向
              </div>
              <div className="mt-2 text-sm leading-6 text-muted-foreground">
                已切换成参考图导向的转角摩天楼主视觉，不再是正立面占位楼体。
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-secondary/20 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Layers3 className="size-4 text-primary" />
                图层策略
              </div>
              <div className="mt-2 text-sm leading-6 text-muted-foreground">
                当前先按 scene plates、玻璃、灯光、街道、遮挡进行叠层，后续再拆正式 atlas。
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-secondary/20 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Sparkles className="size-4 text-primary" />
                可演示性
              </div>
              <div className="mt-2 text-sm leading-6 text-muted-foreground">
                页面已支持昼夜切换、轻量视差和氛围动态，适合继续追相似度。
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-secondary/20 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Route className="size-4 text-primary" />
                下一阶段
              </div>
              <div className="mt-2 text-sm leading-6 text-muted-foreground">
                把重建主视觉继续拆层后，再把业务状态逐层映射进场景。
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
