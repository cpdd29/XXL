import Link from "next/link"
import { Building2, ChevronRight, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function VisualizationPage() {
  return (
    <div className="min-h-full bg-background px-6 py-8 lg:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="rounded-3xl border border-border bg-card px-6 py-8 shadow-sm">
          <Badge variant="secondary" className="gap-1">
            <Sparkles className="size-3.5" />
            可视视图
          </Badge>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground lg:text-4xl">
            可视化场景入口
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground lg:text-base">
            这里作为所有视觉化场景的父路由。后续摩天大厦、像素城市场景和其他专用可视页面都统一挂在这个层级下。
          </p>
        </div>

        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle>已创建的可视页面</CardTitle>
            <CardDescription>当前先保留一个干净的摩天大厦开发入口。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-4 rounded-2xl border border-border bg-secondary/20 p-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-primary/10 p-2 text-primary">
                  <Building2 className="size-5" />
                </div>
                <div>
                  <div className="text-base font-medium text-foreground">摩天大厦</div>
                  <div className="mt-1 text-sm leading-6 text-muted-foreground">
                    路由路径：`/visualization/skyscraper`
                  </div>
                </div>
              </div>

              <Button asChild>
                <Link href="/visualization/skyscraper">
                  打开页面
                  <ChevronRight className="size-4" />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
