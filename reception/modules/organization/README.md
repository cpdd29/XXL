# organization 模块

## 模块职责

负责租户管理、人员画像列表与用户详情。

## 当前路由

- 无独立前端路由（已收敛至租户管理页面内联展示）

## 主要文件

- `pages/users-page.tsx`
- `pages/user-detail-page.tsx`
- `hooks/use-users.ts`

## 注意事项

- 该模块是“租户管理 + 人员画像”聚合层，不做 Agent/工具配置逻辑。
- 导出与管理接口统一经过 `platform/api`。
