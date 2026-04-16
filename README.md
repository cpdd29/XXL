# XXL / WorkBot Brain

`XXL` 是主脑仓，负责统一消息入口、安全网关、项目经理 / 路由 / 编排、三层记忆、控制面和本地主数据真源。  
外接 MCP / Agent / Skill 资产与触手服务在兄弟仓 `XXL_ExternalConnection` 中独立部署。

## 仓库结构

- `backend/`: FastAPI 主脑、控制面 API、调度与安全链路
- `reception/`: Next.js 控制面
- `deploy/external-registry/`: 主脑侧读取的 external registry 快照
- `deploy/multi-instance/`: 多实例 dispatcher / worker 验收 compose
- `deploy/monitoring/`: Prometheus / Grafana 监控接入模板
- `docs/brain/`: 主脑状态、上线前清单、双仓启动与验收文档

## 快速启动

先启动外接仓：

```bash
cd ../XXL_ExternalConnection
cp .env.example .env
./run-external.sh
```

再启动主脑仓：

```bash
cd ../XXL
cp .env.example .env
./run-brain.sh
```

默认入口：

- 前端：`http://127.0.0.1:3000`
- 后端：`http://127.0.0.1:8080`
- PostgreSQL：`127.0.0.1:5432`
- Redis：`127.0.0.1:6379`
- NATS：`127.0.0.1:4222`
- NATS Monitor：`http://127.0.0.1:8222`
- ChromaDB：`http://127.0.0.1:8000`

## 扩展启动模式

多实例验收环境：

```bash
./run-multi-instance-acceptance.sh
```

它会在基础主脑服务之外，再拉起：

- 2 个 dispatcher
- 2 个 workflow execution worker
- 2 个 agent execution worker

监控栈：

```bash
export WORKBOT_METRICS_SCRAPE_TOKEN=change-me
./run-monitoring-stack.sh
```

这会在主脑 compose 之外再拉起：

- Prometheus：`http://127.0.0.1:9090`
- Grafana：`http://127.0.0.1:3001`

`/api/dashboard/metrics` 现在支持两种抓取方式：

- 正常控制面 Bearer Token
- `X-WorkBot-Metrics-Token` / Bearer 形式的 `WORKBOT_METRICS_SCRAPE_TOKEN`

## 关键自检

```bash
python3 backend/scripts/check_production_env_contract.py --strict
python3 backend/scripts/check_persistence_contract.py --strict
python3 backend/scripts/check_scheduler_startup.py
python3 backend/scripts/check_scheduler_runtime_pg_acceptance.py --database-url <postgres_dsn> --strict
python3 backend/scripts/check_nats_contract.py --strict
python3 backend/scripts/check_nats_roundtrip.py --nats-url <nats_url> --strict
python3 backend/scripts/check_compatibility_boundaries.py --strict
python3 backend/scripts/check_memory_governance.py --strict
python3 backend/scripts/check_brain_prelaunch.py --strict-production
```

容器内真实环境检查：

```bash
./check-release-preflight.sh --strict
./check-brain-prelaunch.sh --strict-production
./check-release-runtime.sh --scenario postdeploy --require-control-plane --require-production-ready --strict
./package-release-evidence.sh --strict
```

## 证据采集

监控与告警证据：

```bash
python3 backend/scripts/collect_monitoring_alerting_evidence.py \
  --backend-base-url http://127.0.0.1:8080 \
  --metrics-token "$WORKBOT_METRICS_SCRAPE_TOKEN" \
  --email admin@workbot.ai \
  --password workbot123 \
  --strict
```

外接触手运维证据：

```bash
python3 backend/scripts/collect_external_tentacle_evidence.py \
  --backend-base-url http://127.0.0.1:8080 \
  --registry-path deploy/external-registry/workbot_external_sources.local.json \
  --access-token <operator_token> \
  --scan-sources \
  --strict
```

安全上线证据：

```bash
python3 backend/scripts/collect_security_acceptance_evidence.py \
  --backend-base-url http://127.0.0.1:8080 \
  --access-token <operator_token> \
  --strict
```

统一上线证据总包：

```bash
python3 backend/scripts/package_release_evidence_bundle.py \
  --backend-base-url http://127.0.0.1:8080 \
  --access-token <operator_token> \
  --metrics-token "$WORKBOT_METRICS_SCRAPE_TOKEN" \
  --include-dr-bundle \
  --strict
```

如果主脑已经在 Docker 中运行，也可以直接使用：

```bash
./package-release-evidence.sh --strict
```

发布后 / 回滚后 / 恢复后运行态验收：

```bash
python3 backend/scripts/check_release_runtime.py \
  --scenario all \
  --backend-base-url http://127.0.0.1:8080 \
  --access-token <operator_token> \
  --require-control-plane \
  --require-production-ready \
  --strict
```

如果主脑已经在 Docker 中运行，也可以直接使用：

```bash
./check-release-runtime.sh --scenario recovery --require-control-plane --require-production-ready --strict
```

## 当前状态

- 主脑研发主链已完成，`check-brain-prelaunch.sh --strict-production` 已具备通过路径。
- `Package A / C / D / E / H` 的仓库内交付已经补齐：多实例运行入口、监控 compose、外接/安全证据脚本、相关文档和部署模板都已落仓。
- 兼容层冻结边界与记忆治理仓内校准已补齐：`check_compatibility_boundaries.py --strict` 会阻止 legacy alias 回流，`check_memory_governance.py --strict` 会输出长期记忆白名单、local-only 过滤、tenant/global 隔离和生命周期校验结果。
- 已新增统一上线证据总包：`package_release_evidence_bundle.py` / `package-release-evidence.sh`，可把 preflight、prelaunch、兼容边界、记忆治理、监控、外接、安全、DR 证据统一归档。
- 已新增运行态验收脚本：`check_release_runtime.py` / `check-release-runtime.sh`，可在 `postdeploy / rollback / recovery` 三种场景下复跑主脑运行态检查并生成留档。
- 剩余未收口项，集中在真实生产资源执行：
  - 真实 PostgreSQL / NATS 拓扑下的多实例正式演练与留痕
  - 真实 Prometheus / Grafana / 企业通知凭证接入
  - 真实外接部署拓扑下的灰度 / 回滚 / recover 演练
  - 正式数据库与入口链路下的安全审计样本留档
  - formal DR 演练的持续复演与归档

## 参考文档

- `docs/brain/BRAIN_CORE_STATUS.md`
- `docs/brain/BRAIN_PRELAUNCH_TODO.md`
- `docs/brain/BRAIN_DUAL_REPO_STARTUP.md`
- `docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`
- `docs/brain/MEMORY_GOVERNANCE.md`
- `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`
- `REMAINING_DEVELOPMENT_CHECKLIST.md`
- `REMAINING_DEVELOPMENT_EXECUTION_PLAN.md`
