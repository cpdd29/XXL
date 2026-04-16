# Package U Release Playbook

## Migration Order

1. 先执行发布预检：`./check-release-preflight.sh --strict`
   该命令会在 `workbot-backend` 容器内执行，并自动附带 live DB migration 校验
2. 快照当前配置与编排：`bash backend/scripts/release_snapshot_and_rollback.sh snapshot`
3. 拉起依赖但不切流量：`docker compose up -d postgres redis nats chromadb`
4. 执行 schema migration：`cd backend && alembic upgrade head`
   即使手动漏执行，compose 内 backend 也会在启动前再次执行 `alembic upgrade head`
5. 启动后端并验证协议兼容、健康页、控制面登录
6. 启动前端并验证版本矩阵与关键页
7. 灰度阶段只让单租户或单渠道流量进入新版本
8. 执行发布后运行态验收：`./check-release-runtime.sh --scenario postdeploy --require-control-plane --require-production-ready --strict`
9. 观察无异常后再全量切换

## Rollback Strategy

- 配置回滚：恢复 `.env`、`backend/.env` 与 compose 快照
- 应用回滚：恢复上一个镜像/tag 或上一个工作树提交
- 数据回滚：仅在 migration 明确支持 downgrade 时执行 `alembic downgrade -1`
- 协议回滚：外接 Agent/Skill 兼容矩阵必须保持 `brain-core-v1`
- 回滚后运行态验收：`./check-release-runtime.sh --scenario rollback --require-control-plane --require-production-ready --strict`

## Gray Release

- 第一阶段：单租户 `tenant-alpha`
- 第二阶段：单渠道 `telegram`
- 第三阶段：10% 人工选流量
- 第四阶段：全量

## Preflight Checklist

- Alembic revision 链单头、无断链
- 当前 live DB 已到 migration head
- Docker Compose 关键依赖存在且具备健康检查
- backend 启动命令包含 `alembic upgrade head`
- 前端版本、Agent 协议版本、外接兼容版本已记录
- `release_preflight` 已确认 Package A / D / E 正式验收模板存在：`backend/docs/PACKAGE_A_MULTI_INSTANCE_ACCEPTANCE_TEMPLATE.md`、`backend/docs/PACKAGE_D_EXTERNAL_ACCEPTANCE_TEMPLATE.md`、`backend/docs/PACKAGE_E_SECURITY_ACCEPTANCE_TEMPLATE.md`
- formal DR 结果包已生成并归档：`python3 backend/scripts/package_dr_result_bundle.py --orchestrate --exercise-id <exercise_id> --strict`
- 调度运行态 PG 验收已通过：`python3 backend/scripts/check_scheduler_runtime_pg_acceptance.py --database-url <postgres_dsn> --strict`
- NATS roundtrip / queue-group / command-event 过滤验收已通过：`python3 backend/scripts/check_nats_roundtrip.py --nats-url <nats_url> --strict`
- 配置快照已生成
- 回滚路径已演练

## Runtime Verification

发布后 / 回滚后 / 恢复后，建议分别执行：

```bash
./check-release-runtime.sh --scenario postdeploy --require-control-plane --require-production-ready --strict
./check-release-runtime.sh --scenario rollback --require-control-plane --require-production-ready --strict
./check-release-runtime.sh --scenario recovery --require-control-plane --require-production-ready --strict
```

也可以直接在本地 Python 环境运行：

```bash
python3 backend/scripts/check_release_runtime.py \
  --scenario all \
  --backend-base-url http://127.0.0.1:8080 \
  --access-token <operator_token> \
  --require-control-plane \
  --require-production-ready \
  --strict
```

运行态验收会统一检查：

- `release_preflight`
- `brain_prelaunch`
- `/health` 与控制面关键接口可达性
- rollback 场景下的快照可恢复性
- recovery 场景下的外接触手恢复状态
- recovery 场景下的记忆治理稳定性

## Unified Evidence Bundle

建议在上线窗口统一执行一次：

```bash
python3 backend/scripts/package_release_evidence_bundle.py \
  --backend-base-url http://127.0.0.1:8080 \
  --access-token <operator_token> \
  --metrics-token "$WORKBOT_METRICS_SCRAPE_TOKEN" \
  --include-dr-bundle \
  --strict
```

如果主脑以 Docker 方式运行，也可以直接使用：

```bash
./package-release-evidence.sh --strict
```

该总包会统一归档：

- `release_preflight`
- `brain_prelaunch`
- `compatibility_boundaries`
- `memory_governance`
- `release_runtime`
- `monitoring_alerting`
- `external_tentacles`
- `security_acceptance`
- `dr_bundle`（启用时）
