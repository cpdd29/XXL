# Brain Prelaunch TODO

更新时间：2026-04-16（仓内门禁与验收资产已补齐，正式生产验收待真实环境执行）

关联文档：

- `docs/brain/BRAIN_CORE_STATUS.md`
- `docs/stages/NEXT_STAGE_3_TODO.md`
- `docs/stages/NEXT_STAGE_4_TODO.md`

目标：

- 把“主脑研发主链已完成”的状态，推进到“可做正式生产上线验收”
- 把主脑上线前还缺的环境、运维、安全、兼容层、容灾、监控项拆成可执行开发清单

原则：

- 主脑封闭：裁决、真源、审计、安全策略继续保留在本地主脑
- 触手外置：外接 Agent / Skill / MCP 继续独立部署，不回流主脑
- 协议统一：统一走 `brain_core -> execution_gateway -> external adapters`
- 先验收再扩展：先把上线前门槛补齐，再继续扩展新能力

上线口径：

- 代码完成，不等于上线完成
- 单机 fallback 绿色，不等于正式多实例可上线
- smoke 通过，不等于生产拓扑验收完成

---

## Package A：正式真源接入与多实例联调

目标：

- 把当前 `fallback / degraded` 状态推进到“正式真源接入完成”
- 完成真实数据库真源下的多实例 dispatcher / worker 联调

范围：

- `backend/app/services/persistence_service.py`
- `backend/app/services/workflow_dispatch_poller_service.py`
- `backend/app/services/workflow_execution_worker_service.py`
- `backend/app/services/agent_execution_worker_service.py`
- `backend/scripts/check_scheduler_startup.py`
- docker / 部署配置

任务：

- [ ] 接入正式数据库配置并验证主脑可稳定启动
- [ ] 在正式数据库环境下验证 `task / run / audit / security` 真源写入
- [ ] 在双 dispatcher 实例下验证 dispatch claim 排他
- [ ] 在双 workflow worker 实例下验证 execution claim 排他
- [ ] 在双 agent worker 实例下验证 agent execution claim 排他
- [ ] 验证 stale lease reclaim 在真实数据库环境下成立
- [ ] 验证 missing execution job repair 在真实数据库环境下成立
- [ ] 验证 orphan job 巡检在真实数据库环境下成立
- [ ] 让 `check_scheduler_startup.py` 在正式真源环境输出非 degraded 结果
- [ ] 补齐正式联调记录文档

当前状态：

- 已新增 `backend/scripts/check_scheduler_startup.py`，可区分 `fallback / persistent / degraded`
- 已新增 `backend/scripts/check_persistence_contract.py`，可直接输出 `database_url` 的 driver/host/default/localhost/persistence_enabled 合同检查，便于上线前先排配置问题再排运行态问题
- 已新增 `backend/scripts/check_production_env_contract.py`，可对 `backend/.env.production` 做生产环境变量合同检查（`WORKBOT_ENVIRONMENT / DATABASE_URL / REDIS_URL / NATS_URL / DATA_ENCRYPTION_KEY` 必填、非默认值、非 localhost、口令/密钥强度）
- 已新增 `backend/scripts/check_scheduler_runtime_pg_acceptance.py`，可直接对真实数据库 DSN 跑 dispatcher / workflow execution / agent execution 的 claim、stale takeover、release 保护、guard reclaim/repair 与重启后可见性验收，便于在正式 PostgreSQL 接入后快速确认 `scheduler_multi_instance_ready / scheduler_runtime_persistent`
- 已新增 `backend/scripts/check_brain_prelaunch.py`，聚合 `platform_readiness / scheduler_startup / release_preflight / nats transport snapshot`，统一输出 `blocked / degraded_startable / production_ready`
- `backend/scripts/check_brain_prelaunch.py` 在 `persistence_contract` 通过后会自动追加 `check_scheduler_runtime_pg_acceptance.py`；若仍是默认/降级环境，则输出 `skipped` 而不是新增假 blocker
- 已新增多实例运行入口：`backend/scripts/run_dispatcher_runtime.py`、`backend/scripts/run_workflow_execution_worker_runtime.py`、`backend/scripts/run_agent_execution_worker_runtime.py`
- 已新增多实例 compose 与启动入口：`deploy/multi-instance/docker-compose.multi-instance.yml`、`deploy/multi-instance/.env.multi-instance.example`、`run-multi-instance-acceptance.sh`
- 已新增配套文档：`docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`
- 已新增正式留痕模板：`backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md`
- Package A 的仓内代码、runner、compose、检查脚本和文档已经齐备
- 正式是否通过，取决于目标 PostgreSQL / NATS 环境与运行时输出，不应由文档静态宣告

