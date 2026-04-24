# platform

平台支撑层。

这里放纯技术底座，不放具体业务模块逻辑。当前收敛原先零散的 `core` / `infrastructure` 中与平台能力强相关的实现。

当前已收敛方向：

- `auth`：认证鉴权
- `config`：运行时配置与系统设置
- `messaging`：NATS、Redis 等通信与缓存能力
- `observability`：运行日志与 trace 导出
- `persistence`：状态持久化与数据库读写
- `contracts`：事件协议、Agent 协议等稳定契约
- `audit`：审计日志写入能力
