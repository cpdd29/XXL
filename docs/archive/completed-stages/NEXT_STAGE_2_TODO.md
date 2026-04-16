# Next Stage 2 TODO

更新时间：2026-04-13
目标：在“接入层 + 安全网关 + 统一事件协议 + 主脑执行闭环 + 成本/SLA”完成后，把系统推进到可上线、可告警、可审批、可回放、可扩容的生产级主脑。

原则：

- 大脑封闭：裁决权、真源、审计权、审批权必须保留在本地主脑
- 触手外置：Agent / Skill / MCP 只做执行，不做最终裁决
- 协议统一：调度、回传、告警、审批、事件都走正式协议
- 先运营闭环后生态扩展：先把告警、审批、回放、隔离做好，再做规模化扩展

---

## Package M：主脑决策真源固化

目标：

- 把主脑关键裁决从“运行时上下文混合字段”升级为正式 fact schema
- 让每次 run 的决策都可审计、可回放、可比较

范围：

- `backend/app/services/workflow_execution_service.py`
- `backend/app/schemas/workflows.py`
- `backend/app/services/collaboration_service.py`
- `backend/app/services/task_service.py`

任务：

- [x] 定义 `brain_fact_snapshot` 顶层 schema
- [x] 固化路由决策 fact
- [x] 固化 fallback 决策 fact
- [x] 固化审批/人工接管 fact
- [x] 固化最终交付决策 fact
- [x] 区分运行态字段与审计态字段
- [x] 增加 fact version
- [x] 增加 run detail / task detail 对 fact 的暴露

验收标准：

- 任意 run 都能解释“为什么这样路由”
- 任意失败都能解释“为什么这样回退”
- 人工接管和自动决策边界清晰
- 后续 schema 演进不会污染历史 run

---

## Package N：统一告警中心

目标：

- 把当前 dashboard 中的 `prepared_alerts` 升级为正式告警对象
- 让 SLA、安全、调度异常形成统一告警闭环

范围：

- `backend/app/services/dashboard_service.py`
- `backend/app/services/security_service.py`
- `backend/app/api/routes/`
- `reception/app/dashboard/`
- `reception/app/security/`

任务：

- [x] 定义 `alert` schema
- [x] 定义告警状态：`open / acknowledged / resolved / suppressed`
- [x] 定义告警等级：`info / warning / critical`
- [x] 定义告警来源：`sla / workflow / security / delivery / integration`
- [x] 把 prepared alerts 持久化为正式 alert
- [x] 增加告警去重键与聚合策略
- [x] 增加静默窗口 / 抑制策略
- [x] 增加站内告警列表
- [x] 增加告警确认 / 关闭接口
- [x] 增加告警外发准备字段（钉钉 / 企微 / Telegram）

验收标准：

- 超时率、失败率、安全高风险率异常时会正式开告警
- 相同异常不会无限刷屏
- 告警有生命周期，不是一次性消息
- 运维能看见哪些告警未处理

---

## Package O：主脑控制面审批链

目标：

- 把高风险动作纳入统一审批流
- 不允许关键动作绕过主脑审批直接执行

范围：

- `backend/app/api/routes/settings.py`
- `backend/app/api/routes/security.py`
- `backend/app/api/routes/workflows.py`
- `backend/app/services/security_service.py`
- `backend/app/services/control_plane_audit_service.py`
- `reception/app/settings/`
- `reception/app/security/`

任务：

- [x] 定义审批单 schema
- [x] 定义审批状态：`pending / approved / rejected / expired / cancelled`
- [x] 定义审批动作类型：配置变更 / 安全放行 / 人工接管 / 外接能力放行
- [x] 定义审批人角色约束
- [x] 为高风险配置变更接入审批
- [x] 为安全策略放行接入审批
- [x] 为人工接管 / 手动回退接入审批
- [x] 增加审批审计日志
- [x] 前端增加审批中心页面

验收标准：

- 高风险动作全部有审批记录
- 非授权用户不能直接放行关键动作
- 审批结果可追溯到人、时间、理由

---

## Package P：NATS 事件协议落库与回放

目标：

- 把主脑内部事件从“只传输”升级为“可回放、可补偿、可追责”
- 为故障恢复和审计复盘提供基础设施

范围：

- `backend/app/core/nats_event_bus.py`
- `backend/app/core/event_protocol.py`
- `backend/app/core/event_subjects.py`
- `backend/app/core/event_types.py`
- `backend/app/services/internal_event_delivery_poller_service.py`
- `backend/app/services/workflow_realtime_service.py`

任务：

- [x] 定义统一事件 envelope
- [x] 区分 `command / event / audit / realtime`
- [x] 增加事件版本字段
- [x] 增加 trace_id / causation_id / correlation_id
- [x] 增加事件持久化
- [x] 增加死信事件存储
- [x] 增加事件重放接口
- [x] 增加 replay 审计
- [x] 增加事件协议一致性测试

