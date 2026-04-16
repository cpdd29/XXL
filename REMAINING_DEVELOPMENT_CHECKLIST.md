# 剩余开发清单

更新时间：2026-04-16

## 当前状态

- 主脑与外接触手已经联通
- 主脑研发主链已完成
- 当前剩余工作重点，已经从“核心链路开发”转为“生产落地验收、运维接入、演练闭环、兼容层清理”
- `Package A / C / D / E / H` 的仓库内交付已补齐：多实例 compose、监控 compose、外接/安全证据采集脚本、相关文档与启动脚本已经落仓
- `Package A / D / E` 的正式验收模板已补齐：`backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md`、`backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md`、`backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md`
- `Package F / G / H` 的仓内收口继续推进：兼容层冻结基线守卫、记忆治理仓内验收脚本与校准样本、文档口径同步已补齐
- 仓库内自动化回归已完成收口：`webhooks / messages / security / architecture / assets` 相关验收批次已回归通过
- 当前真正未完成的部分，主要是需要真实 PostgreSQL / NATS / Prometheus / Grafana / 企业通知凭证 / 外接部署拓扑才能执行的生产环境验收

---

## 一、必须完成项

这些项目建议作为“正式上线前必须完成”的收口清单。

### 1. 多实例正式验收

目标：

- 把当前单仓可运行、单机可验证，推进到真实生产拓扑可验收

任务：

- [ ] 在真实 PostgreSQL 真源下完成双 dispatcher 联调
- [ ] 在真实 PostgreSQL 真源下完成双 workflow worker 联调
- [ ] 在真实 PostgreSQL 真源下完成双 agent worker 联调
- [ ] 验证 claim 排他、lease reclaim、missing job repair、orphan job repair
- [ ] 在真实 NATS 下复核 dispatch / workflow / agent 三类事件链一致性
- [ ] 留存正式联调记录与验收证据

验收标准：

- [ ] 多实例下无重复消费、无重复执行、无失控重试
- [ ] worker 异常恢复后任务链可继续推进
- [ ] 真源状态与运行态一致

### 2. 容灾正式演练

目标：

- 把“已有 DR 脚本”推进到“完成过 formal drill 并有证据包”

任务：

- [ ] 按 `docs/brain/BRAIN_DR_RUNBOOK.md` 做一次完整 formal 演练
- [ ] 记录真实 RTO / RPO
- [ ] 记录人工介入点、失败步骤、恢复耗时
- [ ] 修复演练中暴露的问题
- [ ] 修复后再次回归演练
- [ ] 生成正式 evidence bundle 并归档

验收标准：

- [ ] 不再只有 smoke 结果
- [ ] 有完整 formal 报告
- [ ] `dr_result_gate` 严格口径通过

### 3. 监控与告警接真实运维体系

目标：

- 把当前已完成的看板、指标、告警中心，真正接入生产可用的监控链

任务：

- [ ] 接通真实 Prometheus / Grafana 或企业等价监控体系
- [ ] 配置 `/api/dashboard/metrics` 的真实抓取
- [ ] 配置真实企业通知通道凭证
- [ ] 配置告警目标、机器人、chat_id / webhook / target
- [ ] 配置值班升级链、抑制窗口、严重级别分层策略
- [ ] 做至少一轮告警演练并留证据

验收标准：

- [ ] 关键主链有 metrics
- [ ] 关键异常可触达
- [ ] 告警可 ACK / resolve / suppress
- [ ] 运维看板能反映真实运行态

### 4. 外接触手生产运维验收

目标：

- 把外接 Agent / Skill / MCP 从“开发可用”推进到“生产可治理”

任务：

- [ ] 在真实外接部署拓扑下验证 Agent 注册、心跳、掉线恢复
- [ ] 在真实外接部署拓扑下验证 Skill 注册、心跳、掉线恢复
- [ ] 在真实外接部署拓扑下验证 MCP 健康探测与桥接可用
- [ ] 做一次真实灰度、回滚、recover 演练
- [ ] 留存 `health / governance / tools/health` 样本
- [ ] 复核网关 / 反向代理 / Header 透传 / 签名链路

验收标准：

- [ ] 外接能力掉线后主脑可降级
- [ ] 外接能力恢复后可重新接入
- [ ] 控制面状态与真实 registry 一致

### 5. 安全链路生产验收

目标：

- 确认统一消息入口、安全网关、审计真源在真实入口链路全部有效

任务：

- [ ] 复核所有正式入口都经过安全网关
- [ ] 复核限流、认证、注入检测、脱敏、审计在真实入口生效
- [ ] 留存 allow / rewrite / block 三类真实审计样本
- [ ] 复核反向代理、Header 透传、签名校验配置
- [ ] 复核 DB 审计真源权限、备份与只读恢复策略
- [ ] 对 bypass scan 输出的人工复核项逐项核销

验收标准：

- [ ] 无已知绕过路径
- [ ] 高风险请求不会继续进入主脑编排
- [ ] 审计字段完整可追溯

---

## 二、可延期完成项

这些项目不阻塞“主链已经可上线验收”的判断，但建议尽快继续做。