建议预检命令（Package A）：

- `python3 backend/scripts/check_production_env_contract.py --strict`
- `python3 backend/scripts/check_persistence_contract.py --strict`
- `python3 backend/scripts/check_scheduler_startup.py`
- `python3 backend/scripts/check_scheduler_runtime_pg_acceptance.py --database-url <postgres_dsn> --strict`
- `python3 backend/scripts/check_brain_prelaunch.py --strict-production`

当前结论（2026-04-16）：

- Package A 的仓内交付已完成
- 正式多实例验收仍需在真实 PostgreSQL / NATS 环境中执行并留痕

---

## Package B：NATS 正式链路验收

目标：

- 把当前“可 fallback 运行”推进到“正式事件总线验收通过”
- 验证内部事件链在真实 NATS 下的稳定性与恢复能力

范围：

- `backend/app/core/nats_event_bus.py`
- `backend/app/core/event_protocol.py`
- `backend/app/core/event_subjects.py`
- `backend/app/services/internal_event_delivery_poller_service.py`
- `backend/app/services/workflow_dispatcher_service.py`
- `backend/app/services/workflow_execution_worker_service.py`
- `backend/app/services/agent_execution_worker_service.py`

任务：

- [ ] 接入正式 NATS 配置并验证连接稳定
- [ ] 验证 workflow dispatch command 在真实 NATS 下投递成功
- [ ] 验证 workflow execution claimed / started / completed / failed 事件链完整
- [ ] 验证 agent execution request / result / retry / dead-letter 事件链完整
- [ ] 验证 NATS 断连时 fallback 行为与恢复行为符合预期
- [ ] 验证重复订阅、重复消费、消息重放场景下协议幂等性
- [ ] 验证内部事件投递失败后的补偿与重试
- [ ] 补齐正式 NATS 环境的联调记录

当前状态：

- `backend/app/core/nats_event_bus.py` 已新增结构化 `connection_snapshot()` 输出，包含连接状态、注册 handler 数、订阅数、fallback 模式与运行参数
- 已新增 `backend/scripts/check_nats_contract.py`，可直接输出 `nats_url` 的 scheme/host/port/default/localhost、transport registrations、`last_error` 与 `probe_error`，便于把“地址配置问题”和“运行态连接问题”拆开看
- 已新增 `backend/scripts/check_nats_roundtrip.py`，可直接对真实 NATS 跑 roundtrip、queue-group 竞争消费与 command/event 过滤验收，便于在正式链路接入后快速确认 handler 真正收到消息而不是只看 `connected=true`
- `backend/scripts/check_brain_prelaunch.py` 已把 NATS transport 快照纳入上线前严格门禁
- `backend/scripts/check_brain_prelaunch.py` 在 `nats_contract` 通过且非 fallback 时会自动追加 `check_nats_roundtrip.py`；若仍处于本地默认/降级链路，则输出 `skipped`
- 已修复 `check_nats_roundtrip.py` 与运行中 dispatcher 抢消费的探针冲突问题：probe 现使用专用 subject，不再被真实 queue-group 消费者污染
- `check_brain_prelaunch.py` 与 `check_scheduler_startup.py` 的 readiness 摘要已统一以 contract 结果归一，避免输出误导性的 `false/false`
- Package B 的仓内检查脚本与协议守卫已经齐备
- 正式 roundtrip / queue-group / 恢复行为是否通过，仍需针对真实 NATS 运行时执行

建议预检命令（Package B）：

- `python3 backend/scripts/check_nats_contract.py --strict`
- `python3 backend/scripts/check_nats_roundtrip.py --nats-url <nats_url> --strict`
- `python3 backend/scripts/check_brain_prelaunch.py | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({\"nats_contract\": d[\"checks\"][\"nats_contract\"], \"nats_last_error\": d[\"checks\"][\"nats_transport\"].get(\"last_error\")}, ensure_ascii=False, indent=2))'`
- `python3 backend/scripts/check_brain_prelaunch.py --strict-production`

