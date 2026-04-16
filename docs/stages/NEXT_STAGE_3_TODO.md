# Next Stage 3 TODO

更新时间：2026-04-15（已同步 Package M 最新进度）  
目标：在“主脑功能闭环、外接触手治理、协作可视化、灰度回滚、容灾预案”已经到位的基础上，继续把代码层真正收口，补齐控制面与演练自动化，进入可长期维护状态。

原则：

- 主脑封闭：裁决、真源、审计、安全策略继续保留在本地主脑
- 触手外置：执行能力继续独立部署，不回流主脑
- 协议统一：统一从 `brain_core -> execution_gateway -> tentacle_adapters`
- 先收口后扩展：先解决代码层混杂，再做更多高级能力

承接说明：

- `docs/archive/completed-stages/NEXT_STAGE_TODO.md` 中的 `Package E-L` 已完成，本文件是当前正式主开发清单。
- 当前优先级最高的是 `Package M`，不是继续横向扩展新能力。

---

## Package M：主脑主链收口

目标：

- 把主脑从“功能已具备”推进到“主链清晰、边界稳定、兼容层变薄”
- 让 `brain_core` 成为真正唯一的主脑内核

范围：

- `backend/app/brain_core/`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/master_bot_service.py`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/execution_gateway/`
- `backend/scripts/check_architecture_boundaries.py`

任务：

- [x] 建立统一 `brain_core/coordinator` 入口
- [x] 所有消息入口统一先走 coordinator
- [x] 继续迁空 `message_ingestion_service.py`
- [x] 继续迁空 `master_bot_service.py`
- [x] 统一 `route_decision / execution_plan / task_view` 产出路径
- [x] 清理兼容层直接分发或直接执行残留
- [x] 固化唯一执行路径 `brain_core -> execution_gateway -> tentacle_adapters`
- [x] 增加架构边界检查与回归测试

当前已完成：