### 6. 兼容层继续削薄

目标：

- 降低误用旧 service 层的风险

任务：

- [x] 继续缩薄 `master_bot_service.py`
- [x] 继续减少旧 `direct_agent_*` 命名残留
- [x] 继续收口旧 wrapper / alias
- [x] 保持 `brain_core` 为唯一正式主链

验收标准：

- [x] 新代码不再写入兼容层
- [x] 兼容壳只保留读兼容和过渡能力

当前状态：

- 已通过 `check_compatibility_boundaries.py --strict` 把生产残留冻结为当前基线，只允许下降，不允许新增回流。

### 7. 记忆治理生产校准

目标：

- 把三层记忆从“规则已落地”推进到“生产策略精修完成”

任务：

- [x] 细化长期记忆白名单
- [x] 复核 local-only 场景覆盖是否足够
- [x] 复核跨租户 / 项目 / 环境隔离
- [x] 复核召回质量与敏感字段过滤效果
- [ ] 补一轮真实业务样本校验

验收标准：

- [x] 长期记忆不混入敏感临时上下文
- [x] 召回不跨边界
- [ ] 记忆治理规则与真实业务匹配

当前状态：

- 已新增 `check_memory_governance.py --strict` 与 `MEMORY_GOVERNANCE_CALIBRATION.md`，仓内白名单、local-only、隔离与生命周期校验已可重复执行。
- 唯一剩余项是结合真实业务样本做最终人工抽查。

### 8. 文档全面同步

目标：

- 清掉旧文档口径与当前实际状态不一致的问题

任务：

- [x] 同步 `README.md` 到最新主脑 / 外接双仓结构
- [x] 检查根目录遗留文档是否需要迁移到 `docs/`
- [x] 更新启动、验收、部署、联调口径
- [x] 明确“已完成 / 未完成 / 仅保留兼容边界”的说明

验收标准：

- [x] 文档与代码状态一致
- [x] 新同事按文档即可启动和验收

---

## 三、优化项

这些项目不属于当前强阻塞，更偏长期治理和体验提升。

### 9. 兼容旧名技术债清理

- [ ] 继续统一历史字段 snake/camel 双写口径
- [ ] 继续移除低价值兼容别名
- [ ] 继续减少无效 DTO / 重复包装

当前状态：

- `direct_agent_dispatch` 属性别名、`create_direct_agent_run_for_task` wrapper 与编排层兼容入参已移除。
- `check_compatibility_boundaries.py --strict` 已通过，生产残留已从 9 条降到 4 条，且全部收敛为常量级兼容字符串，不再包含可执行别名写路径。
- 本地知识引用真源已切到 `docs/`，`WorkBot_开发全指南.md`、`开发指南补充.md` 与架构 SVG 现在都能被搜索/写作链路命中。

### 10. 控制面体验优化

- [x] 优化 Dashboard / Workflow Monitor 的可读性
- [x] 增强队列、死信、重试、claim 的筛选与定位能力
- [x] 优化外接治理页面的运维体验

当前状态：

- 已在 `reception/app/dashboard/page.tsx` 与 `reception/components/workflow/workflow-inspector.tsx` 补运行态筛选、风险排序、热点摘要与无结果提示。
- Dashboard 与 Workflow Monitor 现在都支持按队列焦点、告警级别、来源/关键词快速定位 `claim / retry / dead-letter / stale` 问题。
- 已在 `reception/app/settings/external-capabilities/page.tsx` 补健康态、路由态、发布通道筛选与风险优先排序，外接治理页现在可快速定位熔断、离线、非可路由和 canary family。

### 11. 运维自动化增强

- [x] 把更多上线前检查收进统一脚本
- [x] 增强发布前自检、回滚自检、恢复后自检
- [x] 补充一键证据打包和归档能力

当前状态：

- 已新增 `backend/scripts/package_release_evidence_bundle.py` 与 `./package-release-evidence.sh`，统一串行归档 `release_preflight / brain_prelaunch / compatibility_boundaries / memory_governance / release_runtime / monitoring / external / security / dr_bundle`。
- 已新增 `backend/scripts/check_release_runtime.py` 与 `./check-release-runtime.sh`，统一覆盖 `postdeploy / rollback / recovery` 三类运行态验收并生成报告。
- 真实生产切流、真实回滚动作、真实恢复动作仍需要在目标环境中实际执行；仓库内已补齐对应的自检脚本与留档入口。

---

## 四、建议优先顺序

### 第一优先级

- [ ] 多实例正式验收
- [ ] 容灾正式演练
- [ ] 监控与告警接真实体系
- [ ] 外接触手生产运维验收
- [ ] 安全链路生产验收

### 第二优先级

- [ ] 兼容层继续削薄
- [ ] 记忆治理生产校准
- [ ] 文档全面同步

### 第三优先级

- [ ] 技术债清理
- [ ] 控制面体验优化
- [ ] 运维自动化增强

---

## 五、一句话结论

当前项目已经不是“主脑还没开发完”，而是“主脑主链已完成，仓库内辅助资产也已补齐，剩余项集中在真实生产验收、运维接入和演练闭环”。