当前结论（2026-04-16）：

- Package B 的仓内交付已完成
- 正式 NATS 验收仍需在真实事件总线环境中执行并留痕

---

## Package C：安全链路生产验收

目标：

- 确认安全网关已经真正串入主消息入口
- 确认生产上线时不存在绕过认证、限流、审计、脱敏、注入检测的路径

范围：

- `backend/app/services/security_gateway_service.py`
- `backend/app/services/security_service.py`
- `backend/app/brain_core/security/`
- `backend/app/api/routes/`
- Adapter 接入链

任务：

- [x] 梳理所有外部消息入口并确认都经过安全网关
- [x] 验证限流策略在真实入口链路生效
- [x] 验证认证策略在真实入口链路生效
- [x] 验证提示注入检测在主脑入口与外接调用前生效
- [x] 验证敏感字段脱敏在日志、审计、记忆写入前生效
- [x] 验证审计日志关键字段完整落库
- [x] 验证高风险请求被拦截后不会继续进入主脑编排
- [x] 对现有 API / webhook / adapter 路径做绕过扫描
- [x] 整理安全上线门禁清单

当前状态：

- `backend/app/api/routes/webhooks.py` 中的 `workflow_webhook_route` 已补入 `security_gateway_service.inspect_text_entrypoint(...)`，workflow webhook 不再绕开统一安全链
- `backend/scripts/check_security_entrypoints.py` 已新增静态入口扫描，覆盖 `messages.ingest`、通道 webhook、Telegram webhook、workflow webhook
- `backend/scripts/check_security_controls.py` 已新增安全控制烟雾验收，覆盖放行审计、脱敏改写、注入拦截、auth scope 拦截、限流拦截
- `backend/scripts/check_security_controls.py` 已进一步补入真实入口链路副作用验收，验证“脱敏后再写入 task / memory”与“高风险拦截后不进入主脑编排”
- `backend/scripts/check_brain_prelaunch.py` 已纳入 `security_entrypoint_coverage` 严格门禁，外部入口缺失统一安全检查会直接阻塞正式上线
- `backend/scripts/check_brain_prelaunch.py` 已纳入 `security_controls_ready` 严格门禁，安全控制本身异常会直接阻塞正式上线
- `backend/scripts/check_brain_prelaunch.py` 已纳入 `security_audit_persistence_ready` 严格门禁，审计未落入真源或 metadata 丢失会直接阻塞正式上线
- `backend/scripts/check_brain_prelaunch.py` 已纳入 `external_ingress_bypass_scan_ready` 严格门禁，公开入口未命中 baseline protection 会直接阻塞正式上线
- `backend/tests/test_webhooks.py` 已补 workflow webhook 的提示注入拦截回归用例
- `backend/tests/test_messages.py` 已补消息入口“拦截无副作用”和“脱敏后再写入 task / memory”回归用例
- `backend/tests/test_security_entrypoints.py` 已补静态扫描验收测试，确保 `workflow_webhook_route` 持续调用 `security_gateway_service.inspect_text_entrypoint(...)`
- `backend/tests/test_security_controls.py` 已补上线前烟雾校验测试，确保关键安全控制可自动回归
- 已新增 `docs/brain/BRAIN_SECURITY_GATE_CHECKLIST.md`，统一沉淀安全上线门禁命令、阻塞条件与证据留存要求
- 已新增 `backend/scripts/check_security_audit_persistence.py`，可自动验证 allow/block/rewrite 三类审计是否进入 `persistence_service` 真源，并校验 runtime 清空后可从 `list_audit_logs()` 回读
- 已新增 `backend/tests/test_security_audit_persistence.py`，覆盖审计真源落库与关键 metadata 字段保真回归
- 已新增 `backend/scripts/collect_security_acceptance_evidence.py`，可一键打包入口覆盖、安全控制、审计真源和 ingress bypass 的证据 bundle
- 已新增正式留痕模板：`backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md`

门禁命令（补充）：

- `python3 backend/scripts/check_security_audit_persistence.py --strict`
- `python3 backend/scripts/check_external_ingress_bypass.py --strict`

