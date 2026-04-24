# auth 模块

## 模块职责

负责登录、会话状态、令牌生命周期相关前端逻辑。

## 当前路由

- `/login`

## 主要文件

- `pages/login-page.tsx`
- `hooks/use-auth.ts`

## 注意事项

- 认证态来源统一走 `platform/api/auth-storage` 与 `platform/api/client`。
- 禁止在业务模块重复实现令牌存储逻辑。
