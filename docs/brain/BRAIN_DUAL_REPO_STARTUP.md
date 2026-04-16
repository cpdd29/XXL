# Brain / External 双仓启动说明

更新时间：2026-04-16

## 目标

- `XXL` 只承载主脑核心、控制面和本地主数据真源。
- `XXL_ExternalConnection` 只承载外接 MCP 服务、Agent/Skill 资产与 external registry 原始配置。
- 主脑统一通过 external registry + 标准 URL 接入外接能力，不直接 build 外接实现。

## 当前启动入口

主脑仓：

- `./run-brain.sh`
- `./run-multi-instance-acceptance.sh`
- `./run-monitoring-stack.sh`

外接仓：

- `./run-external.sh`

## 启动顺序

1. 进入 `XXL_ExternalConnection`，执行 `./run-external.sh`
2. 回到 `XXL`，执行 `./run-brain.sh`

如果要做多实例验收：

```bash
./run-multi-instance-acceptance.sh
```

如果要接本地监控栈：

```bash
export WORKBOT_METRICS_SCRAPE_TOKEN=change-me
./run-monitoring-stack.sh
```

## 当前 compose 边界

`docker-compose.yml` 只包含：

- `postgres`
- `redis`
- `nats`
- `chromadb`
- `backend`
- `frontend`

额外 compose 由 `run-brain.sh` 通过 `WORKBOT_EXTRA_COMPOSE_FILES` 拼接：

- `deploy/multi-instance/docker-compose.multi-instance.yml`
- `deploy/monitoring/docker-compose.monitoring.yml`

## 本地联调方式

- `run-brain.sh` 会优先从 `../XXL_ExternalConnection/config/workbot_external_sources.combined.json` 同步 registry 快照到 `deploy/external-registry/workbot_external_sources.local.json`
- 主脑容器通过 `host.docker.internal` 访问外接仓映射到宿主机的 MCP 端口
- 如果未来分服务器部署，只需更新 registry 中的 `base_url` / `endpoint`，主脑代码无需改动

## 安全与边界

主脑保留：

- 统一消息入口
- 安全网关
- 项目经理 / 路由 / 编排
- 三层记忆
- 审计、权限、主数据真源
- NATS 内部事件总线

外接仓保留：

- MCP 触手服务
- 外接 agent 元数据
- 外接 skill 资产
- external registry 原始配置

## 相关验收文档

- `docs/brain/BRAIN_MULTI_INSTANCE_ACCEPTANCE.md`
- `docs/brain/MEMORY_GOVERNANCE.md`
- `docs/brain/MEMORY_GOVERNANCE_CALIBRATION.md`
- `backend/docs/MONITORING_INTEGRATION_TEMPLATE.md`
- `backend/docs/EXTERNAL_TENTACLE_OPERATIONS.md`
- `docs/brain/BRAIN_SECURITY_GATE_CHECKLIST.md`

仓内补充自检：

```bash
python3 backend/scripts/check_compatibility_boundaries.py --strict
python3 backend/scripts/check_memory_governance.py --strict
```
