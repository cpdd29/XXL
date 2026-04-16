# 剩余开发执行版清单

更新时间：2026-04-16

关联文件：

- `REMAINING_DEVELOPMENT_CHECKLIST.md`
- `docs/brain/BRAIN_PRELAUNCH_TODO.md`
- `docs/brain/BRAIN_CORE_STATUS.md`
- `docs/stages/NEXT_STAGE_4_TODO.md`

适用目标：

- 把“剩余开发清单”进一步拆成可直接执行的开发包
- 每个开发包明确涉及文件、执行步骤、验收命令、交付产物
- 方便继续多轮推进，不再停留在概念层

---

## 使用规则

每完成一个包，至少同步这三类产物：

- 代码或配置改动
- 验收输出或证据文件
- 文档状态更新

建议每个包完成后同步更新：

- `REMAINING_DEVELOPMENT_CHECKLIST.md`
- `docs/brain/BRAIN_CORE_STATUS.md`
- 对应专题文档或 runbook

## 本轮仓库内已补齐资产（2026-04-16）

- 多实例运行入口：`backend/scripts/run_dispatcher_runtime.py`、`backend/scripts/run_workflow_execution_worker_runtime.py`、`backend/scripts/run_agent_execution_worker_runtime.py`
- 多实例部署模板：`deploy/multi-instance/docker-compose.multi-instance.yml`、`deploy/multi-instance/.env.multi-instance.example`、`run-multi-instance-acceptance.sh`
- 监控模板：`deploy/monitoring/docker-compose.monitoring.yml`、Prometheus / Grafana provisioning、`run-monitoring-stack.sh`
- 监控证据采集：`backend/scripts/collect_monitoring_alerting_evidence.py`
- 外接运维证据采集：`backend/scripts/collect_external_tentacle_evidence.py`
- 安全上线证据采集：`backend/scripts/collect_security_acceptance_evidence.py`
- 正式验收模板：`backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md`、`backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md`、`backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md`
- 统一上线证据总包：`backend/scripts/package_release_evidence_bundle.py`、`package-release-evidence.sh`
- 兼容层冻结守卫：`backend/scripts/check_compatibility_boundaries.py` 已升级为“冻结基线 + 防回流”严格模式
- 记忆治理仓内验收：`backend/scripts/check_memory_governance.py`、`docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`
- 文档同步：`README.md`、`docs/brain/BRAIN_DUAL_REPO_STARTUP.md`、`docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`、相关运行手册与模板
- 自动化回归收口：`backend/tests/test_webhooks.py`、`backend/tests/test_messages.py`、安全批、架构批、资产批已串行回归通过

---

## Package A：多实例正式验收

目标：

- 把当前“脚本可通过、单机可运行”推进到“真实多实例部署可验收”

### 涉及文件

- `backend/app/services/workflow_dispatch_poller_service.py`
- `backend/app/services/workflow_dispatcher_service.py`
- `backend/app/services/workflow_execution_worker_service.py`
- `backend/app/services/agent_execution_worker_service.py`
- `backend/app/services/scheduler_guard_service.py`
- `backend/app/services/persistence_service.py`
- `backend/app/core/nats_event_bus.py`
- `backend/scripts/check_scheduler_startup.py`
- `backend/scripts/check_scheduler_runtime_pg_acceptance.py`
- `backend/scripts/check_nats_contract.py`
- `backend/scripts/check_nats_roundtrip.py`
- `backend/scripts/run_dispatcher_runtime.py`
- `backend/scripts/run_workflow_execution_worker_runtime.py`
- `backend/scripts/run_agent_execution_worker_runtime.py`
- `docker-compose.yml`
- 生产部署配置文件或 compose override
- `deploy/multi-instance/docker-compose.multi-instance.yml`
- `run-multi-instance-acceptance.sh`
- `docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`

### 子任务

- [ ] A1. 准备正式 PostgreSQL / NATS 环境变量
- [ ] A2. 准备至少双 dispatcher 实例配置
- [ ] A3. 准备至少双 workflow worker 实例配置
- [ ] A4. 准备至少双 agent worker 实例配置
- [ ] A5. 验证 claim 排他
- [ ] A6. 验证 stale lease reclaim
- [ ] A7. 验证 missing execution job repair
- [ ] A8. 验证 orphan job repair
- [ ] A9. 验证 NATS 断连与恢复后的行为
- [ ] A10. 输出正式验收记录

### 执行步骤

1. 准备真实环境变量
   - 配置正式 `WORKBOT_DATABASE_URL`
   - 配置正式 `WORKBOT_NATS_URL`
   - 确认不再使用 fallback / localhost 默认值