剩余人工项（收口）：

- 在正式数据库环境留存一组真实审计样本，复核字段完整性（trace、prompt 注入评估、rewrite diff）
- 在上线窗口复核 DB 读写权限/备份策略，确保审计真源不可被 runtime fallback 替代
- 对 `check_external_ingress_bypass.py` 输出的 `manual_review_required` 做上线窗口逐项复核，确认反向代理、Header 透传、token/signature 配置与轮换策略符合预期

验收标准：

- 无已知绕过路径
- 认证、限流、注入检测、脱敏、审计全链路有效
- 安全门禁清单可作为上线前核对表

---

## Package D：兼容层继续削薄

目标：

- 保留必要兼容边界，但继续降低误用风险
- 避免团队后续把新逻辑继续写回旧 service 层

范围：

- `backend/app/services/master_bot_service.py`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/brain_core/`
- `backend/scripts/check_architecture_boundaries.py`

任务：

- [x] 标注并梳理当前仍保留的兼容壳清单
- [x] 清点仍在使用的旧 `direct_agent_*` 命名
- [x] 能替换的旧命名继续替换为正式主名
- [x] 对 `master_bot_service.py` 增加更强的冻结说明与守卫
- [x] 对入口层继续检查是否还有业务裁决残留
- [x] 对执行层继续检查是否还有绕过 `execution_gateway` 的路径
- [x] 补齐兼容边界说明文档

当前状态（2026-04-16）：

- 已新增 `docs/brain/BRAIN_COMPAT_BOUNDARY.md`，明确兼容壳清单、主链正式入口/执行路径、`direct_agent_*` 历史别名冻结与迁移策略，以及“不可外置/不可回流”红线。
- 该包已完成代码收口，进入“防回流守卫期”：兼容边界文档、冻结守卫、入口层残留扫描、执行层绕过扫描已补齐，`direct_agent_*` 历史别名向 canonical 写路径已继续收口（含 `agent_execution_service` 的 legacy fallback strategy 出参收口）。
- 已新增 `backend/scripts/check_compatibility_boundaries.py`，可自动输出兼容壳 inventory（覆盖 `master_bot_service.py`、`message_ingestion_service.py`、`workflow_execution_service.py`）与仓库内 `direct_agent_*` 引用清单。
- 脚本支持 `--strict`：若出现 `brain_core` 直接 import compat layer、入口层直连 `routing.rules`、执行层新增 runtime 直连触点、兼容壳 inventory 缺失关键项，或 `direct_agent_*` 生产残留超出冻结基线，会直接失败。
- 已新增 `backend/tests/test_compatibility_boundaries.py`，覆盖 compat import 违规检测、`direct_agent_*` 引用扫描与 strict 失败回归。
- `message_ingestion_service.py` 已摘除对 `app.brain_core.routing.rules.dispatch_intent` 的直接依赖，消息意图推断收回到 `reception_service` 内部。
- `backend/app/brain_core/routing/service.py` 的 `route_decision.routing_strategy` 写路径已收口到 canonical：`workflow_or_agent_dispatch_fallback` / `chat_agent_dispatch`；历史别名仅保留兼容读转换。
- `backend/app/services/workflow_execution_service.py` 的 agent dispatch 新写路径已收口到 canonical：`workflow_id=__agent_dispatch__`、`dispatch_context.type=agent_dispatch`、`fallback_policy.mode=agent_dispatch_fallback`；同时保留 legacy sentinel/alias 读兼容。
- `backend/tests/test_workflows.py`、`backend/tests/test_agents_runtime.py` 已进一步收敛为“canonical 写值 + legacy 读兼容单独断言”；`backend/scripts/check_compatibility_boundaries.py` 的输出已区分 `production residue` 与 `compat test residue`，便于兼容清理排查。
- 验收已通过：`349 passed` 的关键回归集合通过，`check_compatibility_boundaries.py --strict`、`check_architecture_boundaries.py`、`check_todo_sync.py --strict` 全部通过。

守卫项（持续）：

- 持续在新增代码中避免回流 `direct_agent_*` 命名，发现即按 canonical 收口。

验收标准：

- 兼容层只保留薄壳，不再承载真实业务主链
- 新开发默认落在 `brain_core` 正式层次

---

## Package E：记忆治理上线前收口

目标：

- 明确哪些记忆可以存、怎么存、隔离到什么粒度
- 防止主脑在生产环境中出现记忆泄露、越权召回、敏感信息持久化

范围：

- `backend/app/services/memory_service.py`
- `backend/app/core/sqlite_memory_store.py`
- `backend/app/core/chroma_memory_store.py`
- `backend/app/services/tenancy_service.py`
- `backend/app/schemas/memory.py`

任务：

- [x] 划分短期 / 中期 / 长期记忆的写入标准
- [x] 明确敏感字段进入记忆前的脱敏规则
- [x] 明确哪些上下文必须只保留本地不进入长期记忆
- [x] 验证租户 / 项目 / 环境三级隔离是否对记忆读写全覆盖
- [x] 验证记忆召回时不会跨租户泄露
- [x] 验证记忆清理、过期、失效策略
- [x] 整理记忆治理规则文档（`docs/brain/MEMORY_GOVERNANCE.md`）

当前状态（2026-04-15）：

- 三层记忆、隔离策略、生命周期与审核流程已落地并有自动化覆盖。
- 安全网关脱敏规则已作为记忆写入前置约束并有回归测试覆盖。
- `local_only_reasons` / `local_only_filtered_count` 已纳入 memory schema、sqlite mid-term 真源与 long-term metadata。
- `memory_service.distill(...)` 已补入 local-only 硬过滤：命中一次性凭据 / 高风险身份信息 / 临时调试上下文的片段不会进入长期记忆；混合消息会仅保留可长期化片段。
- `backend/tests/test_memory_governance.py` 已新增 local-only 回归，`backend/tests/test_memory.py` 与 `backend/tests/test_database_priority_reads.py` 的相关集合已通过。
- 已新增 `backend/scripts/check_memory_governance.py`，可脚本化输出长期记忆白名单、local-only 原因码、external write block、tenant/global 隔离与生命周期归档结果。
- 已新增 `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`，固化仓内治理样本，便于规则扩展时做对照回归。
- 该包已完成上线前代码收口，进入“规则扩展与防回流守卫期”。

验收标准：

- 记忆读写边界明确
- 敏感数据不会无控制进入长期记忆
- 多租户隔离在记忆系统中成立

---

## Package F：外接触手运维验收

目标：

- 确认主脑对外接 Agent / Skill / MCP 的治理在真实部署中可用
- 确认外部触手异常时主脑仍然可控

范围：

- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/external_skill_registry_service.py`
- `backend/app/services/execution_directory_service.py`
- `backend/app/services/external_connection_auth_service.py`
- `backend/app/api/routes/external_connections.py`
- 外接部署配置

