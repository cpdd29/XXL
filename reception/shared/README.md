# shared 共享层

`reception/shared` 存放跨模块复用能力，不绑定具体业务域。

## 子目录说明

- `ui`：通用 UI 组件
- `layout`：全局布局组件
- `providers`：全局 Provider
- `hooks`：跨域通用 hooks
- `types`：跨域类型定义
- `components`：复用组件（非业务域私有）
- `utils.ts`：通用工具函数

## 边界

- shared 不能依赖具体业务模块（避免循环依赖）。