- `brain_core` 内部已清掉对 `master_bot_service` 的直接依赖，兼容层目前只保留在 `backend/app/services/master_bot_service.py`
- `message_ingestion_service.py` 的主消息分发已统一经由 coordinator，任务意图补推断已收回 `brain_core/reception`
- 自由工作流执行分流已统一经由 `execution_gateway/skill_execution_gateway.py`
- 专业工作流 runtime 执行入口已统一经由 `execution_gateway/skill_execution_gateway.py`
- `message_ingestion_service.py` 中的消息返回投影已统一改由 `brain_core/task_view/service.py` 产出
- `message_ingestion_service.py` 中的新任务聚合根装配与 state_machine 拼装已收回 `brain_core/orchestration/service.py`
- `message_ingestion_service.py` 中的 active task 解析、context patch 计划生成、professional confirmation transition 已开始收回 `brain_core/reception/service.py`
- `message_ingestion_service.py` 中的 `manager_packet / brain_dispatch_summary` 状态刷新已收回 `brain_core/manager/service.py`
- `message_ingestion_service.py` 中的 professional confirmation 应用补丁、context patch 任务投影应用补丁已开始收回 `brain_core/orchestration/service.py`
- `brain_core/coordinator` 与 `brain_core/orchestration` 内部已开始以 `agent_dispatch` 作为中性主名承接原 `direct_agent_dispatch` 语义，并保留旧别名兼容
- `message_ingestion_service.py` 中的新任务返回、professional confirmation、context patch 返回投影已进一步统一到 `brain_core/task_view/service.py` 的 task-event response helper
- `task_service.py` 中的任务读模型聚合、治理字段回填、dispatch_context 回填、失败归因与 `status_reason` 产出已统一改由 `brain_core/task_view/service.py` 负责，`task_service.py` 已收缩为 attach_scope + run/steps 装载的兼容薄包装
- `dashboard_service.py` 与 `collaboration_service.py` 已改为直接调用 `brain_core/task_view/service.py`，任务视图消费面不再依赖 `task_service.py` 的旧聚合逻辑
- `workflow_execution_service.py` 已开始把 `direct_agent_fallback` 运行语义中性化为 `agent_dispatch` 兼容概念，新增 `resolve_agent_dispatch_execution_agent` / `_is_agent_dispatch_run`，并保留旧命名兼容 wrapper
- `brain_core/routing/service.py` 已开始把 `fallbackPolicy.mode` 主名切到 `agent_dispatch_fallback`，同时执行层继续兼容旧值 `direct_agent_fallback`
- `brain_core/routing/planner.py` 与 `brain_core/routing/service.py` 已优先改用 `resolve_agent_dispatch_execution_agent` 与 `AGENT_DISPATCH_*` 常量，逐步脱离旧兼容命名
- `message_ingestion_service.py` 中 professional confirmation / context patch 的后续副作用判断，已进一步改由 `brain_core/orchestration/service.py` 输出 follow-up plan，入口层改为统一执行 plan
- `message_ingestion_service.py` 中 context patch 的“task 有/无”返回分支已统一收口到 `brain_core/task_view/service.py` 的 `build_context_patch_response(...)`
- `brain_core/routing/service.py` 内部已把旧 `direct_agent` routing strategy 映射为 `agent_dispatch` 主名参与内部推导，同时继续保留旧策略值对外兼容
- `brain_core/coordinator/service.py` 的 `brain_dispatch_summary` 已新增 `dispatch_mode` 主字段，并保留 `dispatch_type` 兼容别名
- `task_service.py` 中 `list/get` 的 scoped projection 与列表响应包装已进一步下沉到 `brain_core/task_view/service.py`，`task_service.py` 继续收缩为读取 task/run/steps + scope 过滤 + retry/cancel 的兼容查询壳
- `collaboration_service.py` 中 session `execution_plan` / `fallback_history` 的视图拼装已进一步收口到 `brain_core/task_view/service.py`，协作层不再手工拼装该类任务视图
- `message_ingestion_service.py` 中新任务创建链的 dispatch metadata、task/task_steps 装配与 run launch plan 已进一步收回 `brain_core/orchestration/service.py`，入口层改为消费 bundle/plan 并执行真源写入与启动
- `master_bot_service.py` 已冻结为兼容壳，并新增架构守卫，防止任何 `app/` 代码重新导入该兼容层承载业务逻辑
- `workflow_execution_service.py` 中 `dispatch / execute / tick` 三套主链入口已统一收口到单一推进核心
- `workflow_execution_service.py` 中直接 `execute_task` 的失败处理与结果校验已统一收口到单一 helper，消息入口已改走更中性的 `create_agent_dispatch_run_for_task`
- `workflow_execution_service.py` 已进一步用 `AGENT_DISPATCH_FALLBACK_POLICY_MODES` / `AUTO_RECOVERY_FALLBACK_MODES` 收口 fallback 内部判断，并继续清理 service 内部可安全替换的 `direct_agent_*` 术语
- `workflow_execution_service.py` 已新增 dispatch type / fallback mode 内部归一化 helper，旧 `direct_agent_*` 入口与常量仅保留在兼容 wrapper / 别名边界
- 已新增 execution gateway 单测，并补强架构边界检查，防止 `brain_core` 重新依赖 `master_bot_service`
- 本轮关键回归：
  - `pytest -q backend/tests/test_brain_core.py backend/tests/test_messages.py` -> `88 passed`
  - `pytest -q backend/tests/test_agents_runtime.py backend/tests/test_workflows.py` -> `53 passed`
  - `pytest -q backend/tests/test_brain_core.py backend/tests/test_tasks.py backend/tests/test_collaboration.py` -> `72 passed`
  - `pytest -q backend/tests/test_messages.py backend/tests/test_workflows.py` -> `85 passed`
  - `pytest -q backend/tests/test_collaboration.py` -> `10 passed`
  - `pytest -q backend/tests/test_architecture_boundaries.py` -> `18 passed`
  - `pytest -q backend/tests/test_brain_core.py backend/tests/test_messages.py backend/tests/test_architecture_boundaries.py` -> `114 passed`
  - `pytest -q backend/tests/test_tasks.py backend/tests/test_collaboration.py backend/tests/test_agents_runtime.py backend/tests/test_workflows.py` -> `74 passed`
  - `python3 backend/scripts/check_architecture_boundaries.py` -> `OK`

Package M 收尾说明：

- `master_bot_service.py`、`resolve_direct_execution_agent(...)`、`create_direct_agent_run_for_task(...)`、`DIRECT_AGENT_FALLBACK_*` 与旧 `routing_strategy` 值仍保留，但已明确降级为冻结兼容边界，不再承载 Package M 的真实业务主链
- `task_service.py` 仍保留 task/run/steps 读模型装载与 retry/cancel 变更壳，这是有意保留的查询/操作兼容层，不再作为 Package M 未完成项
- 后续若继续清旧名，将归入 `Package P：架构守卫与技术债清理`，不阻塞 Package M 验收

验收标准：

- 主链只有一条正式路径
- `message_ingestion_service.py` 只保留入口编排与真源写入
- `master_bot_service.py` 不再承载真实业务裁决
- `brain_core` 不再直接触碰具体触手实现

---

## Package N：外接能力控制面前端

目标：

- 把外接 Agent / Skill 的版本治理、灰度、回滚能力从 API 提升到可操作控制面
- 让运维不需要手工调接口就能治理外接能力

范围：

- `reception/app/`
- `reception/components/`
- `reception/hooks/`
- `reception/types/`
- `backend/app/api/routes/external_connections.py`

任务：

- [x] 增加外接 Agent 版本治理页面
- [x] 增加外接 Skill 版本治理页面
- [x] 展示 `version / release_channel / fallback / rollout_policy / rollback_policy`
- [x] 展示 `health / routable / circuit_state / deprecated`
- [x] 接入 `promote / set-fallback / deprecate / rollout / rollback` 操作
- [x] 展示相关审计记录与最近治理动作
- [x] 对非授权角色做只读裁剪与禁用

当前已完成：

