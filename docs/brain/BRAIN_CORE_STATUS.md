# Brain Core Status

更新时间：2026-04-16（主链完成，仓内守卫与模板已补齐）

## 1. 结论

当前这套“主脑”按现阶段研发清单，已经完成主链开发，并完成了当前定义的 prelaunch 严格门禁。

这句话的准确含义是：

- 主脑核心代码主链已经收口完成
- 当前阶段 TODO 中定义的主脑相关包已经完成
- 但正式生产上线前，仍有一批环境联调、部署验收、兼容层清理工作没有做完

所以现在的状态应定义为：

- 研发完成：是
- 主链完成：是
- prelaunch 严格门禁：通过
- 可继续扩展：是
- 生产终局版完全收官：否

---

## 2. 主脑已完成边界

以下内容已经可以视为主脑正式能力边界内“完成”的部分。

### 2.1 主脑分层已经成型

主脑核心目录已经独立成层：

- `backend/app/brain_core/coordinator`
- `backend/app/brain_core/reception`
- `backend/app/brain_core/routing`
- `backend/app/brain_core/orchestration`
- `backend/app/brain_core/manager`
- `backend/app/brain_core/security`
- `backend/app/brain_core/task_view`

这意味着主脑内部已经不是散落在 service 中的混合逻辑，而是按职责拆成了明确内核层。

### 2.2 主消息入口已经统一

已完成：

- 所有消息入口先进入 `brain_core/coordinator`
- `message_ingestion_service.py` 已迁薄，主要保留入口编排与真源写入
- 主脑内部接待、理解、路由、编排不再分散在旧 service 中各自为政

这部分对应 `Package M` 的“统一 coordinator 入口”和“消息入口统一先走 coordinator”。

### 2.3 项目经理/接待/路由主链已经形成

主脑当前已具备以下正式裁决链：

- 接待与上下文理解：`reception`
- 路由决策与执行计划：`routing`
- 编排与后续动作计划：`orchestration`
- 任务视图投影：`task_view`
- 管理侧状态刷新：`manager`

也就是你之前要求保留在主脑内部的“接待 + 项目经理 + 路由分发”这一层，已经不再依赖外置能力承载核心裁决。

### 2.4 主执行路径已经固定

已经固定为唯一正式路径：

- `brain_core -> execution_gateway -> tentacle_adapters`

这代表：

- 主脑负责裁决
- 网关负责统一执行出口
- 外置 Agent / Skill / MCP 只负责执行，不接管主脑判断权

这正符合“主脑封闭、触手外置、协议统一”的架构原则。

### 2.5 旧主脑兼容层已被冻结

以下旧层已不再承载真实主链，只保留兼容边界：

- `backend/app/services/master_bot_service.py`
- 部分旧 `direct_agent_*` 命名
- 少量冻结的常量级兼容别名

这表示：

- 旧层还在
- 但它们已经不是主脑真实核心
- 新能力不应该继续往这些层里写
- `check_compatibility_boundaries.py --strict` 当前已把生产残留压到 4 条，且只剩常量级兼容字符串，执行别名写路径已继续收口

兼容层边界、正式入口/执行路径、`direct_agent_*` 别名冻结与迁移规则，统一见：

- `docs/brain/BRAIN_COMPAT_BOUNDARY.md`

### 2.6 主脑内部调度协议底座已经补齐

`NEXT_STAGE_4` 中与主脑正式调度底座直接相关的能力已完成：

- `Package Q`：持久化队列协议快照
- `Package R`：调度运行时控制面
- `Package S`：多实例调度守卫

已经落地的能力包括：

- dispatch / workflow execution / agent execution 三类 job 持久化协议快照
- retry / dead-letter / claimed / started / completed / failed 事件链
- runtime snapshot
- queue depth / active lease / stale claim / dead-letter / retry 告警
- stale lease reclaim
- orphan job 巡检
- missing execution job repair
- dispatcher / worker 启动自检
- 多实例 smoke test

### 2.7 架构守卫已经存在

已完成：

- 架构边界检查脚本
- TODO 同步检查
- 相关回归测试与 smoke test

这意味着主脑已经不是“只能靠口头约束”，而是已经有自动化守卫防止后续再写回旧结构。

### 2.8 前端控制面与运行态可视化已接通

已经完成：

- workflow monitor 读取 runtime snapshot
- dashboard 展示调度运行态摘要
- dashboard / workflow monitor 已补运行态筛选、热点摘要与风险排序
- 外接治理控制面已补健康态、路由态、发布通道过滤，便于快速定位熔断与离线 family
- 协作页执行计划可视化 smoke test 已通过

