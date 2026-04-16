# Brain 多实例验收说明

更新时间：2026-04-16

## 目标

- 在同一 PostgreSQL / Redis / NATS 真源下，同时拉起多实例 dispatcher / workflow worker / agent worker
- 为正式联调和故障恢复演练提供统一启动方式与操作口径

## 相关文件

- `deploy/multi-instance/docker-compose.multi-instance.yml`
- `deploy/multi-instance/.env.multi-instance.example`
- `backend/scripts/run_dispatcher_runtime.py`
- `backend/scripts/run_workflow_execution_worker_runtime.py`
- `backend/scripts/run_agent_execution_worker_runtime.py`
- `run-multi-instance-acceptance.sh`

## 启动方式

```bash
cp .env.example .env
./run-multi-instance-acceptance.sh
```

这会在基础主脑服务之外，再拉起：

- `dispatcher-a`
- `dispatcher-b`
- `workflow-worker-a`
- `workflow-worker-b`
- `agent-worker-a`
- `agent-worker-b`

如需自定义实例 ID / 轮询参数，可参考：

- `deploy/multi-instance/.env.multi-instance.example`

## 推荐联调顺序

1. 先确认 `./run-brain.sh` 可正常启动
2. 再执行 `./run-multi-instance-acceptance.sh`
3. 执行以下检查：

```bash
python3 backend/scripts/check_production_env_contract.py --strict
python3 backend/scripts/check_persistence_contract.py --strict
python3 backend/scripts/check_scheduler_startup.py
python3 backend/scripts/check_scheduler_runtime_pg_acceptance.py --database-url <postgres_dsn> --strict
python3 backend/scripts/check_nats_contract.py --strict
python3 backend/scripts/check_nats_roundtrip.py --nats-url <nats_url> --strict
python3 backend/scripts/check_brain_prelaunch.py --strict-production
```

## 故障演练建议

- 强制停止一个 dispatcher，观察 claim reclaim 与 repair
- 强制停止一个 workflow worker，观察 execution lease takeover
- 强制停止一个 agent worker，观察 agent execution reclaim

建议同时留存：

- `docker compose ps`
- `docker compose logs dispatcher-a dispatcher-b workflow-worker-a workflow-worker-b agent-worker-a agent-worker-b`
- 上述检查脚本输出 JSON

## 当前边界

- 仓库内的多实例运行入口、compose 和 runner 脚本已经齐备
- 真实生产拓扑下的正式联调记录、故障恢复证据，仍需在真实 PostgreSQL / NATS 环境执行并归档
