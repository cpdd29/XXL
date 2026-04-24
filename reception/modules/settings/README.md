# settings 模块

## 模块职责

负责平台设置，包括通用设置、渠道集成、Agent API、租户设置入口。

## 当前路由

- `/settings/general`
- `/settings/channel-integration`
- `/settings/agent-api`
- `/settings/tenants`

## 主要文件

- `pages/general-settings-page.tsx`
- `pages/channel-integration-settings-page.tsx`
- `pages/agent-api-settings-page.tsx`
- `pages/tenant-settings-page.tsx`
- `hooks/use-settings.ts`

## 注意事项

- 设置项按子域拆分，避免单文件聚合过大。
- 配置写入前需保留后端返回校验信息，前端不绕过校验。