2. 启动多实例
   - dispatcher 至少 2 个实例
   - workflow execution worker 至少 2 个实例
   - agent execution worker 至少 2 个实例
   - 所有实例共用同一个 PostgreSQL 与 NATS

3. 跑正式真源验收
   - 先验 `persistence contract`
   - 再验 `scheduler startup`
   - 再验 `runtime pg acceptance`
   - 再验 `nats contract`
   - 再验 `nats roundtrip`

4. 做故障切换场景
   - 强制停一个 dispatcher
   - 强制停一个 workflow worker
   - 强制停一个 agent worker
   - 观察 lease reclaim、job repair、队列恢复

5. 固化结果
   - 保存终端输出
   - 保存运行截图或日志
   - 形成正式联调记录

### 验收命令

```bash
python3 backend/scripts/check_production_env_contract.py --strict
python3 backend/scripts/check_persistence_contract.py --strict
python3 backend/scripts/check_scheduler_startup.py
python3 backend/scripts/check_scheduler_runtime_pg_acceptance.py --database-url <postgres_dsn> --strict
python3 backend/scripts/check_nats_contract.py --strict
python3 backend/scripts/check_nats_roundtrip.py --nats-url <nats_url> --strict
python3 backend/scripts/check_brain_prelaunch.py --strict-production
```

### 交付产物

- [ ] 多实例部署配置
- [ ] 正式验收日志
- [ ] 故障恢复验证记录
- [ ] 文档状态更新

建议记录模板：

- `backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md`

---

## Package B：容灾正式演练

目标：

- 把 DR 从“有脚本”推进到“有 formal drill、有证据包、有 RTO/RPO”

### 涉及文件

- `docs/brain/BRAIN_DR_RUNBOOK.md`
- `backend/scripts/dr_precheck.py`
- `backend/scripts/failover_prepare.py`
- `backend/scripts/post_failover_verify.py`
- `backend/scripts/external_tentacle_recovery.py`
- `backend/scripts/dr_result_gate.py`
- `backend/scripts/package_dr_result_bundle.py`
- `backend/docs/`

### 子任务

- [ ] B1. 按 runbook 明确正式演练场景
- [ ] B2. 执行 precheck
- [ ] B3. 执行 failover prepare
- [ ] B4. 执行 failover 后 verify
- [ ] B5. 执行外接触手恢复检查
- [ ] B6. 记录 RTO / RPO
- [ ] B7. 记录人工介入点
- [ ] B8. 对失败点修复并复演
- [ ] B9. 打包 formal evidence bundle

### 执行步骤

1. 选定一次 formal exercise id
2. 严格按 runbook 跑四段主链
3. 记录各阶段耗时与异常点
4. 跑 `dr_result_gate` 做 formal 判定
5. 跑 `package_dr_result_bundle.py` 打包归档

### 验收命令

```bash
python3 -m pytest backend/tests/test_dr_scripts.py backend/tests/test_brain_prelaunch.py -q
python3 backend/scripts/dr_result_gate.py --strict
python3 backend/scripts/dr_result_gate.py --strict --report-prefix dr_result_gate_formal
python3 backend/scripts/package_dr_result_bundle.py --orchestrate --exercise-id <exercise_id> --strict
python3 backend/scripts/package_dr_result_bundle.py --exercise-id <exercise_id> --archive-dir backend/docs/dr_formal_bundle --strict
```

### 交付产物

- [ ] formal 演练结果
- [ ] RTO / RPO 记录
- [ ] 人工介入点清单
- [ ] DR evidence bundle

---

## Package C：监控与告警接真实体系

目标：

- 把已经存在的 Dashboard / metrics / alert center 接进真实监控和值班链

### 涉及文件

- `backend/app/services/dashboard_service.py`
- `backend/app/services/workflow_runtime_snapshot_service.py`
- `backend/app/services/alert_center_service.py`
- `backend/app/api/routes/dashboard.py`
- `backend/app/api/routes/alerts.py`
- `backend/docs/PACKAGE_H_OBSERVABILITY_OPERATIONS_TEMPLATE.md`
- `backend/docs/MONITORING_INTEGRATION_TEMPLATE.md`
- `backend/scripts/generate_monitoring_evidence_template.py`
- `backend/scripts/collect_monitoring_alerting_evidence.py`
- `reception/app/dashboard/page.tsx`
- `reception/components/`
- 运维监控配置文件
- `deploy/monitoring/`
- `run-monitoring-stack.sh`