验收标准：

- 主脑关键事件可落库
- 失败事件能重放
- 任意事件都能追踪上下游关系

---

## Package Q：外接触手正式接入协议 v1

目标：

- 为独立服务器部署的 Agent / Skill / MCP 建立统一接入协议
- 让主脑可以稳定发现、鉴权、心跳、摘除和熔断外接能力

范围：

- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/external_skill_registry_service.py`
- `backend/app/services/tool_source_service.py`
- `backend/app/services/master_bot_service.py`
- `/Users/xiaoyuge/Documents/XXL_ExternalConnection`

任务：

- [x] 定义统一注册协议 v1
- [x] 定义统一能力声明 contract
- [x] 增加外接实例心跳协议
- [x] 增加鉴权签名 / token 校验
- [x] 增加离线摘除策略
- [x] 增加熔断与恢复策略
- [x] 增加网络失败退避策略
- [x] 增加外接能力健康页
- [x] 增加桥接兼容测试

验收标准：

- 外接能力独立部署后仍能被主脑稳定治理
- 不健康能力不会被持续错误调度
- 外接实例上下线可观察、可审计

---

## Package R：多租户与环境隔离

目标：

- 为后续团队化、环境化、生产化使用建立隔离边界
- 防止不同租户、项目、环境互相污染

范围：

- `backend/app/services/`
- `backend/app/schemas/`
- `backend/app/api/routes/`
- `reception/app/`

任务：

- [x] 定义 tenant / project / environment 标识
- [x] 给任务、run、告警、审计增加隔离字段
- [x] 区分 `dev / staging / prod` 配置域
- [x] 区分租户级权限与全局权限
- [x] 区分租户级记忆与全局记忆
- [x] 增加跨租户访问拦截
- [x] 增加环境隔离测试

验收标准：

- 不同租户看不到彼此任务和告警
- 不同环境配置不会串用
- 审计日志能标清租户和环境归属

---

## Package S：记忆系统治理

目标：

- 让三层记忆真正可控、可追责、可回收
- 防止外接触手污染主脑记忆真源

范围：

- `backend/app/services/memory_service.py`
- `backend/app/services/document_search_service.py`
- `backend/app/services/workflow_execution_service.py`

任务：

- [x] 区分事实记忆 / 工作记忆 / 对话记忆
- [x] 定义记忆生命周期策略
- [x] 增加记忆写入来源标记
- [x] 增加记忆可信级别
- [x] 增加记忆淘汰 / 压缩 / 归档
- [x] 增加记忆删除与纠错流程
- [x] 增加外接写入边界
- [x] 增加记忆审计视图

验收标准：

- 记忆来源可追踪
- 错误记忆可纠正
- 外接触手不能直接污染长期真源

---

## Package T：运行压测与故障演练

目标：

- 让主脑知道自己的容量边界和故障退化路径
- 在上线前发现真实瓶颈

范围：

- `backend/tests/`
- `backend/scripts/`
- `docker-compose.yml`

任务：

- [x] 增加并发消息压测脚本
- [x] 增加超时与重试场景压测
- [x] 增加外接离线演练
- [x] 增加 NATS 堵塞演练
- [x] 增加数据库慢查询演练
- [x] 增加安全高压场景演练
- [x] 记录基线指标
- [x] 输出故障演练报告

验收标准：

- 知道主脑的容量上限
- 知道外接离线时系统如何退化
- 知道性能瓶颈在什么层

---

## Package U：发布与回滚体系

目标：

- 让主脑具备安全升级与快速回退能力
- 避免生产演进靠人工硬修

范围：

- `backend/alembic/`
- `backend/app/config.py`
- `docker-compose.yml`
- `run-full.sh`

任务：

- [x] 定义 schema migration 发布顺序
- [x] 增加配置变更回滚方案
- [x] 增加前后端版本兼容检查
- [x] 增加外接协议兼容检查
- [x] 增加灰度发布策略
- [x] 增加回滚演练脚本
- [x] 增加发布前检查清单

验收标准：

- 升级失败可快速回滚
- 配置错误不会直接污染生产
- 外接协议升级不会悄悄打崩主脑

---

## 推荐开发顺序

最快最全的顺序：

1. `Package S` 记忆系统治理
2. `Package T` 运行压测与故障演练
3. `Package U` 发布与回滚体系

---

## 当前建议

下一步最建议直接开始 `Package S`。

原因：

- 多租户读隔离和控制面隔离已经有骨架，下一阶段风险转到记忆真源
- 现在三层记忆还没有正式区分 tenant 级与全局级写入边界，外接触手仍可能污染长期真源
- 记忆治理做完后，压测、发布和回滚体系才有稳定的生产约束
