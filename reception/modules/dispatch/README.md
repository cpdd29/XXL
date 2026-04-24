# dispatch 模块

## 模块职责

负责任务下发、任务列表、任务详情展示与任务动作操作。

## 当前路由

- `/tasks`
- `/tasks/[taskId]`

## 主要文件

- `pages/tasks-page.tsx`
- `pages/task-detail-page.tsx`
- `hooks/use-tasks.ts`

## 注意事项

- 任务编排策略（单 Agent / 多 Agent）由后端决策，前端仅做配置展示和触发。
- 与安全拦截相关展示放在 `security` 模块，避免职责重叠。
