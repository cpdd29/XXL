# Package M 边界清单

更新时间：2026-04-15

## 结论

`Package M` 完成后，代码层要分成 3 类：

1. 正式主链：长期保留，后续继续扩展。
2. 冻结兼容边界：暂时保留，只为兼容旧调用/旧命名，后续应删除。
3. 保留型外壳：不是主脑核心，但属于稳定 facade，不是当前删除目标。

核心原则：

- 主脑正式主链只认 `brain_core -> execution_gateway -> tentacle_adapters`
- 旧 `direct_agent_*`、`master_bot_*` 只允许留在兼容边界
- 新功能不允许再挂到冻结兼容边界上

## 一、正式主链：长期保留

这些模块属于后续继续演进的正式结构，不应删除。

### 1. 主脑核心

- `backend/app/brain_core/coordinator/`
  统一消息进入主脑后的总入口。
- `backend/app/brain_core/reception/`
  接待、延续任务判断、确认/续写计划生成。
- `backend/app/brain_core/routing/`
  路由决策、路由理由、fallback policy、执行计划主名。
- `backend/app/brain_core/manager/`
  项目经理 Agent 的 manager packet / dispatch summary 真源。
- `backend/app/brain_core/orchestration/`
  任务装配、dispatch context、state machine、follow-up plan、run launch plan。
- `backend/app/brain_core/task_view/`
  `route_decision / execution_plan / task_view` 的统一产出层。

### 2. 正式执行链

- `backend/app/execution_gateway/`
  正式唯一执行网关。
- `backend/app/services/workflow_execution_service.py`
  workflow run 真源、推进核心、fallback/恢复、执行时状态流转。

### 3. 正式消息入口

- `backend/app/services/message_ingestion_service.py`
  本地消息入口编排层。保留，但职责应稳定在“入口接入、真源写入、触发执行”。
- `backend/app/api/routes/messages.py`
- `backend/app/api/routes/webhooks.py`
- `backend/app/services/dingtalk_stream_service.py`

### 4. 正式消费层

- `backend/app/services/dashboard_service.py`
- `backend/app/services/collaboration_service.py`

说明：

这些服务现在已经主要消费 `brain_core/task_view`，属于稳定消费层，不是兼容废层。

## 二、冻结兼容边界：后续应删除

这些对象现在可以保留，但定位已经变成 compatibility-only。
等没有存量依赖后，应删除。

### A. 兼容服务壳

- `backend/app/services/master_bot_service.py`
  状态：已冻结为兼容 facade。
  当前作用：兼容旧入口调用 `route_message(...)` 和 `list_external_capabilities(...)`。
  后续目标：整个文件删除。
  当前保护：`check_architecture_boundaries.py` 已阻止 `app/` 代码重新依赖它。

### B. workflow_execution 旧命名 wrapper

- `backend/app/services/workflow_execution_service.py`
  后续应删除的兼容项：
  - `resolve_direct_execution_agent(...)`
  - `_is_direct_agent_run(...)`
  - `create_direct_agent_run_for_task(...)`
  - `DIRECT_AGENT_FALLBACK_WORKFLOW_ID`
  - `DIRECT_AGENT_FALLBACK_WORKFLOW_NAME`

说明：

- 这些对象现在只是旧命名兼容入口。
- 正式主名已经是 `agent_dispatch`。

### C. 主脑内旧命名别名

- `backend/app/brain_core/coordinator/service.py`
  - `BrainDispatchPlan.direct_agent_dispatch`
- `backend/app/brain_core/orchestration/service.py`
  - `create_task_steps(..., direct_agent_dispatch=...)`

说明：

- 这类别名只为兼容旧调用点。
- 后续所有调用点都迁完后可以删。

### D. 旧 routing strategy 兼容值

- `backend/app/brain_core/routing/service.py`
  - `chat_direct_agent`
  - `workflow_or_direct_agent_fallback`

说明：

- 这两个值现在只作为旧协议/旧数据兼容值存在。
- 主脑内部已经归一到 `agent_dispatch` 语义。

### E. 旧摘要/响应兼容字段

- `brain_dispatch_summary.dispatch_type`
  主字段已经是 `dispatch_mode`，`dispatch_type` 后续可删。

说明：

- 这类字段删除前，必须先确认前端、报表、审计消费端都已切到新字段。

## 三、保留型外壳：不是当前删除目标

这些不是主脑核心，但属于稳定 facade，不应和冻结兼容边界混为一谈。

- `backend/app/services/task_service.py`
  角色：task API 的查询/变更壳。
  当前保留原因：仍负责 task/run/steps 读模型装载，以及 `retry/cancel` 操作。
  结论：保留，不作为 Package M 删除项。

- `backend/app/services/collaboration_service.py`
  角色：协作页 session/node/log 汇总 facade。
  结论：保留。

- `backend/app/services/dashboard_service.py`
  角色：Dashboard 聚合 facade。
  结论：保留。

## 四、删除前必须满足的条件

冻结兼容边界不是“想删就删”，必须满足以下条件：

1. 代码内无调用
- `rg` 扫描无业务调用点
- 只剩定义本身或测试中的历史兼容测试

2. 外部接口无依赖
- 前端不再读旧字段
- 外部调用方不再依赖旧函数/旧路由行为

3. 持久化/事件协议无依赖
- 历史 run/task 数据中的旧值已不再被读取
- 事件协议消费方已完成迁移

4. 替代主链已稳定
- 新主链至少经历一轮完整回归
- 灰度/回滚验证通过

5. 删除后 CI 通过
- 架构边界检查通过
- 邻近测试通过
- 对外 API smoke test 通过

## 五、推荐删除顺序

建议按风险从低到高删除：

1. `master_bot_service.py`
- 因为它现在几乎没有真实业务调用，而且已被架构守卫拦住继续扩散。

2. `brain_core` 内旧别名
- `direct_agent_dispatch` property / 参数别名。

3. `workflow_execution_service.py` 旧 wrapper
- `resolve_direct_execution_agent(...)`
- `_is_direct_agent_run(...)`
- `create_direct_agent_run_for_task(...)`
- `DIRECT_AGENT_FALLBACK_*`

4. 旧 routing strategy 兼容值与旧摘要字段
- `workflow_or_direct_agent_fallback`
- `chat_direct_agent`
- `dispatch_type`

## 六、当前执行建议

现阶段不建议立即删除冻结兼容边界，建议先维持：

- 主链继续只走正式结构
- 架构检查继续阻止新增旧依赖
- 后续把删除动作放入 `Package P：架构守卫与技术债清理`

一句话判断：

- 正式主链：继续保留并扩展
- 冻结兼容边界：先封存，后删除
- 保留型外壳：不是这轮删除目标
