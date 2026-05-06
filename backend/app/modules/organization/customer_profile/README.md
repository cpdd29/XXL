# 租户客户画像

## 模块职责
租户客户画像模块负责维护租户下客户的基础资料、渠道绑定关系、长期偏好和服务状态。

本模块是客户主档，不是会话上下文，不是 Hermes 运行时记忆。

## 核心功能
1. 保存客户基础资料
2. 保存客户与渠道账号的绑定关系
3. 保存客户归属租户
4. 保存客户服务状态
5. 为接待层、调度层、长期记忆层提供客户主数据

## 典型字段
- `profile_id`
  人员画像主键，也是租户下人员的稳定标识。
- `tenant_id`
  租户主键，用于确定画像归属的租户边界。
- `customer_id`
  租户下该人员的业务客户编号，不等同于人员主键；当前实现里通常由 `tenant_id + service_code + mobile` 派生。
- `company_name`
- `contact_name`
- `mobile`
- `channel_accounts`
- `service_status`
- `first_seen_at`
- `last_seen_at`

## 与其他模块关系
- 由 `customer_access` 模块首次写入
- 由 `reception` 模块读取归属信息
- 由 `tenant_memory` 模块关联客户长期记忆
- 不负责 Hermes 会话内短期记忆

## 边界说明
客户画像是平台侧结构化主数据。

`customer_id` 应理解为业务编号，不应替代 `profile_id` 作为“当前对话人员”的唯一标识。

不得将 Hermes 临时上下文直接写入客户画像。
