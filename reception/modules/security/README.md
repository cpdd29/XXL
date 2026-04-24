# security 模块

## 模块职责

负责安全运营视图，包括审计日志、告警中心、规则与处置相关页面交互。

## 当前路由

- `/security`

## 主要文件

- `pages/security-page.tsx`
- `hooks/use-security.ts`

## 注意事项

- 安全能力在系统链路中定位为实时监听与阻断，不直接替代业务回复层。
- 页面只展示与操作安全策略，不承载 Hermes 对话逻辑。
