# 主脑 / 触手跨机房容灾预案

更新时间：2026-04-15
适用范围：`XXL` 本地主脑、`XXL_ExternalConnection` 外接 Agent / Skill / MCP、NATS 基础链路、主脑真源数据库与审计链路。

## 1. 容灾红线

必须保留在主脑机房并做真源复制的对象：

- `task` 真源
- `workflow_run` / `step` 真源
- `manager_packet`
- `brain_dispatch_summary`
- `execution_plan_snapshot`
- 安全策略与处罚状态
- 审计日志
- 记忆真源
- 外接能力注册中心状态

可以在切换后重新注册或重建的对象：

- 外接 Agent Worker 在线实例
- 外接 Skill 服务在线实例
- MCP Runtime 实例
- 各类浏览器 / 搜索 / 文档处理执行节点

结论：

- 主脑必须做“同构双机房，真源复制，单主裁决”
- 触手可以做“多机房多实例，重新注册即可恢复”
- 禁止把主脑裁决权下放给任一触手机房

## 2. 推荐拓扑

推荐模式：`主脑单主 + 异地热备 + 触手多活`

拓扑拆分：

- `AZ-A / IDC-A`
  - Active Brain
  - 主数据库 Primary
  - NATS Primary
  - 安全网关与接入层
- `AZ-B / IDC-B`
  - Standby Brain
  - 主数据库 Replica / 可提升
  - NATS Standby
  - 只读健康探针与冷启动控制面
- `External Tentacles`
  - Agent / Skill / MCP 可同时部署在 A/B
  - 统一回连主脑注册中心

## 3. RTO / RPO 目标

- 主脑 API 故障切换：RTO `<= 5 min`
- 外接触手重注册恢复：RTO `<= 10 min`
- 主脑真源数据恢复点：RPO `<= 1 min`
- 审计与安全处罚数据：RPO `0` 为目标，至少保证同步落盘后放行
- 协作页 / 仪表盘观测恢复：RTO `<= 10 min`

## 4. 数据分级与复制要求

### P0 必须实时复制

- `tasks`
- `workflow_runs`
- `task_steps`
- `audit_logs`
- `security penalties / incidents`
- `system_settings`
- `memory` 长短期真源
- `external registry state`

要求：

- 数据库主从复制或双写日志复制
- 审计日志追加后再返回关键操作成功
- 安全处罚状态禁止只存在内存

### P1 可短时回放恢复

- dashboard 聚合缓存
- collaboration 只读快照缓存
- 非关键实时日志流

要求：

- 允许通过数据库真源重算
- 不作为切换阻塞项

### P2 可重新生成

- 外接触手在线连接状态
- MCP 工具探活缓存
- 前端本地缓存

要求：

- 切换后通过心跳与注册重新建立

## 5. 故障分级与动作

### Level 1：触手局部机房故障

表现：

- 单个外接 Agent / Skill / MCP 机房不可达
- 主脑正常

动作：

- 主脑依赖心跳 / circuit breaker 摘除故障实例
- 版本治理层按 fallback 版本或稳定版本回退
- 并发编排自动收缩为可用分支

不做：

- 不切主脑
- 不切数据库主

### Level 2：主脑所在机房网络异常，但数据库仍可提升

表现：

- 接入层、主脑 API、NATS 主实例不可用
- 异地副本健康

动作：

1. 冻结旧主脑入口，停止新的入站流量
2. 提升异地数据库副本
3. 启动 Standby Brain 为 Active Brain
4. 切换 API / Webhook / 控制台入口到备用机房
5. 触发外接触手重新注册与心跳恢复
6. 校验 `task/run/audit/security` 真源完整性

### Level 3：数据库损坏或双机房链路分裂

表现：

- 真源不可确认
- 可能出现脑裂

动作：

1. 立即停止双侧写入
2. 以最后一致审计点选定唯一主真源
3. 从审计日志与 run 真源回放恢复
4. 只读开放控制台，禁止继续调度
5. 恢复后再放开消息入口

红线：

- 脑裂状态下禁止双主继续接单

## 6. 切换顺序

必须按顺序执行：

1. 冻结入站
2. 确认旧主失效
3. 提升数据库真源
4. 提升主脑控制面
5. 恢复 NATS
6. 恢复外接注册中心
7. 触手重新注册
8. 恢复消息入口
9. 校验协作页 / 审计 / 安全中心

## 7. 降级策略

切换期间允许的降级：

- 暂停多触手并发，退回单触手稳定版本
- 暂停 canary，全部切到 stable
- 暂停高风险自动放行，只保留人工审批
- 暂停非关键 dashboard 实时推送，保留只读快照

