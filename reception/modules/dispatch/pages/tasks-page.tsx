"use client"

import { startTransition, useState } from "react"
import { ListTodo, Search } from "lucide-react"
import { Card, CardContent } from "@/shared/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/shared/ui/empty"
import { Input } from "@/shared/ui/input"
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs"

export default function TasksPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [activeTab, setActiveTab] = useState("all")

  const handleSearchChange = (value: string) => {
    startTransition(() => {
      setSearchQuery(value)
    })
  }

  const handleStatusChange = (value: string) => {
    startTransition(() => {
      setActiveTab(value)
    })
  }

  return (
    <div className="flex h-full flex-col p-6">
      <Tabs value={activeTab} onValueChange={handleStatusChange} className="flex-1 gap-4">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="pending">待处理</TabsTrigger>
            <TabsTrigger value="running">运行中</TabsTrigger>
            <TabsTrigger value="completed">已完成</TabsTrigger>
            <TabsTrigger value="failed">失败</TabsTrigger>
          </TabsList>

          <div className="relative w-full max-w-md md:ml-auto md:w-80">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索任务标题、描述、Agent 或渠道..."
              value={searchQuery}
              onChange={(event) => handleSearchChange(event.target.value)}
              className="bg-secondary pl-10"
            />
          </div>
        </div>

        <Card className="bg-card">
          <CardContent className="p-8">
            <Empty className="border-border py-12">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <ListTodo className="size-5" />
                </EmptyMedia>
                <EmptyTitle>当前没有可展示的任务</EmptyTitle>
                <EmptyDescription>
                  执行任务列表为空时，会在这里展示待处理、运行中和已完成的任务记录。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </CardContent>
        </Card>
      </Tabs>
    </div>
  )
}