### 子任务

- [ ] C1. 接通真实 metrics 抓取
- [ ] C2. 配置真实 Grafana 或等价看板
- [ ] C3. 配置真实企业通知通道
- [ ] C4. 配置严重级别策略与升级链
- [ ] C5. 做一次告警触发演练
- [ ] C6. 做一次告警 ACK/resolve/suppress 演练
- [ ] C7. 留存可触达证据

### 执行步骤

1. 明确监控接入方式
   - Prometheus / Grafana
   - 企业现网等价监控系统

2. 接 metrics
   - 让监控系统抓取 `/api/dashboard/metrics`
   - 验证主脑、队列、dead-letter、retry 指标可见

3. 接告警
   - 配置 Telegram / WeCom / Feishu / DingTalk 真实凭证
   - 配置目标路由
   - 配置升级链和抑制窗口

4. 做故障注入
   - 人工触发 runtime prepared alerts
   - 验证通知到达、ACK、resolve 全链闭环

### 验收命令

```bash
python3 -m pytest backend/tests/test_dashboard_stats.py backend/tests/test_workflow_runtime_snapshot.py backend/tests/test_alerts.py backend/tests/test_alert_policies.py backend/tests/test_monitoring_evidence_template_script.py -q
python3 backend/scripts/generate_monitoring_evidence_template.py
python3 backend/scripts/check_brain_prelaunch.py --strict-production
```

### 交付产物

- [ ] 真实监控抓取配置
- [ ] 告警通道配置记录
- [ ] 值班升级链配置记录
- [ ] 故障注入与告警证据

---

## Package D：外接触手生产运维验收

目标：

- 把外接 Agent / Skill / MCP 从“功能可用”推进到“生产可治理、可恢复”

### 涉及文件

- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/external_skill_registry_service.py`
- `backend/app/services/execution_directory_service.py`
- `backend/app/services/external_connection_auth_service.py`
- `backend/app/services/mcp_runtime_service.py`
- `backend/app/api/routes/external_connections.py`
- `backend/docs/EXTERNAL_TENTACLE_OPERATIONS.md`
- `backend/scripts/collect_external_tentacle_evidence.py`
- `XXL_ExternalConnection/docker-compose.yml`
- `XXL_ExternalConnection/config/workbot_external_sources.combined.json`
- `XXL_ExternalConnection/docs/external-deployment.md`
- `XXL_ExternalConnection/docs/combined-registry.md`
- `XXL_ExternalConnection/agents/`
- `XXL_ExternalConnection/skills/`
- `XXL_ExternalConnection/mcp-services/`

### 子任务

- [ ] D1. 复核外接 registry 配置与实际服务一致
- [ ] D2. 验证 Agent 注册、心跳、掉线恢复
- [ ] D3. 验证 Skill 注册、心跳、掉线恢复
- [ ] D4. 验证 MCP 健康探测与桥接
- [ ] D5. 做一次灰度发布演练
- [ ] D6. 做一次 fallback / rollback / recover 演练
- [ ] D7. 留存 `health / governance / tools/health` 样本
- [ ] D8. 复核签名、Header 透传、网关配置

### 执行步骤

1. 启动外接仓
   - 确认 `run-external.sh` 与 `docker-compose.yml` 正常
   - 确认 registry 文件和实际端口一致

2. 逐项验服务
   - MCP 服务存活
   - 外接 Agent 可见
   - Skill 可见
   - 主脑可读到治理信息

3. 做异常演练
   - 停某个 Agent
   - 停某个 MCP
   - 观察主脑降级和恢复

4. 做治理演练
   - promote
   - set fallback
   - rollout
   - rollback
   - recover

### 验收命令

```bash
python3 -m pytest backend/tests/test_external_connections.py backend/tests/test_external_registries.py backend/tests/test_tool_source_service.py backend/tests/test_tools_catalog.py backend/tests/test_external_ingress_bypass.py -q
python3 backend/scripts/check_external_ingress_bypass.py --strict
./run-external.sh
./run-brain.sh
```

### 交付产物

- [ ] 外接 registry 对账结果
- [ ] 治理操作演练记录
- [ ] 掉线恢复记录
- [ ] 网关与签名链复核记录

建议记录模板：

- `backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md`

---

## Package E：安全链路生产验收

目标：

- 确认统一消息入口、安全网关、日志审计、脱敏链在真实环境下全部闭环

### 涉及文件

- `backend/app/services/security_gateway_service.py`
- `backend/app/services/security_service.py`
- `backend/app/brain_core/security/`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/api/routes/messages.py`
- `backend/app/api/routes/webhooks.py`
- `backend/app/api/routes/security.py`
- `backend/scripts/check_security_entrypoints.py`
- `backend/scripts/check_security_controls.py`
- `backend/scripts/check_security_audit_persistence.py`
- `backend/scripts/check_external_ingress_bypass.py`
- `backend/scripts/collect_security_acceptance_evidence.py`
- `docs/brain/BRAIN_SECURITY_GATE_CHECKLIST.md`

