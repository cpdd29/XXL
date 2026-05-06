# 前端业务模块（modules）

`reception/modules` 承载业务域逻辑与页面实现，`reception/app` 只保留路由壳。

## 目录约定

- `modules/<domain>/pages/*.tsx`：该域页面实现
- `modules/<domain>/hooks/*.ts`：该域数据访问与状态逻辑
- `modules/<domain>/components/*.tsx`：该域私有组件
- `modules/navigation/*`：侧边栏与导航元数据

## 当前模块

- `workbench`：工作台/总览
- `dispatch`：任务下发与任务详情
- `agent-config`：Agent 配置接入
- `capability`：工具、Skill、外部连接能力
- `knowledge`：知识仓、同步记录、检索日志管理
- `executor-config`：执行器接入配置（CLI/HTTP执行器）
- `intake`：接入层运营视图（接待 Agent 状态、准入执行态、接入事件流）
- `organization`：租户与人员画像
- `security`：安全运营与审计视图
- `settings`：系统设置
- `auth`：登录与会话
- `navigation`：导航配置

## 边界要求

- 模块之间不直接互调 `hooks`，跨域能力通过 `platform` 或 `shared` 抽象。
- 新页面先落在对应模块 `pages`，再由 `app/*/page.tsx` 做路由导出。
