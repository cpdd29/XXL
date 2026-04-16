# Next Stage TODO

更新时间：2026-04-14
目标：在“接入层 + 安全网关 + 统一事件协议”已经到位的基础上，继续把主脑做成真正可运营、可观测、可回退、可并发编排的闭环系统。

原则：

- 大脑封闭：裁决权、真源、审计权必须保留在本地主脑
- 触手外置：Agent / Skill / MCP 只做执行，不做最终裁决
- 协议统一：所有调度、回传、观测都走正式协议
- 先主线后治理：先把主脑执行闭环做完整，再做 RBAC / 配置 / 成本 / SLA

当前状态：

- `Package E-L` 已完成并落地到代码与前端视图。
- 本文件转为“已完成阶段记录”，当前开发主线已切换到 `NEXT_STAGE_3_TODO.md` 的 `Package M`。

---

## Package E：主脑执行计划可视化

目标：

- 让主脑的“路由决定、执行计划、当前阶段、失败分支、回退路径”可视化
- 让前端和运维可以直接看清主脑为什么这么调度

范围：

- `backend/app/brain_core/routing/`
- `backend/app/brain_core/orchestration/`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/services/collaboration_service.py`
- `reception/app/collaboration/`
- `reception/app/workflow/`

任务：

- [x] 定义统一 `execution_plan` schema
- [x] 定义 `plan_step` / `plan_branch` / `plan_fallback` 结构
- [x] 在 run 真源中保存 plan snapshot
- [x] 在 task / collaboration session 中暴露 plan 摘要
- [x] 前端展示当前计划、当前执行节点、下一跳目标
- [x] 前端展示失败分支和 fallback path
- [x] 增加 plan 版本字段，避免后续 schema 演进冲突
- [x] 增加从路由决策到执行计划的追踪字段

验收标准：

- 用户或运维能看到“为什么走这个路由”
- 用户或运维能看到“下一步要调度哪个触手”
- 用户或运维能看到“失败后会退到哪里”
- 主脑 plan 来自本地真源，不依赖总线回放

当前已落地（2026-04-14）：

- `backend/app/brain_core/orchestration/service.py` 已统一产出 `execution_plan_snapshot`
- `backend/app/services/collaboration_service.py` 已对协作页暴露 `execution_plan / fallback / manager_packet`
- `reception/components/collaboration/execution-plan-visualizer.tsx` 已展示计划步骤、分支结果、winner、fallback 与 route rationale
- `reception/app/collaboration/page.tsx` 已接入执行计划可视化卡片
- 已复核 `backend/tests/test_collaboration.py` 与 `backend/tests/test_messages.py`：`48 passed`

---

## Package F：调度失败自动回退

目标：

- 任一触手失败后，由主脑自动决定重试、切换、降级或人工接管
- 不允许外接能力自己决定下一步

范围：

- `backend/app/brain_core/orchestration/`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/services/agent_execution_service.py`
- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/external_skill_registry_service.py`

任务：

- [x] 定义失败分类枚举
- [x] 定义 `fallback_policy` schema
- [x] 接入超时失败回退
- [x] 接入触手不可用回退
- [x] 接入协议错误回退
- [x] 接入结果不合格回退
- [x] 接入人工确认 / 人工接管回退
- [x] 为每次回退记录审计和状态原因
- [x] 为 run / task 增加 fallback history

验收标准：

- 触手离线时，主脑能自动切换或降级
- 执行超时时，主脑能自动重试或回退
- 返回结果不合格时，主脑能拒收并重新决策
- 所有回退都能被追溯

---

## Package G：多触手并发编排

目标：

- 主脑支持串行、并行、竞速、汇总式调度
- 多个外接触手可以协同完成一个任务，但最终结果仍由主脑收口

范围：

- `backend/app/brain_core/orchestration/`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/services/agent_execution_service.py`
- `backend/app/services/task_service.py`
- `backend/app/services/collaboration_service.py`

任务：

- [x] 定义并发编排模式：`serial / parallel / race / merge`
- [x] 定义 fan-out 调度协议
- [x] 定义 fan-in 结果汇总协议
- [x] 增加并发子任务状态聚合
- [x] 增加 winner 策略
- [x] 增加 quorum 策略
- [x] 增加 merge 汇总策略
- [x] 增加部分成功容错
- [x] 增加取消剩余触手的治理逻辑

验收标准：