### 子任务

- [ ] E1. 盘点全部正式入口
- [ ] E2. 复核统一安全网关是否全覆盖
- [ ] E3. 验证限流真实生效
- [ ] E4. 验证认证真实生效
- [ ] E5. 验证注入检测真实生效
- [ ] E6. 验证脱敏先于真源写入
- [ ] E7. 验证 allow / rewrite / block 审计样本
- [ ] E8. 复核 bypass scan 的人工项

### 执行步骤

1. 列全部入口
   - API
   - webhook
   - DingTalk / Telegram / 其他 adapter
   - 外接公开入口

2. 跑自动门禁
   - 入口扫描
   - 控制校验
   - 审计落库校验
   - bypass 扫描

3. 做真实链路样本
   - allow 一条
   - rewrite 一条
   - block 一条
   - 从数据库回读审计字段

4. 复核网关层
   - Header 透传
   - 签名
   - token
   - 反向代理

### 验收命令

```bash
python3 -m pytest backend/tests/test_security.py backend/tests/test_security_entrypoints.py backend/tests/test_security_controls.py backend/tests/test_security_audit_persistence.py backend/tests/test_webhooks.py backend/tests/test_messages.py -q
python3 backend/scripts/check_security_entrypoints.py --strict
python3 backend/scripts/check_security_controls.py --strict
python3 backend/scripts/check_security_audit_persistence.py --strict
python3 backend/scripts/check_external_ingress_bypass.py --strict
```

### 交付产物

- [ ] 三类审计样本
- [ ] 真实入口覆盖表
- [ ] bypass 人工复核记录
- [ ] 安全上线验收记录

建议记录模板：

- `backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md`

---

## Package F：兼容层继续削薄

目标：

- 减少旧 service 层误用风险，继续收口到 `brain_core`

### 涉及文件

