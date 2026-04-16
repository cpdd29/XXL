# NATS Event Protocol TODO

更新时间：2026-04-13
目标：把主脑内部现有 NATS 基础链路，升级成统一、可审计、可重试、可扩展的内部事件协议系统。

## 一、目标定义

这次改造不是“接入 NATS”，而是“规范主脑内所有通过 NATS 流转的事件协议”。

必须达成：

- 统一事件信封
- 统一 subject 命名
- 统一事件类型
- 统一 trace / request / idempotency / lease 字段
- 区分 command / event / result / snapshot
- 保证“事件总线不是事实真源，数据库和本地主脑状态才是真源”

## 二、边界红线

以下内容禁止直接作为 NATS payload 全量广播：

- 完整 task
- 完整 run
- 完整 step
- 完整 manager_packet
- 完整 brain_dispatch_summary
- 完整 memory_items
- 完整安全审计细节
- 完整处罚状态

NATS 中只允许传：

- task_id
- run_id
- workflow_id
- event_id
- event_name
- event_version
- message_type
- trace_id
- request_id
- idempotency_key
- attempt
- max_attempts
- lease_until
- source
- target
- 必要摘要 payload

原则：

- 事件用于通知、调度、回执
- 事实状态以本地主脑持久化层为准
- 外部观察者收到事件后，如需详情，应回查 task/run 真源

## 三、现状问题

当前已具备：

- `backend/app/core/nats_event_bus.py`
- `backend/app/services/workflow_realtime_service.py`
- `backend/app/services/agent_execution_worker_service.py`
- `backend/app/core/agent_protocol.py`
- `workflow_service` / `internal_event_delivery_poller_service` 的内部事件投递链路

当前主要问题：

1. 事件信封不统一
- workflow realtime 自己拼 payload
- agent execution 走另一套 envelope
- internal event delivery 又是另一套结构

2. subject 命名不统一
- `workflow.runs.*`
- `agent.execution.run`
- `agent.execution.result`
- `agent.execution.event`

3. 语义不统一
- 有的是 command
- 有的是状态通知
- 有的是结果回执
- 有的是前端 snapshot

4. 追踪字段不统一
- 有的地方有 `trace_id`
- 有的地方有 `request_id`
- 有的地方没有统一 `idempotency_key`

5. 事件与事实层边界不清晰
- 某些 payload 携带过多运行态信息
- 没有明确“总线只发摘要，不发真源全量对象”

## 四、协议设计

## 4.1 统一事件信封

新增建议：

- `backend/app/core/event_protocol.py`

统一事件结构：

```python
{
  "event_id": "evt_xxx",
  "event_name": "brain.workflow.run.updated",
  "event_version": "v1",
  "message_type": "event",  # command | event | result | snapshot
  "subject": "brain.workflow.run.updated",
  "aggregate": {
    "type": "workflow_run",
    "id": "run-123"
  },
  "trace": {
    "trace_id": "trace-123",
    "request_id": "req-123",
    "parent_event_id": None
  },
  "routing": {
    "partition_key": "workflow-1",
    "idempotency_key": "workflow.run.updated:run-123:1"
  },
  "timing": {
    "emitted_at": "2026-04-13T12:00:00+00:00",
    "available_at": "2026-04-13T12:00:00+00:00",
    "expires_at": None,
    "lease_until": None
  },
  "source": {
    "kind": "workflow_execution_service",
    "id": "brain-node-1"
  },
  "target": {
    "kind": "workflow_realtime_service",
    "id": "local-subscribers"
  },
  "payload": {}
}
```

必须统一的字段：

- `event_id`
- `event_name`
- `event_version`
- `message_type`
- `subject`
- `aggregate.type`
- `aggregate.id`
- `trace.trace_id`
- `routing.idempotency_key`
- `timing.emitted_at`
- `source.kind`
- `payload`

## 4.2 统一 subject 命名

新增建议：

- `backend/app/core/event_subjects.py`

命名规则：

- `brain.<domain>.<entity>.<action>`

建议 subject：

- `brain.workflow.run.created`
- `brain.workflow.run.updated`
- `brain.workflow.run.completed`
- `brain.workflow.run.failed`
- `brain.workflow.run.snapshot`
- `brain.workflow.run.keepalive`
- `brain.agent.execution.request`
- `brain.agent.execution.claimed`
- `brain.agent.execution.started`
- `brain.agent.execution.completed`
- `brain.agent.execution.failed`
- `brain.internal_event.delivery.requested`
- `brain.internal_event.delivery.claimed`
- `brain.internal_event.delivery.completed`
- `brain.internal_event.delivery.failed`
- `brain.internal_event.delivery.retried`

要求：

- 禁止业务代码继续散写硬编码 subject
- 所有 subject 必须从常量文件引用

## 4.3 统一事件类型

新增建议：

- `backend/app/core/event_types.py`

消息类型：

- `command`
- `event`
- `result`
- `snapshot`

定义要求：

- command：驱动执行
- event：表示事实状态变化
- result：对 command 的回执
- snapshot：供观察层/前端消费的状态快照

## 五、分包开发

### Package N1：协议底座

目标：

- 先把统一协议底座建起来，不先改大面积业务逻辑

范围：

- `backend/app/core/event_protocol.py`
- `backend/app/core/event_subjects.py`
- `backend/app/core/event_types.py`
- `backend/app/core/nats_event_bus.py`

任务：

- [x] 新增 `brain_event_v1` 协议版本常量
- [x] 定义统一 envelope builder
- [x] 定义 envelope normalizer
- [x] 定义 envelope validator
- [x] 定义 subject 常量
- [x] 定义 message_type 常量
- [x] 给 `nats_event_bus.publish_json()` 增加协议校验入口
- [x] 保持旧接口兼容，避免全量调用点一次性爆炸