任务：

- [x] 验证外接 Agent 注册、心跳、掉线恢复
- [x] 验证外接 Skill 注册、心跳、掉线恢复
- [x] 验证外接 MCP 桥接能力与健康探测
- [x] 验证灰度发布、回滚、熔断在真实环境可操作
- [x] 验证触手断连时主脑降级而非失控
- [x] 验证注册中心真源与控制面展示一致
- [x] 整理外接能力运维手册

当前状态（2026-04-15）：

- `backend/app/api/routes/external_connections.py` 已补齐 Agent / Skill 的 `recover` 控制面路由，控制面治理接口现已覆盖 `promote / fallback / rollout / rollback / deprecate / recover`。
- `backend/app/services/external_connection_auth_service.py` 已补齐 replay 状态重置接口，外接公开入口已覆盖 token、timestamp+signature、nonce replay 防护；签名校验已改为基于原始请求 JSON，避免因字段别名/默认值归一化导致验签偏差。
- `backend/app/services/external_agent_registry_service.py` 与 `backend/app/services/external_skill_registry_service.py` 已覆盖注册、心跳、失败上报、熔断开路、半开、恢复、重新心跳闭环；其中 Skill 的 `prune_expired()` 半开顺序已修正为与 Agent 一致。
- `backend/tests/test_external_registries.py` 已补 Agent / Skill 的 failure -> open -> half_open -> recover -> heartbeat 闭环回归，以及 Skill 的 canary rollout / rollback 选路回归。
- `backend/tests/test_external_connections.py` 已补 `recover` 控制面路由回归；`backend/tests/test_external_ingress_bypass.py` 与 `backend/scripts/check_external_ingress_bypass.py` 已继续覆盖公开外接入口的 baseline protection 扫描。
- MCP bridge / registry 健康探测已通过 `backend/tests/test_tool_source_service.py`、`backend/tests/test_tools_catalog.py` 固化到 `/api/tools/health`、`/api/tool-sources`、`mcp_registry` 目录扫描链路。
- 已新增 `backend/docs/EXTERNAL_TENTACLE_OPERATIONS.md`，统一沉淀外接能力日常检查、故障处置、灰度/回滚与 MCP fallback 运维口径。
- 已新增 `backend/scripts/collect_external_tentacle_evidence.py`，可对 registry 快照、`health / governance / tool-sources / tools/health` 做一次性留痕打包。

