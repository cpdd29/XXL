# NATS Event Protocol

更新时间：2026-04-13

## 1. 目的

主脑内 NATS 只承担协议化分发，不承担事实真源存储。

这份规范的目标是：

- 让主脑内部事件有统一主题、统一 envelope、统一字段语义
- 让外部观察者、前端订阅端、后台 worker 都能按协议消费
- 严格限制哪些数据可以离开主脑真源

## 2. 总原则

### 2.1 事件总线不是事实真源

NATS 上的消息只用于：

- 调度
- 状态通知
- 观测
- 重试驱动
- 跨进程同步

NATS 上的消息不作为以下对象的事实真源：

- task
- workflow run
- step
- manager_packet
- memory
- audit
- 安全裁决状态

这些真源必须保留在本地持久层或主脑内存态，由主脑负责最终一致性。

### 2.2 大脑封闭、触手外置、协议统一

- 大脑封闭：裁决、记忆、审计、真源状态都在本地主脑
- 触手外置：MCP、Skill、外接 Agent 可以独立部署
- 协议统一：所有内部总线消息必须遵守统一字段规范

## 3. 统一 envelope

所有标准事件统一字段：

- `event_id`
- `event_name`
- `event_version`
- `message_type`
- `subject`
- `aggregate.type`
- `aggregate.id`
- `trace.trace_id`
- `trace.request_id`
- `trace.parent_event_id`
- `routing.partition_key`
- `routing.idempotency_key`
- `timing.emitted_at`
- `timing.available_at`
- `timing.expires_at`
- `timing.lease_until`
- `source.kind`
- `source.id`
- `target.kind`
- `target.id`
- `payload`

其中：

- `message_type` 只允许 `command | event | result | snapshot`
- `routing.idempotency_key` 必须可重复计算，不能依赖随机值
- `timing.lease_until` 只在存在租约语义时填写

## 4. 主题划分

### 4.1 Workflow Run

- `brain.workflow.run.created`
- `brain.workflow.run.updated`
- `brain.workflow.run.completed`
- `brain.workflow.run.failed`
- `brain.workflow.run.snapshot`
- `brain.workflow.run.keepalive`

### 4.2 Agent Execution

- `brain.agent.execution.request`
- `brain.agent.execution.claimed`
- `brain.agent.execution.started`
- `brain.agent.execution.completed`
- `brain.agent.execution.failed`

### 4.3 Internal Event Delivery

- `brain.internal_event.delivery.requested`
- `brain.internal_event.delivery.claimed`
- `brain.internal_event.delivery.completed`
- `brain.internal_event.delivery.failed`
- `brain.internal_event.delivery.retried`

## 5. 数据边界

### 5.1 可以进入总线的内容

只允许进入总线的内容：

- 调度标识
- 状态字段
- 时间字段
- 聚合标识
- trace / request / correlation 关联信息
- 计数型摘要
- 简化后的运行摘要

### 5.2 禁止进入总线的内容

以下内容禁止以完整对象进入总线：

- 完整 `task`
- 完整 `run`
- 完整 `step`
- 完整 `manager_packet`
- 完整 `memory`
- 完整 `audit`
- 任意上下文补丁全文
- 任意主脑安全裁决原始细节

如果业务需要感知它们，只能发送摘要对象，例如：

- `summary_only: true`
- `summary_kind: workflow_run`
- `node_count`
- `log_count`
- `active_edge_count`
- `dispatch_context` 中允许的安全字段

## 6. 前后端消费约定

### 6.1 前端

前端主要消费：

- `snapshot`
- `keepalive`
- 必要的 run 摘要事件

前端实时层不应把总线摘要当成详情真源。详情仍应优先来自 API 查询或本地已持有状态。

### 6.2 后端内部 worker

后端内部 worker 主要消费：

- `command`
- `event`
- `result`

它们用来驱动：

- 执行请求
- 状态推进
- 重试
- 失败处理

## 7. 兼容策略

当前阶段保留部分 legacy subject / payload 兼容：

- 旧 subject 可继续发布一段时间
- 新 `brain.*` subject 并行发布
- 历史消费方逐步迁移到统一 envelope

迁移完成后，再移除 legacy 发布。

## 8. 当前实现约束

当前代码中已经落地：

- workflow realtime 总线发布摘要 payload，本地广播保留详情
- internal event delivery 进入统一事件协议
- agent execution 使用统一 subject 命名
- payload 摘要化、敏感字段剥离、事件大小控制

结论：

主脑内部可以继续使用 NATS 提升解耦和跨进程协作，但绝不能把它升级成主脑真源。真源始终在本地持久层和主脑控制面。
