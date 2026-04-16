# DR Drill Result Template

适用脚本：

- `backend/scripts/dr_precheck.py`
- `backend/scripts/failover_prepare.py`
- `backend/scripts/post_failover_verify.py`
- `backend/scripts/external_tentacle_recovery.py`

## 1. 结果字段

- `drill_name`: 演练名称
- `scenario`: 演练场景
- `generated_at`: 报告生成时间
- `objectives`: RTO / RPO 目标
- `timeline.failover_started_at`: 故障切换起点
- `timeline.verified_at`: 验证完成时间
- `baseline.truth_sources`: 切换前 `task/run/audit/security` 基线
- `baseline.external_manifest`: 切换前外接 Agent / Skill 注册清单
- `post_state.truth_sources`: 切换后真源状态
- `post_state.external_manifest`: 切换后触手恢复状态
- `checks`: 检查项结果
- `failed_steps`: 失败步骤列表
- `evidence.drill_kind`: `formal / smoke`
- `evidence.evidence_level`: 证据完整度标记（如 `full / precheck / smoke`）
- `evidence.operator_notes`: 值班/演练人员备注
- `measurements.rto_seconds`: 主脑切换实际 RTO
- `measurements.external_recovery_rto_seconds`: 外接触手恢复实际 RTO
- `measurements.estimated_rpo_seconds`: 估算 RPO
- `measurements.estimated_lost_records`: 估算丢失记录数
- `status`: `pending / prepared / passed / failed / blocked`

## 2. JSON Skeleton

```json
{
  "drill_name": "brain_failover_drill",
  "scenario": "level2_brain_failover",
  "generated_at": "2026-04-15T00:00:00+00:00",
  "objectives": {
    "brain_api_failover_rto_seconds": 300,
    "external_reregistration_rto_seconds": 600,
    "observability_restore_rto_seconds": 600,
    "truth_source_rpo_seconds": 60,
    "audit_rpo_seconds": 0
  },
  "timeline": {
    "failover_started_at": "2026-04-15T00:00:00+00:00",
    "verified_at": "2026-04-15T00:05:00+00:00"
  },
  "baseline": {
    "truth_sources": {},
    "external_manifest": {}
  },
  "post_state": {
    "truth_sources": {},
    "external_manifest": {}
  },
  "checks": [],
  "failed_steps": [],
  "evidence": {
    "drill_kind": "formal",
    "evidence_level": "full",
    "operator_notes": ""
  },
  "measurements": {
    "rto_seconds": 300,
    "external_recovery_rto_seconds": 420,
    "estimated_rpo_seconds": 0,
    "estimated_lost_records": 0
  },
  "status": "passed"
}
```

## 3. 推荐执行顺序

1. 先执行 `dr_precheck.py`，确认 runbook、模板、真源快照、外接清单都可读取。
2. 执行 `failover_prepare.py`，冻结前抓取标准基线。
3. 完成人工切换动作。
4. 执行 `post_failover_verify.py`，验证主脑真源连续性。
5. 执行 `external_tentacle_recovery.py`，验证外接触手回连与恢复。
6. 执行 `dr_result_gate.py --strict`，校验正式结果包门禁。

## 4. 正式结果包（formal）产物规范

正式生产验收时，必须归档以下结果包到同一证据目录（示例：`backend/docs/dr_formal_bundle/`）：

- `dr_precheck_*.json` + `dr_precheck_*.md`
- `failover_prepare_*.json` + `failover_prepare_*.md`
- `post_failover_verify_*.json` + `post_failover_verify_*.md`
- `external_tentacle_recovery_*.json` + `external_tentacle_recovery_*.md`
- `dr_result_gate_formal_*.json` + `dr_result_gate_formal_*.md`

正式门禁要求：

- `dr_result_gate_formal` 报告必须 `status=passed`。
- `formal_drill_kind_required` 检查项必须通过，且四份核心报告的 `evidence.drill_kind` 全部为 `formal`。
- 四份核心报告必须包含 `gate_stats.failed` 与 `gate_stats.manual_intervention`。
- `post_failover_verify` 必须包含 `measurements.rto_seconds` 与 `measurements.estimated_rpo_seconds`。

正式打包命令（示例）：

- 生成并归档正式证据包：`python3 backend/scripts/package_dr_result_bundle.py --exercise-id <exercise_id> --archive-dir backend/docs/dr_formal_bundle --strict`
- 归档目录将至少包含 10 个核心文件：四份核心报告与 `dr_result_gate_formal` 的 `.json + .md`
- 脚本还会额外生成 `dr_result_bundle_formal_*.json + .md` 与 `archive_manifest.json + .md`

上线口径：

- `smoke` 报告只能用于烟雾演练和联调，不得作为正式生产上线证据。
- 使用 `--allow-smoke` 通过门禁时，结果仅可标记为“非正式演练通过”，不得标记为“正式上线验收通过”。