因此当前主脑并不是黑箱，已经开始具备控制面可观测性。

### 2.9 本地知识引用真源已恢复

已经完成：

- 本地知识检索改为读取 `docs/WorkBot_开发全指南.md` 与 `docs/开发指南补充.md`
- 已补回 `docs/security_gateway_pipeline.svg` 与 `docs/memory_distillation_lifecycle.svg`
- 搜索 / 写作结果会优先引用仓内真实文档资产，而不是依赖过期根目录文件路径

---

## 3. 现在不该再混回主脑内部的东西

以下能力应继续保持外置，不应重新写回主脑目录：

- MCP 服务实现本体
- Skill 具体执行实现
- 外接 Agent 执行实现
- 浏览器自动化、搜索、PDF、CRM 等具体触手逻辑
- 外接能力的网络调用细节

主脑内部应保留的，只能是：

- 意图理解
- 需求澄清
- 路由决策
- 执行计划
- 安全策略
- 审计
- 调度
- 真源状态
- 记忆治理

---

## 4. 主脑上线前剩余项

下面这些不是“主脑代码没做”，而是“主脑要进入正式生产形态，还必须补的项”。

### 4.1 仓内 prelaunch 资产已补齐，但正式结论取决于目标环境

当前主脑已经把上线前需要的脚本、模板和仓内守卫补齐：

- `check_scheduler_runtime_pg_acceptance.py`
- `check_nats_roundtrip.py`
- `./check-release-preflight.sh --strict`
- `./check-brain-prelaunch.sh --strict-production`
- `check_compatibility_boundaries.py --strict`
- `check_memory_governance.py --strict`
- `backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md`
- `backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md`
- `backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md`

这代表：

- 仓库内已经具备“可执行正式验收”的资产
- `check_brain_prelaunch.py` 可以对目标环境给出 `blocked / degraded_startable / production_ready`
- 但文档本身不能静态宣告“当前一定 production_ready”，最终结论必须以验收时对真实 PostgreSQL / NATS / 外接拓扑 / 监控凭证的实际输出为准
- 仓库内已新增统一上线证据总包：`backend/scripts/package_release_evidence_bundle.py` / `package-release-evidence.sh`
- 仓库内已新增运行态验收脚本：`backend/scripts/check_release_runtime.py` / `check-release-runtime.sh`

### 4.2 正式多实例部署验收还没做完

还需要补齐：

- 真实数据库下的多实例 dispatcher 验收
- 真实数据库下的多实例 workflow worker 验收
- 真实数据库下的多实例 agent worker 验收
- 真实 NATS 下的事件一致性与恢复测试
- 故障恢复后的 claim reclaim / repair 现场验证

当前 smoke test 证明的是“机制成立”，不是“生产拓扑已经验收完毕”。

仓库内现已补齐：

- `deploy/multi-instance/docker-compose.multi-instance.yml`
- `backend/scripts/run_dispatcher_runtime.py`
- `backend/scripts/run_workflow_execution_worker_runtime.py`
- `backend/scripts/run_agent_execution_worker_runtime.py`
- `run-multi-instance-acceptance.sh`
- `docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`

### 4.3 安全中心与主脑联动还需要做生产级验收

虽然安全网关和安全中心已经有阶段性建设，但主脑上线前还需要重点看：

- 安全策略是否已经完全串入主消息入口
- 审计字段是否在真实场景下完整落库
- 脱敏、注入检测、认证、限流在外部接入链上是否全部生效
- 高风险路由是否存在绕过路径

也就是说，安全能力代码不等于安全上线验收。

当前已经补上的自动化门禁包括：

- `backend/scripts/check_security_entrypoints.py`：检查外部入口是否持续挂在统一安全链上
- `backend/scripts/check_security_controls.py`：检查放行审计、脱敏改写、auth/rate limit 拦截，以及“拦截后无编排副作用”
- `backend/scripts/check_security_audit_persistence.py`：检查 allow / rewrite / block 三类审计是否稳定落入真源，并保留关键 metadata
- `backend/scripts/check_external_ingress_bypass.py`：扫描公开入口与认证控制面，识别未命中 baseline protection 的绕过风险
- `docs/brain/BRAIN_SECURITY_GATE_CHECKLIST.md`：给出上线前必须执行的命令、阻塞条件与证据留存要求

所以这一块已经从“只有安全能力代码”推进到“有自动门禁和核对表”，但仍未替代正式数据库、正式 NATS、真实入口链上的生产验收。