- 一个任务可以同时调度多个触手
- 主脑可以选出 winner 或汇总多个结果
- 部分触手失败不会直接拖垮整任务
- 并发执行过程可观察、可审计、可回放

---

## Package H：外接能力版本管理

目标：

- Skill / Agent / MCP 的版本、兼容性、淘汰状态可被主脑正式治理
- 为后续多服务器部署、灰度切换、回滚做准备

范围：

- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/external_skill_registry_service.py`
- `backend/app/services/tool_catalog_adapters/`
- `backend/app/services/master_bot_service.py`

任务：

- [x] 注册协议增加 `version`
- [x] 注册协议增加 `compatibility`
- [x] 注册协议增加 `deprecated`
- [x] 注册协议增加 `release_channel`
- [x] 增加版本选择策略
- [x] 增加默认版本和回退版本
- [x] 增加不兼容版本拦截
- [x] 增加灰度版本标记
- [x] 增加版本审计日志

验收标准：

- 主脑能按版本约束选择外接能力
- 不兼容能力不会被错误调度
- 灰度版本可以被识别和控制
- 回滚版本可追溯

---

## Package I：主脑 RBAC 分层

目标：

- 把主脑“谁能看、谁能改、谁能放行、谁能操作外接触手”正式分层

范围：

- `backend/app/services/security_service.py`
- `backend/app/api/routes/`
- `reception/app/security/`
- `reception/app/settings/`

任务：

- [x] 定义主脑角色层级
- [x] 区分只读、调度、配置、安全、审计权限
- [x] 为关键操作增加权限校验
- [x] 为前端页面增加权限裁剪
- [x] 为敏感操作增加审计

验收标准：

- 非授权用户不能修改主脑关键配置
- 非授权用户不能放行安全策略
- 所有关键操作都有审计记录

---

## Package J：配置中心治理

目标：

- 主脑配置不再散落在各服务中，建立正式配置治理层

范围：

- `backend/app/config.py`
- `backend/app/services/`
- `reception/app/settings/`

任务：

- [x] 识别主脑关键配置项
- [x] 区分运行时配置与部署时配置
- [x] 建立配置读取优先级
- [x] 增加配置变更审计
- [x] 增加配置校验与风险提示

验收标准：

- 主脑关键配置有统一入口
- 改动可追溯
- 配置错误不会静默污染运行态

---

## Package K：调度成本统计

目标：

- 让主脑知道每次调度花了多少 token、多少时间、用了哪些触手

范围：

- `backend/app/services/workflow_execution_service.py`
- `backend/app/services/agent_execution_service.py`
- `backend/app/services/dashboard_service.py`

任务：

- [x] 为 run 统计 token 成本
- [x] 为 run 统计时间成本
- [x] 为触手统计调用次数
- [x] 为触手统计成功率
- [x] 在 dashboard 展示成本分布

验收标准：

- 每个 run 都能看到成本
- 每个外接能力都能看到使用量和成功率

---

## Package L：SLA 与运行指标

目标：

- 主脑具备正式运行指标，知道什么时候健康、什么时候异常

范围：

- `backend/app/services/dashboard_service.py`
- `backend/app/services/security_service.py`
- `backend/app/services/workflow_execution_service.py`

任务：

- [x] 定义核心 SLA 指标
- [x] 定义成功率、超时率、失败率、回退率
- [x] 定义健康阈值
- [x] 增加 dashboard 指标展示
- [x] 增加异常告警准备字段

验收标准：

- 主脑可以量化当前运行状态
- 异常时能快速定位是哪个链路出问题

---

## 本清单状态

本文件对应阶段已完成：

1. `Package E` 主脑执行计划可视化
2. `Package F` 调度失败自动回退
3. `Package G` 多触手并发编排
4. `Package H` 外接能力版本管理
5. `Package I` 主脑 RBAC 分层
6. `Package J` 配置中心治理
7. `Package K` 调度成本统计
8. `Package L` SLA 与运行指标

后续开发请以 `NEXT_STAGE_3_TODO.md` 为主，不再按本文件继续排新任务。

---

## 当前建议

下一步最建议继续 `NEXT_STAGE_3_TODO.md` 中的 `Package M`。

原因：

- 当前“可视化 / 回退 / 并发 / 版本 / RBAC / 配置 / 成本 / SLA”这一阶段已经完成
- 现在最关键的是把 `message_ingestion_service.py / workflow_execution_service.py / task_view` 继续收口到主脑正式代码层
- 只有先把主链彻底收干净，后面的控制面、容灾、长期维护才会稳定