- `backend/app/services/master_bot_service.py`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/brain_core/`
- `backend/scripts/check_architecture_boundaries.py`
- `backend/scripts/check_compatibility_boundaries.py`
- `docs/brain/BRAIN_COMPAT_BOUNDARY.md`

### 子任务

- [x] F1. 列出当前兼容壳 inventory
- [x] F2. 清点旧 `direct_agent_*` 残留
- [x] F3. 能改名的继续改成 canonical
- [x] F4. 能迁出的逻辑继续迁出 compat 层
- [x] F5. 增强守卫，防止新逻辑回流

### 验收命令

```bash
python3 backend/scripts/check_architecture_boundaries.py
python3 backend/scripts/check_compatibility_boundaries.py --strict
python3 -m pytest backend/tests/test_architecture_boundaries.py backend/tests/test_compatibility_boundaries.py -q
```

### 交付产物

- [x] compat inventory 更新
- [x] canonical 命名收口记录
- [x] 架构守卫回归通过

当前状态（2026-04-16）：

- 已冻结兼容层生产残留基线为 4 条，`check_compatibility_boundaries.py --strict` 会阻止新增残留或扩散到新文件。
- `direct_agent_*` 写路径已继续收口到 canonical，剩余生产残留仅保留常量级兼容字符串。
- 本地知识引用真源已切回 `docs/`，搜索/写作链路可以稳定引用 `WorkBot_开发全指南.md`、`开发指南补充.md` 与本地架构 SVG。

---

## Package G：记忆治理生产校准

目标：

- 把三层记忆从“已实现”推进到“生产策略校准完成”

### 涉及文件

- `backend/app/services/memory_service.py`
- `backend/app/core/sqlite_memory_store.py`
- `backend/app/core/chroma_memory_store.py`
- `backend/app/services/tenancy_service.py`
- `backend/app/schemas/memory.py`
- `docs/brain/MEMORY_GOVERNANCE.md`

### 子任务

- [x] G1. 细化长期记忆白名单
- [ ] G2. 补一轮真实样本审查
- [x] G3. 复核 local-only 规则
- [x] G4. 复核租户 / 项目 / 环境隔离
- [x] G5. 复核过期与清理策略

### 验收命令

```bash
python3 backend/scripts/check_memory_governance.py --strict
python3 -m pytest backend/tests/test_memory.py backend/tests/test_memory_governance.py backend/tests/test_memory_longterm_chroma.py backend/tests/test_database_priority_reads.py backend/tests/test_tenancy_isolation.py -q
```

### 交付产物

- [ ] 真实样本校准记录
- [x] 记忆白名单更新
- [x] 记忆治理文档更新

当前状态（2026-04-16）：

- 已新增长期记忆白名单快照、local-only 原因码清单与仓内治理验收脚本。
- 已新增 `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`，用于仓内样本回归对照。
- 唯一剩余项是“真实业务样本抽查”，需要上线窗口或真实业务数据配合。

---

## Package H：文档全面同步

目标：

- 让当前代码状态、双仓启动方式、上线口径和文档完全一致

### 涉及文件

- `README.md`
- `REMAINING_DEVELOPMENT_CHECKLIST.md`
- `REMAINING_DEVELOPMENT_EXECUTION_PLAN.md`
- `docs/brain/BRAIN_CORE_STATUS.md`
- `docs/brain/BRAIN_DUAL_REPO_STARTUP.md`
- `docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`
- `docs/brain/BRAIN_PRELAUNCH_TODO.md`
- `docs/brain/BRAIN_SECURITY_GATE_CHECKLIST.md`
- `XXL_ExternalConnection/README.md`
- `XXL_ExternalConnection/docs/external-deployment.md`

### 子任务

- [x] H1. 更新根 README 的状态口径
- [x] H2. 更新双仓启动文档
- [x] H3. 更新上线前验收命令
- [x] H4. 更新外接部署与接线说明
- [x] H5. 清理过时描述

### 验收标准

- [x] 新人只看文档就能启动
- [x] 文档不再出现与当前代码状态冲突的旧表述

当前状态（2026-04-16）：

- 已同步 README、双仓启动文档、兼容边界、记忆治理与 prelaunch 文档。
- 已把“仓内资产已补齐”和“真实环境已验收完成”拆开表述，避免状态误判。

---

## Package I：运维自动化增强

目标：

- 把分散的预检与证据脚本继续统一，减少上线窗口的人肉拼装

### 涉及文件

- `backend/scripts/package_release_evidence_bundle.py`
- `backend/scripts/check_release_runtime.py`
- `package-release-evidence.sh`
- `check-release-runtime.sh`
- `backend/docs/PACKAGE_U_RELEASE_PLAYBOOK.md`
- `README.md`

### 子任务

- [x] I1. 把更多上线前检查收进统一脚本
- [x] I2. 增强发布前自检、回滚自检、恢复后自检
- [x] I3. 补充一键证据打包和归档能力

### 验收命令

```bash
python3 -m pytest backend/tests/test_release_runtime_check.py backend/tests/test_release_evidence_bundle.py backend/tests/test_remaining_development_assets.py -q
python3 backend/scripts/check_release_runtime.py --scenario all
python3 backend/scripts/package_release_evidence_bundle.py --skip-monitoring --skip-external --skip-security
```

### 交付产物

- [x] 统一上线证据总包脚本
- [x] 统一运行态验收脚本
- [x] Docker 包装入口
- [x] Release playbook 更新

当前状态（2026-04-16）：

- 已新增统一入口，能把 `release_preflight / brain_prelaunch / compatibility_boundaries / memory_governance / release_runtime / monitoring / external / security / dr_bundle` 汇总为同一份 archive manifest。
- 已新增 `check_release_runtime.py` / `check-release-runtime.sh`，可对 `postdeploy / rollback / recovery` 三种场景执行仓库内闭环自检并生成报告。
- 仍待目标环境落地的部分，是“真实生产切流后的动作执行本身”，这需要绑定真实发布窗口、真实流量切换与真实外部资源。

---

## 建议执行顺序

### 第一批

- Package A：多实例正式验收
- Package B：容灾正式演练
- Package C：监控与告警接真实体系
- Package D：外接触手生产运维验收
- Package E：安全链路生产验收

### 第二批

- Package F：兼容层继续削薄
- Package G：记忆治理生产校准
- Package H：文档全面同步

---

## 最终完成定义

满足以下条件后，才建议把“剩余开发项”定义为基本完成：

- [ ] 多实例正式验收完成
- [ ] formal DR 演练完成并归档
- [ ] 真实监控与告警链路接通
- [ ] 外接触手生产治理验收完成
- [ ] 安全链路生产验收完成
- [x] compat 层继续收口一轮
- [x] 文档与代码状态完全同步
