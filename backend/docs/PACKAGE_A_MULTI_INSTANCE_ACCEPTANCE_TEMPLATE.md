# Package A Multi-Instance Acceptance Template

更新时间：2026-04-16

用途：

- 正式 PostgreSQL / NATS 环境下的多实例联调记录
- dispatcher / workflow worker / agent worker 排他 claim 验收留痕
- stale reclaim / missing job repair / orphan repair / NATS 恢复场景归档

## 1. 基本信息

- 验收日期：
- 验收窗口：
- 环境名称：
- 验收负责人：
- 参与角色：
- exercise / change id：

## 2. 目标环境

- PostgreSQL DSN：
- NATS URL：
- Brain image / commit：
- External registry snapshot：
- dispatcher 实例数：
- workflow worker 实例数：
- agent worker 实例数：

## 3. 前置检查

- [ ] `python3 backend/scripts/check_production_env_contract.py --strict`
- [ ] `python3 backend/scripts/check_persistence_contract.py --strict`
- [ ] `python3 backend/scripts/check_scheduler_startup.py`
- [ ] `python3 backend/scripts/check_scheduler_runtime_pg_acceptance.py --database-url <postgres_dsn> --strict`
- [ ] `python3 backend/scripts/check_nats_contract.py --strict`
- [ ] `python3 backend/scripts/check_nats_roundtrip.py --nats-url <nats_url> --strict`

前置检查结果摘要：

```text
粘贴终端输出或报告文件路径
```

## 4. 多实例拓扑

| 组件 | 实例名 | 主机/IP | 版本 | 结果 |
| --- | --- | --- | --- | --- |
| dispatcher |  |  |  |  |
| workflow worker |  |  |  |  |
| agent worker |  |  |  |  |

## 5. 核心验收项

| 验收项 | 预期 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| dispatch claim 排他 | 单次只被一个 dispatcher 认领 |  |  |
| workflow execution claim 排他 | 单次只被一个 worker 认领 |  |  |
| agent execution claim 排他 | 单次只被一个 agent worker 认领 |  |  |
| stale lease reclaim | 过期租约能被接管 |  |  |
| missing execution job repair | 缺失 job 可自动修复 |  |  |
| orphan job repair | 孤儿 job 可被巡检并回收 |  |  |
| NATS 断连 fallback | 断连期间主链不失控 |  |  |
| NATS 恢复 | 恢复后事件链重新正常 |  |  |

## 6. 故障注入记录

| 场景 | 操作 | 恢复结果 | 恢复耗时 | 证据 |
| --- | --- | --- | --- | --- |
| 停 dispatcher-a |  |  |  |  |
| 停 workflow-worker-a |  |  |  |  |
| 停 agent-worker-a |  |  |  |  |
| 断 NATS |  |  |  |  |

## 7. 证据索引

- 调度运行日志：
- 运行截图：
- report JSON：
- report Markdown：
- archive manifest：

## 8. 结论

- [ ] Package A 验收通过
- [ ] 需要补做复验
- [ ] 存在 blocker，禁止进入 production_ready

阻塞项 / 待办：

1. 
2. 
3. 

