# Next Stage 4 TODO

更新时间：2026-04-15  
目标：在 `docs/stages/NEXT_STAGE_3_TODO.md` 已收口后，继续把 Dispatcher / Worker / NATS 主链推进到“持久化队列协议明确、重试与死信可治理、运行态可观测”的正式底座。

原则：

- 主脑闭环：`task / run / audit / security` 仍以本地主脑真源为准
- 触手外置：外接能力只执行，不接管调度裁决
- 队列正规化：job 持久化层必须保存协议快照，不能只靠内存态 `dispatch_context.protocol`
- 多实例优先：所有 claim / lease / retry / dead-letter 设计都要兼容多实例

---

## Package Q：持久化队列协议快照

目标：

- 把 `workflow_dispatch_jobs / workflow_execution_jobs / agent_execution_jobs` 从“只有时间和 owner”的轻队列表，推进成“携带 protocol snapshot 的正式控制面队列”
- 让 worker 重试、死信、排障不再只依赖 run 内存态

范围：

- `backend/app/db/models.py`
- `backend/alembic/versions/20260415_0015_job_protocol_snapshots.py`
- `backend/app/services/persistence_service.py`
- `backend/app/services/workflow_dispatcher_service.py`
- `backend/app/services/workflow_execution_worker_service.py`
- `backend/tests/test_persistence.py`
- `backend/tests/test_workflow_dispatcher.py`
- `backend/tests/test_workflow_execution_worker.py`

任务：

- [x] 为三类 job 表增加 `protocol` 快照列
- [x] 持久化层返回 `protocol + flatten` 双兼容 payload
- [x] dispatcher 派发 execution command 时保留 run 上次 retry attempt
- [x] workflow execution worker 补齐 `claimed / started / completed / failed` 标准事件
- [x] workflow execution worker 补齐 retry / dead-letter 语义
- [x] 补齐回归测试

当前状态：

- 已新增 `backend/alembic/versions/20260415_0015_job_protocol_snapshots.py`
- 已为 `backend/app/db/models.py` 中三类 job record 增加 `protocol` 字段
- `backend/app/services/persistence_service.py` 已持久化并回传 protocol snapshot
- `backend/app/services/workflow_dispatcher_service.py` 已在 execution retry 场景保留 attempt，不再被 dispatch failure count 覆盖回 1
- `backend/app/services/workflow_execution_worker_service.py` 已补齐 claimed / started / completed / dead-letter 事件与 retry attempt 递增
- 已补齐 `backend/tests/test_persistence.py`、`backend/tests/test_workflow_dispatcher.py`、`backend/tests/test_workflow_execution_worker.py` 的回归覆盖

验收标准：

- execution / agent / dispatch job 都能在数据库里保留协议快照
- workflow execution retry 不会把 `attempt` 重置回 1
- worker 失败达到上限后能进入 dead-letter，并写回 run protocol

---

## Package R：调度运行时控制面

目标：

- 把 dispatcher / poller / execution worker / agent worker 的运行态做成可读控制面

任务：

- [x] 增加 dispatcher / worker runtime snapshot service
- [x] 暴露 queue depth / active lease / claimed stale / dead-letter 统计
- [x] 暴露最近 retry / dead-letter / reclaim 告警
- [x] 接入 workflow monitor 与 dashboard

当前状态：

- 已新增 `backend/app/services/workflow_runtime_snapshot_service.py`，统一聚合 dispatch / workflow execution / agent execution 三类队列运行态
- 已新增 `backend/app/schemas/runtime.py`，并接入 `backend/app/schemas/workflows.py` 与 `backend/app/schemas/dashboard.py`
- `backend/app/services/persistence_service.py` 已补齐三类 job 的列表读取能力，供 runtime control plane 聚合使用
- `backend/app/services/workflow_service.py` 已把 runtime snapshot 接入 workflow monitor
- `backend/app/services/dashboard_service.py` 已把 runtime snapshot 接入 dashboard，并把 runtime recent alerts 合并进 prepared alerts
- `reception/app/dashboard/page.tsx` 与 `reception/components/workflow/workflow-inspector.tsx` 已展示队列深度、lease、stale claim、retry / dead-letter 告警
- 已补齐 `backend/tests/test_workflow_runtime_snapshot.py` 回归覆盖，且相关 `dashboard / workflow monitor / database priority` 回归已通过

验收标准：

- workflow monitor 能展示三类队列的 runtime snapshot 与 recent alerts
- dashboard 能展示 queue depth / active lease / stale claim / dead-letter / retry 摘要
- runtime recent alerts 能覆盖 retry / dead-letter / reclaim 三类运行态风险

---

## Package S：多实例调度守卫

目标：

- 继续收紧多实例下的 lease 回收、stale claim 修复、重复消费防护

任务：

- [x] 增加 stale lease reclaim 的自动审计
- [x] 增加 execution job claim repair 与 orphan job 巡检
- [x] 增加 dispatcher / worker 启动自检脚本
- [x] 增加多实例 smoke test

当前状态：

- 已新增 `backend/app/services/scheduler_guard_service.py`，统一处理 dispatch / workflow execution / agent execution 三类队列的 stale lease reclaim、orphan job 清理、missing execution job repair，并补齐控制面审计与运行日志
- `backend/app/services/workflow_dispatch_poller_service.py`、`backend/app/services/workflow_execution_worker_service.py`、`backend/app/services/agent_execution_worker_service.py` 已接入守卫巡检，轮询前会先做 lease reclaim 与队列修复
- 已新增 `backend/scripts/check_scheduler_startup.py`，可输出 dispatcher / worker / guard / lease window / 多实例模式的启动自检结果，并支持 `--strict`
- 已补齐 `backend/tests/test_scheduler_guard_service.py`、`backend/tests/test_scheduler_startup.py`、`backend/tests/test_package_s_smoke.py`，覆盖 reclaim 审计、execution repair、orphan 巡检、启动自检、多实例共享 SQLite smoke

验收标准：

- stale dispatch claim、workflow execution claim、agent execution claim 在 lease 过期后都能被守卫自动回收，并写入 audit / realtime log
- `dispatched` 与 `agent_queued` 运行态在 execution job 丢失时，守卫能够自动补建持久化 job
- dispatcher / worker 启动自检脚本可在当前仓库输出绿色结果，并明确标注 `fallback` 与 `strict multi-instance` 的边界
- 多实例 smoke 能证明共享真源下的 claim 排他、stale reclaim、repair 后再 claim 这一整条链路成立