验收标准：

- 任意内部事件都可以用同一 builder 构造
- subject 不再由业务代码随手拼接
- 不合规 payload 能在开发期被识别

### Package N2：Agent Execution 事件规范化

目标：

- 把现有 agent 执行链路统一成标准 command/result 流

范围：

- `backend/app/services/agent_execution_worker_service.py`
- `backend/app/core/agent_protocol.py`
- 相关测试

任务：

- [x] 统一 `agent.execution.request` 为标准 envelope
- [x] 增加 `brain.agent.execution.claimed`
- [x] 增加 `brain.agent.execution.started`
- [x] 增加 `brain.agent.execution.completed`
- [x] 增加 `brain.agent.execution.failed`
- [x] 统一 `attempt / max_attempts / lease_until`
- [x] 统一 `request_id / trace_id / idempotency_key`
- [x] 保证 worker claim 后的回执事件可追踪

验收标准：

- 单个 agent 执行链能完整追到 request -> claimed -> started -> completed/failed
- lease 和 retry 行为在事件里可观测
- 兼容当前数据库 job 持久化逻辑

### Package N3：Workflow Run 事件规范化

目标：

- 把 workflow realtime 和 workflow 状态事件拆成统一 event + snapshot 双层语义

范围：

- `backend/app/services/workflow_realtime_service.py`
- `backend/app/services/workflow_execution_service.py`
- 相关测试

任务：

- [x] 把 `publish_run_event()` 改为统一 envelope
- [x] 定义 `brain.workflow.run.created`
- [x] 定义 `brain.workflow.run.updated`
- [x] 定义 `brain.workflow.run.completed`
- [x] 定义 `brain.workflow.run.failed`
- [x] 定义 `brain.workflow.run.snapshot`
- [x] 定义 `brain.workflow.run.keepalive`
- [x] 区分 domain event 和前端 snapshot
- [x] payload 改成“摘要对象”，不广播完整真源
- [x] 保留前端 camelCase 消费兼容

验收标准：

- workflow 状态变化有统一事件
- 前端实时页仍然正常
- snapshot 不再假装是 domain event

### Package N4：Internal Event Delivery 规范化

目标：

- 让 internal event delivery 进入统一事件协议体系

范围：

- `backend/app/services/workflow_service.py`
- `backend/app/services/internal_event_delivery_poller_service.py`
- 相关测试

任务：

- [x] 定义 `brain.internal_event.delivery.requested`
- [x] 定义 `brain.internal_event.delivery.claimed`
- [x] 定义 `brain.internal_event.delivery.completed`
- [x] 定义 `brain.internal_event.delivery.failed`
- [x] 定义 `brain.internal_event.delivery.retried`
- [x] 统一 `internal_event_id`
- [x] 统一 `idempotency_key`
- [x] 统一 `attempt_count`
- [x] 统一 `lease_until`
- [x] 统一 source / target

验收标准：

- internal event retry 链可完整追踪
- 投递失败、重试、完成状态都能标准化输出
- 和现有持久化 delivery 记录兼容

### Package N5：安全与边界收口

目标：

- 确保协议规范化不会把主脑真源广播出去

范围：

- `workflow_realtime_service`
- `agent_execution_worker_service`
- `workflow_service`
- 协议层 helper

任务：

- [x] 增加 payload 摘要化 helper
- [x] 增加敏感字段剥离 helper
- [x] 禁止完整 `task/run/step/manager_packet/memory/audit` 进入总线
- [x] 增加字段白名单测试
- [x] 增加事件大小控制测试

验收标准：

- 总线消息只包含调度和观测所需摘要
- 主脑真源仍只在本地持久层保存

## 六、字段规范

所有事件统一要求：

- `event_id`: 唯一事件 ID
- `event_name`: 事件名
- `event_version`: 当前固定 `v1`
- `message_type`: `command|event|result|snapshot`
- `subject`: 总线主题
- `aggregate.type`: 如 `workflow_run` / `agent_execution` / `internal_event_delivery`
- `aggregate.id`: 聚合 ID
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

## 七、测试清单

- [x] event protocol builder 测试
- [x] event protocol validator 测试
- [x] subject 常量覆盖测试
- [x] workflow run event 测试
- [x] agent execution event 测试
- [x] internal event delivery 测试
- [x] fallback to local bus 测试
- [x] idempotency key 稳定性测试
- [x] lease 字段测试
- [x] 敏感字段不出现在 payload 的测试

## 八、文档清单

- [x] 更新 `BRAIN_CORE_TODO.md`
- [x] 新增 `backend/docs/NATS_EVENT_PROTOCOL.md`
- [x] 说明“事件总线不是事实真源”
- [x] 说明“前端消费 snapshot，后端内部消费 event/command/result”

## 九、推荐开发顺序

最快最稳的顺序：

1. 先做 `Package N1`
2. 再做 `Package N2`
3. 然后做 `Package N3`
4. 最后做 `Package N4`
5. 收尾做 `Package N5`

原因：

- `N1` 是底座，必须先有
- `N2` 当前最接近标准协议，改造成本最低
- `N3` 牵涉前端兼容，放到第二阶段更稳
- `N4` 带 retry/lease，逻辑更重
- `N5` 做总线边界封口，避免安全倒退

## 十、当前定义的完成标准

当以下条件全部满足，才算“主脑内 NATS 事件协议规范化完成”：

- 所有内部 NATS 消息都通过统一 envelope 发出
- 所有 subject 都来自统一常量定义
- command / event / result / snapshot 已明确分层
- workflow / agent execution / internal delivery 三条链路全部接入
- 事件中不再广播主脑真源全量对象
- 后端全量测试通过
- 架构边界检查通过
