# 前端路由与页面清单

更新时间：2026-04-24

## 路由映射（app -> modules）

| 路由 | 路由入口 | 页面实现 |
| --- | --- | --- |
| `/` | `app/page.tsx` | `shared/providers/home-redirect.tsx` |
| `/login` | `app/login/page.tsx` | `modules/auth/pages/login-page.tsx` |
| `/dashboard` | `app/dashboard/page.tsx` | `modules/workbench/pages/dashboard-page.tsx` |
| `/agents` | `app/agents/page.tsx` | `modules/agent-config/pages/agents-page.tsx` |
| `/tasks` | `app/tasks/page.tsx` | `modules/dispatch/pages/tasks-page.tsx` |
| `/tasks/[taskId]` | `app/tasks/[taskId]/page.tsx` | `modules/dispatch/pages/task-detail-page.tsx` |
| `/tools` | `app/tools/page.tsx` | `modules/capability/pages/tools-page.tsx` |
| `/users` | `app/users/page.tsx` | `modules/organization/pages/users-page.tsx` |
| `/users/[userId]` | `app/users/[userId]/page.tsx` | `modules/organization/pages/user-detail-page.tsx` |
| `/security` | `app/security/page.tsx` | `modules/security/pages/security-page.tsx` |
| `/settings/general` | `app/settings/general/page.tsx` | `modules/settings/pages/general-settings-page.tsx` |
| `/settings/channel-integration` | `app/settings/channel-integration/page.tsx` | `modules/settings/pages/channel-integration-settings-page.tsx` |
| `/settings/agent-api` | `app/settings/agent-api/page.tsx` | `modules/settings/pages/agent-api-settings-page.tsx` |
| `/settings/tenants` | `app/settings/tenants/page.tsx` | `modules/settings/pages/tenant-settings-page.tsx` |

## 备注

- `app/*` 为路由壳，业务实现集中在 `modules/*`。
- 导航配置在 `modules/navigation/sidebar-nav.ts`。