同时，仓库内已新增 `backend/scripts/collect_security_acceptance_evidence.py`，可统一打包自动门禁与控制面样本。

### 4.4 兼容层还没有彻底摘除

当前保留的兼容壳是合理的，但它们仍然是未来的清理对象：

- `master_bot_service.py`
- 旧 `direct_agent_*` 命名
- 少量冻结的常量级兼容别名

这些现在不阻塞主脑主链成立，但长期来看仍需要继续瘦身，避免未来团队误用。

本阶段清理口径以 `docs/brain/BRAIN_COMPAT_BOUNDARY.md` 为准：兼容壳只读、主链唯一、禁止新增 `direct_agent_*` 语义。

同时，`backend/scripts/check_compatibility_boundaries.py --strict` 已升级为冻结基线守卫：

- 仅允许当前文档列出的 4 条生产残留继续存在
- 允许残留继续下降
- 不允许新增 `direct_agent_*` 生产残留或扩散到新文件

### 4.5 记忆系统需要继续做生产策略校准

目前架构上已经有短期/中期/长期记忆与治理方向，但上线前还建议继续收口：

- 哪些记忆能进长期
- 哪些上下文必须只留本地
- 哪些字段必须脱敏后才能进入记忆
- 记忆召回在不同租户/项目/环境下的隔离策略

这部分属于“主脑长期治理能力”，不是主链未完成，但对生产可控性影响很大。

当前仓内已补齐：

- `docs/brain/MEMORY_GOVERNANCE.md`
- `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`
- `backend/scripts/check_memory_governance.py --strict`

这些资产已经把长期记忆白名单、local-only 原因码、tenant/global 隔离和生命周期归档做成可复核基线；仍待补的是上线窗口的真实业务样本抽查。

### 4.6 外接触手的注册、健康、回滚需要继续做运维验证

主脑本身已经有外接治理控制面，但上线前还要确认：

- 外接 Agent 注册中心是否稳定
- 外接 Skill 注册中心是否稳定
- 灰度、回滚、熔断是否在真实部署中可操作
- 外部服务断连后主脑能否保持降级而不失控

仓库内现已补齐 `backend/scripts/collect_external_tentacle_evidence.py`，用于对账 registry 快照与控制面样本。

### 4.7 容灾是有脚本了，但还需要做真实演练闭环

当前已具备：

- `dr_precheck`
- `failover_prepare`
- `post_failover_verify`
- 外接触手恢复脚本

监控与告警侧也已补齐仓库内资产：

- `deploy/monitoring/docker-compose.monitoring.yml`
- `run-monitoring-stack.sh`
- `backend/scripts/collect_monitoring_alerting_evidence.py`
- `backend/docs/MONITORING_INTEGRATION_TEMPLATE.md`

但还需要继续完成：

- 按 runbook 做完整演练
- 记录真实 RTO / RPO
- 修正演练中暴露的问题
- 形成正式上线门禁

### 4.8 监控与告警需要接入正式运维体系

当前已有 runtime control plane，但正式上线前还建议继续补：

- 指标接 Prometheus 或现有监控系统
- 告警接企业通知链路
- 关键事件的分级告警策略
- 主脑健康、worker 健康、外接触手健康的统一看板

---

## 5. 可以认定为“主脑已开发完”的标准

如果按研发视角判断，现在已经满足：

- 主脑代码层明确
- 主脑主链唯一
- 主脑裁决权保留在本地
- 外接执行路径独立
- 运行态控制面存在
- 多实例守卫存在
- 架构边界守卫存在

所以从研发交付角度，可以说：

主脑已经开发完当前应完成的部分。

---

## 6. 不能误判为“已经彻底收官”的点

以下说法现在还不能下结论：

- 主脑已经完成正式生产验收
- 主脑已经完成真实多机多实例上线验证
- 主脑已经彻底删除所有旧兼容层
- 主脑已经完成最终长期治理形态

这些都还属于下一阶段的上线与治理工作。

---

## 7. 当前建议

建议把接下来的工作拆成两条线：

### A. 上线验收线

- 接正式数据库
- 接正式 NATS
- 跑多实例联调
- 跑容灾演练
- 跑安全链路验收

### B. 持续治理线

- 继续削薄兼容层
- 继续统一旧命名
- 继续补监控告警
- 继续收紧记忆治理
- 继续固化运维门禁

---

## 8. 一句话定义

当前主脑状态最准确的定义是：

主脑研发主链已完成，生产终局验收未完成。
