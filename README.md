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
```

## 当前状态

- 当前仓库保留主运行链、模块化后端结构和多实例运行入口。
- 兼容层冻结边界与记忆治理仓内校准仍保留：`check_compatibility_boundaries.py --strict` 会阻止 legacy alias 回流，`check_memory_governance.py --strict` 会输出长期记忆白名单、local-only 过滤、tenant/global 隔离和生命周期校验结果。
- 监控 compose、多实例 compose 和主运行脚本仍保留，用于当前接待层 / 调度层的继续开发。

## 参考文档

- `docs/brain/BRAIN_CORE_STATUS.md`
- `docs/brain/BRAIN_PRELAUNCH_TODO.md`
- `docs/brain/BRAIN_DUAL_REPO_STARTUP.md`
- `docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`
- `docs/brain/MEMORY_GOVERNANCE.md`
- `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`
- `REMAINING_DEVELOPMENT_CHECKLIST.md`
- `REMAINING_DEVELOPMENT_EXECUTION_PLAN.md`
