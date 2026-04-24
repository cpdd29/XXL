# platform 平台适配层

`reception/platform` 负责对后端与运行时能力做统一适配，供各业务模块调用。

## 子目录说明

- `api`：HTTP 请求客户端、鉴权存储、错误模型
- `query`：React Query 客户端与 key 规范
- `runtime`：运行时监控相关适配

## 边界

- 业务模块通过平台层访问后端，避免重复封装请求逻辑。