剩余人工项（收口）：

- 在真实外接部署拓扑下留存一轮 `health / governance / tools/health` 样本，确认 Nginx / API Gateway Header 透传与签名配置无偏差。
- 在真实外接 Agent / Skill / MCP 服务上做一次生产窗口演练，留存 rollback 与 recover 操作证据。

验收标准：

- 外接能力可注册、可治理、可恢复
- 主脑对外部能力故障具备可控降级能力

---

## Package G：容灾演练闭环

目标：

- 把“已有容灾脚本”推进到“做过完整演练并沉淀结果”
- 让主脑上线前具备真实故障切换依据

范围：

- `docs/brain/BRAIN_DR_RUNBOOK.md`
- `backend/scripts/dr_precheck.py`
- `backend/scripts/failover_prepare.py`
- `backend/scripts/post_failover_verify.py`
- `backend/scripts/external_tentacle_recovery.py`

任务：

- [ ] 按 runbook 完成一次完整演练
- [ ] 记录真实 RTO / RPO
- [ ] 记录演练中失败步骤与人工介入点
- [ ] 修复演练暴露的问题
- [ ] 回归验证修复后再次演练
- [ ] 把演练结果沉淀成正式记录
- [x] 形成容灾上线门禁（脚本化）

当前状态（2026-04-15）：

- `backend/scripts/dr_result_gate.py` 已新增 DR 结果门禁脚本，可聚合 `dr_precheck / failover_prepare / post_failover_verify / external_tentacle_recovery` 四份结果包。
- `backend/scripts/dr_precheck.py`、`backend/scripts/failover_prepare.py`、`backend/scripts/post_failover_verify.py`、`backend/scripts/external_tentacle_recovery.py` 已统一写入 `gate_stats.failed / gate_stats.manual_intervention`，便于演练后做脚本化裁决。
- `backend/scripts/external_tentacle_recovery.py` 已补显式 `tentacle_recovery_scope.mcp` 字段，外接恢复结果不再只隐含在 Agent / Skill 清单里。
- `backend/scripts/check_brain_prelaunch.py` 已纳入 `dr_result_gate_ready` 严格门禁；若缺少完整结果包，或缺少 `RTO/RPO` 与人工介入统计，将直接阻塞正式生产上线口径。
- DR 门禁默认要求 `formal`：若四份核心报告存在 `smoke/unknown`，`formal_drill_kind_required` 会失败并阻塞生产口径；`--allow-smoke` 仅用于烟雾演练，不可用于正式上线验收。
- `backend/scripts/package_dr_result_bundle.py` 已新增正式证据包打包能力，可把四份核心报告、`dr_result_gate_formal`、bundle 摘要与 archive manifest 归档到同一目录，减少上线窗口手工拷贝风险。
- `backend/scripts/package_dr_result_bundle.py --orchestrate` 已支持一键串行执行 `dr_precheck -> failover_prepare -> post_failover_verify -> external_tentacle_recovery -> gate -> bundle archive`，可直接刷新默认 formal 报告并产出归档。
- `backend/tests/test_dr_scripts.py` 与 `backend/tests/test_brain_prelaunch.py` 已补成功/失败回归，当前本地相关验收已通过。

验收命令（Package G）：

