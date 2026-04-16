# Brain Security Gate Checklist

更新时间：2026-04-15

目标：

- 给主脑上线前的安全验收提供一份可执行、可留痕、可复跑的门禁清单
- 明确哪些检查已经自动化，哪些仍需要上线窗口中的人工核验

适用范围：

- 本地主脑可信区
- 主消息入口、Webhook 入口、安全网关、审计链、记忆写入路径

---

## 1. 自动化门禁

上线前必须执行以下命令：

```bash
cd /Users/xiaoyuge/Documents/XXL
python3 backend/scripts/check_security_entrypoints.py --strict
python3 backend/scripts/check_security_controls.py --strict
python3 backend/scripts/check_security_audit_persistence.py --strict
python3 backend/scripts/check_external_ingress_bypass.py --strict
python3 backend/scripts/check_brain_prelaunch.py
python3 backend/scripts/collect_security_acceptance_evidence.py --access-token <operator_token> --strict
```

### 1.1 `check_security_entrypoints.py --strict`

验证内容：

- `messages.ingest` 仍走统一消息接入链
- 通道 webhook 仍走限流、payload 大小控制、secret 校验
- `workflow_webhook_route` 仍走 `security_gateway_service.inspect_text_entrypoint(...)`

阻塞条件：

- 任一外部入口缺失安全检查调用
- `workflow webhook` 再次绕开统一安全网关

### 1.2 `check_security_controls.py --strict`

验证内容：

- 安全网关放行时仍会生成本地 trace / audit
- 敏感内容会被改写后再进入任务描述和短期记忆
- 提示注入消息会被主消息入口拦截，且不会创建 task / run / active task cache
- 非法 `auth scope` 会在消息入口被拦截，且不会继续写入记忆
- 限流会在真实消息入口链路生效
- `workflow webhook` 的高风险请求会被拦截，且不会进入编排

阻塞条件：

- 任一安全控制失效
- 敏感字段以原文进入任务或记忆
- 被拦截的请求仍产生编排副作用

### 1.3 `check_brain_prelaunch.py`

验证内容：

- 聚合主脑上线前严格门禁
- 包含 `security_entrypoint_coverage`
- 包含 `security_controls_ready`
- 包含 `security_audit_persistence_ready`
- 包含 `external_ingress_bypass_scan_ready`

判定口径：

- `production_ready=true` 才能进入正式上线窗口
- `degraded_startable` 仅代表可降级启动，不代表可正式上线

### 1.4 `check_security_audit_persistence.py --strict`

验证内容：

- 安全网关可产生 `allow / rewrite / block` 三类审计
- 审计会写入 `persistence_service` 真源，不是仅停留在 runtime store
- runtime 清空后仍可从 `list_audit_logs()` 回读审计
- 回读审计中保留关键 metadata 字段（`trace.trace_id`，以及 `prompt_injection_assessment` 或 `rewrite_diffs`）

阻塞条件：

- 三类审计缺失任一类
- 审计仅存在于 runtime，不存在于真源数据库
- 审计回读缺失关键 metadata 字段

### 1.5 `check_external_ingress_bypass.py --strict`

验证内容：

- 扫描 `messages ingress`、`webhooks`、`external_connections` 的外部入口
- 区分 `public_external_ingress` 与 `authenticated_control_plane`
- 对公开入口输出 protection summary（`secret/signature`、`rate_limit`、`payload_size`、`security_gateway`、`require_authenticated_user`）
- 输出 `manual_review_required` 供上线窗口复核

阻塞条件：

- 存在公开外部入口未命中任何 baseline protection（`failed_public_routes > 0`）

---

## 2. 人工核验项

以下内容仍需在上线窗口或联调环境中人工复核：

- 正式数据库真源下，审计日志是否完整落库
- 正式 NATS 下，安全相关事件与运行态告警是否可追踪
- 对外接 Adapter / 反向代理 / 网关层的真实来源 IP、Header 透传是否符合预期
- `manual_review_required` 列出的公开入口，需复核反向代理、Header 透传、token/signature 配置与轮换策略
- 安全策略变更后的审批、回滚、追溯流程是否可执行
- 安全处罚、解除处罚、事件复盘在控制面展示是否与真源一致
- 对审计真源做一次上线窗口抽样（allow/rewrite/block 各至少 1 条）并留档

---

## 3. 证据留存

上线验收时至少保留以下证据：

- `check_security_entrypoints.py` 输出 JSON
- `check_security_controls.py` 输出 JSON
- `check_security_audit_persistence.py` 输出 JSON
- `check_external_ingress_bypass.py` 输出 JSON
- `check_brain_prelaunch.py` 输出 JSON
- `collect_security_acceptance_evidence.py` 输出 JSON / Markdown bundle
- 一份真实环境下的安全审计样本
- 一份高风险拦截样本
- 一份敏感信息改写样本

---

## 4. 当前结论

当前仓库已经具备以下自动化安全门禁：

- 外部入口静态扫描
- 安全控制烟雾验收
- 审计真源落库与 metadata 保真验收
- 外部公开入口绕过扫描与人工复核清单
- 主消息入口高风险拦截无副作用校验
- workflow webhook 高风险拦截无副作用校验
- 脱敏内容进入任务/记忆前的改写校验

仍未完成的，是正式数据库、正式 NATS、真实部署链路下的生产环境验收。
