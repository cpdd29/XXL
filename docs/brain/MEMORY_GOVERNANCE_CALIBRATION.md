# Memory Governance Calibration

更新时间：2026-04-16

## 目标

- 固化一组仓库内可重复执行的记忆治理校准样本
- 把“长期记忆白名单、local-only 过滤、作用域隔离、生命周期归档”从规则描述变成可复核样本

## 校准样本

### 样本 1：长期偏好允许沉淀

- 输入：`请记住我每周三上午同步周报，偏好中文。`
- 预期：
- `user_preference` / `session_summary` 可进入长期记忆
- `memory_scope=tenant`
- 不产生 `local_only_reasons`

### 样本 2：调试密钥只允许本地保留

- 输入：`长期偏好：每周三上午同步周报。临时调试密钥 local-debug-secret-778899 仅本地排障使用`
- 预期：
- `每周三上午同步周报` 可进入长期记忆
- `local-debug-secret-778899` 不进入长期记忆
- `distill_audit.local_only_filtered_count >= 1`
- `local_only_reasons` 包含 `debug_log_fragment`

### 样本 3：跨租户不得召回 tenant 记忆

- Alpha scope：`tenant-alpha / project-a / prod`
- Beta scope：`tenant-beta / project-b / prod`
- 预期：
- Beta 无法召回 Alpha 的 tenant 记忆
- `scope_breakdown.tenant = 0`

### 样本 4：global 记忆允许跨租户共享

- 输入：`所有租户都需要遵守统一安全基线。`
- 预期：
- `memory_scope=global`
- 其他租户可召回
- 跨租户召回结果中 `scope_breakdown.global >= 1`

### 样本 5：过期长期记忆自动归档

- 前提：将某条长期记忆的 `expires_at` 调整到过去时间
- 预期：
- 执行 lifecycle 后 `archived_count = 1`
- 该条长期记忆 `memory_status=archived`

## 对应脚本

仓库内统一脚本：

```bash
python3 backend/scripts/check_memory_governance.py --strict
```

脚本输出包括：

- 长期记忆白名单快照
- local-only 原因码清单
- external skill / agent 写入限制
- tenant/global 作用域校验结果
- 生命周期归档校验结果

## 说明

- 本文档覆盖的是仓库内基线样本，不替代真实业务样本复核。
- 正式上线前，仍需要补一轮真实业务数据的人工抽样校准，重点复核：
- 召回质量是否满足业务预期
- 脱敏后文本是否仍保留足够业务语义
- 新增敏感模式是否需要加入 `local_only` 规则表
