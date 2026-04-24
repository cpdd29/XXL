# workbench 模块

## 模块职责

负责首页工作台与总览统计展示。

## 当前路由

- `/dashboard`

## 主要文件

- `pages/dashboard-page.tsx`
- `hooks/use-dashboard.ts`

## 注意事项

- 工作台作为聚合展示层，不直接写入业务数据。
- 指标口径由后端定义，前端只做展示与轻量交互。