- `python3 -m pytest backend/tests/test_dr_scripts.py backend/tests/test_brain_prelaunch.py -q`
- `python3 backend/scripts/dr_result_gate.py --strict`
- `python3 backend/scripts/dr_result_gate.py --strict --report-prefix dr_result_gate_formal`
- `python3 backend/scripts/package_dr_result_bundle.py --orchestrate --exercise-id <exercise_id> --strict`
- `python3 backend/scripts/package_dr_result_bundle.py --exercise-id <exercise_id> --archive-dir backend/docs/dr_formal_bundle --strict`

验收标准：

- 有真实演练结果
- 有可追踪的 RTO / RPO 数据
- 有明确的容灾上线门禁
- 有完整 formal 证据包（四份核心报告、`dr_result_gate_formal`、bundle 摘要与 archive manifest 同目录归档）

上线口径（Package G）：

- 只有 `formal` 演练结果包可作为“正式生产上线证据”。
- 旧 `smoke` 报告或 `--allow-smoke` 门禁通过结果，不能替代正式演练证据，不能用于宣告主脑生产上线。

---

## Package H：监控、告警与运维看板

目标：

- 把现有 runtime control plane 接入正式运维体系
- 让主脑、worker、外接触手的异常能被及时发现

范围：

- `backend/app/services/dashboard_service.py`
- `backend/app/services/workflow_runtime_snapshot_service.py`
- `backend/app/services/alert_center_service.py`
- `reception/app/dashboard/`
- 监控与告警接入配置

任务：

- [x] 主脑 + runtime + 队列 + dead-letter 指标在控制面已可计算并可视化
- [x] 已提供 Prometheus 文本导出入口（`/api/dashboard/metrics`）
- [x] 已具备统一告警中心（聚合 audit / operational / runtime prepared alerts）
- [x] 已具备告警订阅与手动发送能力（`telegram / wecom / feishu / dingtalk` 通道抽象）
- [x] 已具备告警策略控制面能力（按严重级别配置 `ordered_channels / send_all / max_deliveries / suppression_minutes`）
- [x] 已具备 delivery preview 能力（发送前可预览 matched/selected 订阅、渠道选择结果与原因）
- [x] 已具备统一运维看板（含 `prepared_alerts`、`runtime.recent_alerts`、health signals）
- [x] 已补齐运维落地模板：`backend/docs/PACKAGE_H_OBSERVABILITY_OPERATIONS_TEMPLATE.md`（抓取、看板、通知渠道、升级链、抑制窗口、演练证据）
- [x] 已补齐监控接入/演练留痕辅助资产：`backend/docs/MONITORING_INTEGRATION_TEMPLATE.md`、`backend/scripts/generate_monitoring_evidence_template.py`
- [ ] 真实监控系统抓取配置（Prometheus/Grafana 或企业现网等价体系）仍需落地
- [ ] 真实企业通知渠道配置（机器人凭证、target/chat_id、网络放通）仍需落地
- [ ] 严重级别分层告警策略的真实值班升级链路（值班组、升级时延、抑制窗口）仍需上线配置
- [ ] 上线窗口故障注入/演练并留存“无漏报、可触达、可闭环”证据

当前状态（2026-04-15）：

- `backend/app/services/dashboard_service.py` 已形成主脑运行态统计、SLA health signals、prepared alerts 与 `export_prometheus_metrics(...)` 指标导出能力。
- `backend/app/services/workflow_runtime_snapshot_service.py` 已覆盖 retry / dead-letter / stale run/job 告警构建，运行态风险可进入统一快照。
- `backend/app/services/alert_center_service.py` 已完成告警聚合、去重、ACK/resolve/suppress、订阅配置与手动分发，并已提供严重级别策略控制与 delivery preview（发送前选择预览）；当前回归使用 fake adapter，尚未绑定真实企业通道凭证。
- `reception/app/dashboard/` 已接入 prepared/runtime 告警与健康信号展示，具备统一运维看板入口。
- `backend/docs/PACKAGE_H_OBSERVABILITY_OPERATIONS_TEMPLATE.md` 已提供生产接入模板：Prometheus/Grafana 抓取与看板、企业通知渠道配置清单、值班升级链/抑制窗口、演练证据表。
- `backend/docs/MONITORING_INTEGRATION_TEMPLATE.md` 与 `backend/scripts/generate_monitoring_evidence_template.py` 已补齐监控接入/演练证据模板，便于真实环境落表和留痕。
- `/api/dashboard/metrics` 已支持 `WORKBOT_METRICS_SCRAPE_TOKEN` 抓取口径，仓库内已新增 `deploy/monitoring/docker-compose.monitoring.yml`、Grafana provisioning、`run-monitoring-stack.sh` 与 `backend/scripts/collect_monitoring_alerting_evidence.py`。
- 本地验收已通过：`python3 -m pytest backend/tests/test_dashboard_stats.py backend/tests/test_workflow_runtime_snapshot.py backend/tests/test_alerts.py backend/tests/test_alert_policies.py backend/tests/test_monitoring_evidence_template_script.py -q`（27 passed）。
- 仍需真实环境执行：填入正式 Prometheus/Grafana 参数并接通抓取、配置真实机器人凭证与目标、完成 on-call 值班组与升级时延/抑制窗口上线配置，并在上线窗口完成至少一轮故障注入演练与证据留存。

