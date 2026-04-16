# MEMORY_GOVERNANCE

本文件定义主脑记忆治理的上线口径，用于约束三层记忆写入、作用域隔离、生命周期与审计验收。

## 1. 三层记忆写入标准

- `short_term`（短期）
- 写入对象：原始对话消息与最近上下文。
- 允许来源：主脑内部链路、受控接入层。
- 存储特性：高频读写，短 TTL，不作为长期事实真源。

- `mid_term`（中期）
- 写入对象：会话摘要、阶段性提炼结果。
- 允许来源：主脑蒸馏链路（`distill`）与人工审核修订。
- 约束：不可由外接 Agent / Skill 直接写入。

- `long_term`（长期）
- 写入对象：可复用事实、稳定偏好、结构化结论。
- 允许来源：主脑蒸馏链路、审核通过后的修正写回。
- 约束：不可由外接 Agent / Skill 直接写入；必须带作用域与生命周期元数据。

当前长期记忆白名单（canonical）：

- `session_summary`
- `user_preference`
- `agent_decision`
- `task_result`
- `event_digest`

约束：

- 新增长期记忆类型前，必须先扩白名单、补 retention/layer/scope 规则、补回归测试。
- 外接 `Agent / Skill` 仍禁止直接写入中长期记忆；长期记忆白名单当前只允许 `distillation` 写入。

## 2. 敏感字段脱敏规则

- 记忆系统遵循“先网关脱敏，再进入记忆写链路”。
- 涉及邮箱、银行卡等 PII 的文本，必须在安全网关层完成脱敏（如 `REDACTED_*`）。
- 未经脱敏的数据不得进入中长期记忆。

当前状态：

- 已有自动化验证安全网关脱敏规则生效与持久化优先级读取（见测试清单）。
- 记忆治理文档层已明确“脱敏前置”为强约束。

## 3. 仅本地保留，不进入长期记忆

以下上下文默认归类为“仅本地保留”：

- 一次性凭据：密码、验证码、短期 token、会话密钥。
- 高风险身份信息：完整证件号、银行卡全号、私钥、助记词。
- 临时调试上下文：仅用于当前任务排障的瞬时日志片段。

治理要求：

- 可存在于短期上下文用于当前轮推理。
- 不允许沉淀到 `long_term`。
- 需要在蒸馏阶段显式过滤并记录拒绝原因（审计字段）。

当前状态：

- 规则已明确并纳入上线口径。
- `local_only_reasons` / `local_only_filtered_count` 已纳入 memory schema 与 sqlite 真源字段，用于审计留痕。
- 蒸馏阶段已落地“命中 local-only 后不得进入 long_term”的硬过滤；对混合消息按片段过滤，仅保留可长期化部分。
- 该规则进入持续守卫阶段，后续新增 local-only 类型时需同步补回归测试。

当前 local-only 原因码：

- `credential_api_key`
- `credential_bot_token`
- `credential_bearer_token`
- `credential_secret_assignment`
- `credential_otp`
- `credential_password`
- `credential_session_secret`
- `pii_cn_id_card`
- `financial_bank_card`
- `secret_private_key`
- `secret_mnemonic`
- `debug_log_fragment`

## 4. 租户隔离（tenant/project/environment）

- 记忆读写必须同时携带 `tenant_id`、`project_id`、`environment`。
- 召回结果必须按三元组过滤，禁止跨租户、跨项目、跨环境泄露。
- 支持 `tenant` 与 `global` 记忆域；`global` 仅用于可共享基线知识。

## 5. 生命周期策略

- 记忆状态：`active` / `archived` / `deleted`。
- 支持审核流：`pending` -> `approved` / `corrected` / `deleted`。
- 支持过期归档：到期后自动从可召回集合中移除并归档。
- 长期记忆必须包含 `expires_at`、`archived_at` 等生命周期字段。

## 6. 现有自动化校验

- 记忆治理主用例：
- `backend/tests/test_memory_governance.py`
- 覆盖外部写入限制、作用域隔离、global/tenant 记忆域、审核流程、生命周期归档、路由层 scope 校验。
- 新增 local-only 回归：命中本地保留内容后不得进入长期记忆，且 `distill` 返回 local-only 过滤原因/计数。

- 三层记忆与蒸馏流程：
- `backend/tests/test_memory.py`
- 覆盖短中长期蒸馏、检索、会话滚动蒸馏、持久化状态恢复。

- 多租户隔离：
- `backend/tests/test_tenancy_isolation.py`
- 覆盖 tenant/project/environment 三元组隔离与跨域拒绝。

- 脱敏前置链路：
- `backend/tests/test_database_priority_reads.py`
- 覆盖安全网关脱敏规则、数据库优先读取与脱敏结果稳定性。

- 记忆治理仓内验收脚本：
- `backend/scripts/check_memory_governance.py`
- 输出长期记忆白名单、local-only 原因码、external write block、tenant/global 隔离、生命周期归档等仓内基线校验结果。

- 仓内校准样本：
- `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`
- 固化“允许沉淀 / local-only 过滤 / 作用域隔离 / 生命周期归档”样本，便于继续扩规则时做对照。

## 7. Package E 落地状态（2026-04-15）

- 已落地：
- 三层记忆模型与蒸馏链路。
- tenant/project/environment 隔离与检索过滤。
- global/tenant 记忆域区分。
- 生命周期归档与审核流。
- 外部 Agent/Skill 对中长期写入限制。
- local-only 片段级硬过滤与审计字段回传。

- 持续收口项：
- 脱敏前置与记忆蒸馏链路之间的联动回归可继续增加专项用例。
- 新增 local-only 类型时需同步扩展规则表与回归测试，避免规则漂移。
- 真实业务样本的人工抽样校准仍需在上线窗口补做，当前仓内脚本与样本仅覆盖基线能力，不替代真实业务复核。
