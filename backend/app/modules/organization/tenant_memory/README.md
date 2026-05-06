# 平台长期记忆

## 模块职责
平台长期记忆模块负责保存租户级、客户级、任务结论级的长期可复用信息，是平台的长期认知主库。

本模块不负责 Hermes 当前会话的短期工作记忆。

## 核心功能
1. 保存 `tenant_soul` 或租户协议长期内容
2. 保存租户规则与业务事实
3. 保存客户长期偏好与历史结论
4. 保存任务完成后的可复用摘要
5. 为接待、调度、多 Agent 协作提供跨会话长期记忆支持

## 推荐记忆类型
- `tenant_soul`
- `tenant_rule`
- `customer_preference`
- `business_fact`
- `decision`
- `task_result`
- `service_policy`

## 典型字段
- `memory_id`
- `tenant_id`
- `scope`
- `subject_id`
- `memory_type`
- `title`
- `content`
- `summary`
- `source`
- `importance`
- `created_at`
- `updated_at`

## 作用域说明
- `tenant`：租户级长期记忆
- `customer`：客户级长期记忆
- `task_summary`：任务结论级长期记忆

## 边界说明
本模块是长期记忆主库。

Hermes 的会话压缩、最近几轮对话、临时工作状态不应直接作为长期记忆原文保存。
