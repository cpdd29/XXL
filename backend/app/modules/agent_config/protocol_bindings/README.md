# 租户协议与外接 Agent 路由绑定

## 模块职责
本模块负责为租户和 Agent 绑定外接对话服务协议，决定请求应路由到哪个 Hermes 实例，以及采用哪种记忆策略和命名空间策略。

本模块不负责客户准入，不负责客户画像，不负责长期记忆内容本身。

## 核心功能
1. 绑定 `tenant_id` 与 `agent_id`
2. 绑定 `protocol_id` 与 `protocol_version`
3. 绑定目标 Hermes 实例
4. 绑定运行时记忆模式
5. 绑定命名空间隔离策略
6. 为接待层提供统一的外接对话调用配置

## 典型字段
- `binding_id`
- `tenant_id`
- `agent_id`
- `protocol_id`
- `protocol_version`
- `target_provider`
- `target_instance_id`
- `target_base_url`
- `runtime_memory_mode`
- `memory_namespace_strategy`
- `enabled`
- `created_at`
- `updated_at`

## 运行时记忆模式
- `platform_stateless`
  - 平台主导记忆：平台每次注入完整上下文
  - Hermes 无状态执行：仅基于本次请求回复
  - 回复后是否写回画像/长期记忆由平台决定

## 命名空间策略
- `tenant`
- `tenant_customer`
- `tenant_session`
- `tenant_task`

## 边界说明
本模块定义平台如何调用 Hermes，不定义 Hermes 内部如何实现模型调用。

后期替换 Hermes 或新增其他对话 Agent 时，应优先复用本模块提供的标准协议绑定能力。