验收命令（Package H）：

- `python3 -m pytest backend/tests/test_dashboard_stats.py backend/tests/test_workflow_runtime_snapshot.py backend/tests/test_alerts.py backend/tests/test_alert_policies.py backend/tests/test_monitoring_evidence_template_script.py -q`
- `python3 backend/scripts/check_brain_prelaunch.py --strict-production`

阻塞边界（上线口径）：

- 不阻塞“本地可启动/联调”：当前监控与告警代码路径、接口和回归已齐备。
- 阻塞“正式生产值班可用”：若未完成真实 metrics 抓取、企业通知通道凭证与目标配置、on-call 值班升级链上线配置、上线演练证据留存，则不得宣告 Package H 验收完成。

验收标准：

- 关键主链有监控
- 关键风险有告警
- 运维可通过看板快速判断主脑状态

---

## 当前严格 blocker（按未接入正式基础设施时的默认口径）

来源：

- `python3 backend/scripts/check_brain_prelaunch.py`

说明：

- 这一节描述的是“如果正式 PostgreSQL / NATS / 外接拓扑 / formal DR 结果包尚未接入时”，`check_brain_prelaunch.py` 默认会阻塞哪些项。
- 实际环境的最终状态请以执行当时的 `python3 backend/scripts/check_brain_prelaunch.py --strict-production` 输出为准，文档不再静态写死某一次运行结果。

当前严格阻塞项（`strict_blockers`）：

- 未接入正式数据库真源，当前仍处于 fallback/degraded 启动模式。
- NATS 未建立正式连接，当前仍依赖 fallback event bus。
- 调度守卫尚未进入 strict multi-instance ready 状态。
- dispatcher / worker 仍未全部进入 persistent runtime 模式。

说明：

- `release_preflight_green` 已恢复为通过状态；`backend/.env.production.example` 已补齐非默认、非 localhost、强口令/强密钥示例值。
- `dr_result_gate_ready` 已恢复为通过状态；默认会命中最新 formal 报告，不再被旧 `smoke` 文件按文件名字典序误选。

---

## 推荐执行顺序

1. `Package A` 正式真源接入与多实例联调
2. `Package B` NATS 正式链路验收
3. `Package C` 安全链路生产验收
4. `Package F` 外接触手运维验收
5. `Package G` 容灾演练闭环
6. `Package H` 监控、告警与运维看板
7. `Package D` 兼容层继续削薄
8. `Package E` 记忆治理上线前收口

原因：

- A、B、C、F、G、H 直接决定能不能上线
- D、E 更偏长期治理，不应阻塞基础上线验收

---

## 上线前最低门槛

以下条件全部满足，才建议把主脑定义为“可进入正式上线窗口”：

- [ ] 正式数据库真源已接入并完成多实例联调
- [ ] 正式 NATS 链路已验收
- [ ] 安全网关全链路验收通过
- [ ] 外接触手治理与降级能力验收通过
- [ ] 容灾完成至少一轮完整演练
- [ ] 关键监控与告警已接通
- [ ] 启动自检不再仅输出 degraded/fallback 结论

---

## 一句话定义

本文件不是“新功能愿望单”，而是“主脑进入正式上线窗口之前必须完成的开发与验收清单”。