- 新增 `GET /api/external-connections/governance`，返回 family 级治理摘要与最近外接能力审计
- 设置区已新增“外接能力治理”正式页面，按 `Agent / Skill` 双视图展示版本治理状态
- 页面已展示 `current version / release_channel / fallback / rollout_policy / rollback_policy`
- 页面已展示 `status / routable / circuit_state / deprecated / last_heartbeat_at`
- 版本详情抽屉已接通 `promote / set-fallback / deprecate / rollout / rollback`
- 页面已展示最近治理动作与 family 相关审计记录
- 非 `external:write` 角色已自动降级为只读视图，治理控件禁用

验收标准：

- 运维可在 UI 上完成切主、灰度、回滚
- UI 状态与后端 registry 真源一致
- 所有控制面动作都有审计记录

---

## Package O：容灾演练自动化

目标：

- 把容灾从“有文档”推进到“可演练、可脚本执行、可记录结果”
- 为主脑/触手跨机房切换建立标准操作面

范围：

- `docs/brain/BRAIN_DR_RUNBOOK.md`
- `backend/scripts/`
- `backend/app/services/`
- `docker-compose.yml`
- 运维脚本目录

任务：

- [x] 新增 `dr_precheck` 脚本
- [x] 新增 `failover_prepare` 脚本
- [x] 新增 `post_failover_verify` 脚本
- [x] 新增外接触手重注册与恢复检查脚本
- [x] 固化主脑切换后的 `task/run/audit/security` 真源校验
- [x] 固化演练结果模板，记录 RTO / RPO / 失败步骤
- [x] 把 runbook 中的人工步骤映射为脚本步骤或检查项

验收标准：

- 容灾演练有标准脚本入口
- 切换后可自动校验关键真源连续性
- 演练结果可沉淀为记录，不靠手工散记

当前状态：

- 已新增 `backend/scripts/dr_precheck.py`
- 已新增 `backend/scripts/failover_prepare.py`
- 已新增 `backend/scripts/post_failover_verify.py`
- 已新增 `backend/scripts/external_tentacle_recovery.py`
- 已新增 `backend/docs/dr_drill_result_template.md`
- `docs/brain/BRAIN_DR_RUNBOOK.md` 已补齐脚本化映射与检查项
- 已新增 `backend/tests/test_dr_scripts.py`

---

## Package P：架构守卫与技术债清理

目标：

- 防止后续开发把旧结构写回去
- 把当前已完成的大量能力从“能用”提升到“可持续演进”

范围：

- `backend/scripts/`
- `backend/tests/`
- `reception/tests/` 或前端校验链
- `AGENTS.md`
- TODO 文档同步逻辑

任务：

- [x] 禁止 `brain_core` 直接 import 具体执行实现
- [x] 禁止新增主脑内置重执行 `*_skill`
- [x] 增加 TODO 文档同步检查
- [x] 增加灰度/回滚 smoke test
- [x] 增加协作页执行计划可视化 smoke test
- [x] 清理重复 DTO、兼容层重复字段和无效包装函数
- [x] 归档已完成阶段文档，避免主清单继续漂移

验收标准：

- CI 能阻止架构边界被破坏
- 新增功能默认落在正确层次
- 文档与代码状态保持同步

当前状态：

- `brain_core/routing/service.py` 与 `brain_core/routing/planner.py` 已通过 `execution_directory_service.py` 间接访问执行目录，主脑不再直接 import `workflow_execution_service`
- `backend/scripts/check_architecture_boundaries.py` 已新增对 `brain_core -> workflow_execution_service` 的禁入守卫，并补齐回归测试
- `backend/scripts/check_todo_sync.py` 已落地，默认检查 `docs/stages/NEXT_STAGE_3_TODO.md` 与 `docs/archive/completed-stages/` 下的完成态文档引用和状态块
- 已新增 `backend/tests/test_package_p_smoke.py`，覆盖外接灰度/回滚治理 smoke 与协作页执行计划可视化 smoke
- 已新增 `backend/app/core/brain_payload_fields.py`，统一 `route_decision / execution_plan / dispatch_context` 的 snake/camel 兼容字段读取
- `workflow_execution_service.py` 内部无效包装 `_resolve_workflow_execution_agent_compat` / `_is_direct_agent_run` 已清理
- `reception/types/external-connection.ts` 已收敛重复治理 DTO，统一 `rollout / rollback policy` 类型定义
- `AGENTS.md` 已补充 Package P 的守卫命令与边界要求
- 已完成历史阶段文档归档：`docs/archive/completed-stages/`

---

## 推荐开发顺序

1. `Package M` 主脑主链收口
2. `Package N` 外接能力控制面前端
3. `Package O` 容灾演练自动化
4. `Package P` 架构守卫与技术债清理

---

## 当前建议

下一步最建议开始 `Package N` 或 `Package P`。

原因：

- `Package M` 已达到当前阶段的验收目标，主脑主链、兼容边界与执行路径已稳定
- 继续做剩余旧名清理属于技术债治理，不再阻塞主线进入控制面与守卫建设
- 更高收益的下一步是把外接能力控制面补齐，或把架构守卫做成更强的 CI 约束
