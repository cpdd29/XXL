# app 路由壳层

`reception/app` 仅保留 Next.js 路由入口文件，不存放复杂业务逻辑。

## 规则

- `app/**/page.tsx` 只做模块页面转发。
- `app/**/layout.tsx` 只做布局装配。
- 业务实现统一在 `reception/modules/*`。
