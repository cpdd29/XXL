# capability 模块

## 模块职责

负责工具能力管理，包括工具源、工具目录、Skill 注册与管理、外部连接管理。

## 当前路由

- `/tools`

## 主要文件

- `pages/tools-page.tsx`
- `hooks/use-tools.ts`
- `hooks/use-tool-sources.ts`
- `hooks/use-brain-skills.ts`
- `hooks/use-external-connections.ts`
- `components/*`

## 注意事项

- 该模块是“产品赋能”主入口，避免混入与组织管理、任务执行无关逻辑。
- 模型与 Agent 的绑定配置应交由对应模块，不在这里做跨域写入。