切换期间禁止的降级：

- 禁止绕过安全网关
- 禁止关闭审计
- 禁止把裁决逻辑下放到触手

## 8. 脚本化映射

标准入口：

- 预检：`python3 backend/scripts/dr_precheck.py --strict`
- 切换前基线：`python3 backend/scripts/failover_prepare.py --strict`
- 切换后真源校验：`python3 backend/scripts/post_failover_verify.py --baseline-report <failover_prepare.json> --strict`
- 外接触手恢复校验：`python3 backend/scripts/external_tentacle_recovery.py --baseline-report <failover_prepare.json> --strict`
- DR 结果门禁：`python3 backend/scripts/dr_result_gate.py --strict`
  - 仅 smoke 包验收时：`python3 backend/scripts/dr_result_gate.py --strict --allow-smoke`

正式结果包打包命令（formal）：

- 生成四份正式结果报告：`python3 backend/scripts/dr_precheck.py --strict`
- 生成切换前基线：`python3 backend/scripts/failover_prepare.py --strict`
- 生成切换后真源校验：`python3 backend/scripts/post_failover_verify.py --strict`
- 生成外接触手恢复校验：`python3 backend/scripts/external_tentacle_recovery.py --strict`
- 生成并归档正式证据包：`python3 backend/scripts/package_dr_result_bundle.py --exercise-id <exercise_id> --archive-dir backend/docs/dr_formal_bundle --strict`

正式产物说明：

- `backend/docs/dr_formal_bundle/<exercise_id>/` 至少包含 10 个核心文件：`dr_precheck`、`failover_prepare`、`post_failover_verify`、`external_tentacle_recovery`、`dr_result_gate_formal` 的 `.json + .md`。
- `package_dr_result_bundle.py` 还会额外归档 `dr_result_bundle_formal` 的 `.json + .md`，并生成 `archive_manifest.json + archive_manifest.md`。
- `dr_result_gate_formal` 必须 `status=passed` 且检查项 `formal_drill_kind_required=ok`。
- 任何 `smoke` 报告都不能作为正式生产上线证据；`--allow-smoke` 仅用于烟雾演练或本地联调。

步骤映射：

1. 冻结入站
   对应：`failover_prepare.py`
   输出：冻结前标准基线与待执行步骤清单
2. 确认旧主失效
   对应：Runbook 人工门禁
   说明：记录故障开始时间，作为后续 `RTO` 计算起点
3. 提升数据库真源
   对应：Runbook 人工门禁
   说明：以数据库为 `task/run/audit/security` 唯一真源
4. 提升主脑控制面
   对应：Runbook 人工门禁
   说明：恢复单主裁决权
5. 恢复 NATS
   对应：`post_failover_verify.py`
   检查项：`nats_or_fallback_ready`
6. 恢复外接注册中心
   对应：`external_tentacle_recovery.py`
   检查项：`registry_inventory_loaded`
7. 触手重新注册
   对应：`external_tentacle_recovery.py`
   检查项：`family_recovered`、`stale_heartbeats_cleared`、`open_circuits_cleared`
8. 恢复消息入口
   对应：人工放行
   前置：`post_failover_verify.py` 与 `external_tentacle_recovery.py` 均通过
9. 校验协作页 / 审计 / 安全中心
   对应：`post_failover_verify.py`
   检查项：`task_truth_continuity`、`run_truth_continuity`、`audit_truth_continuity`、`security_truth_continuity`

结果模板：

- 统一采用 [`backend/docs/dr_drill_result_template.md`](backend/docs/dr_drill_result_template.md)
- 每次演练都必须输出 `.json + .md` 两份结果
- 正式上线验收必须额外归档 `dr_formal_bundle/<exercise_id>/` 证据包；仅有单份 smoke 报告或仅有门禁脚本执行记录都不算完成

## 9. 演练清单

每月至少一次：

- 断开单个 Agent 机房，验证摘除与 fallback
- 停掉主脑机房 API，验证 Standby 提升
- 模拟 NATS 故障，验证主脑本地真源不丢
- 模拟数据库主从切换，验证 `task/run/audit` 连续性
- 模拟 canary 版本异常，验证一键 rollback

每次演练必须记录：

- 开始时间
- 触发原因
- 切换耗时
- RTO / RPO 实际值
- 失败步骤
- 后续修复项

## 10. 验收标准

- 单个触手机房故障不会导致主脑失控
- 主脑机房切换后，`task/run/audit/security` 真源连续
- 外接能力可在备用机房 10 分钟内重新注册恢复
- 所有切换动作都有审计记录
- 任意时刻都只有一个主脑拥有最终裁决权
