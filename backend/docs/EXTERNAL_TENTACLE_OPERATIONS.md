# External Tentacle Operations

更新时间：2026-04-15

适用范围：

- 外接 Agent 注册、心跳、失败上报、恢复、版本治理
- 外接 Skill 注册、心跳、失败上报、恢复、版本治理
- 外接 MCP bridge / registry 的健康检查与 fallback 观察

相关实现：

- `backend/app/api/routes/external_connections.py`
- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/external_skill_registry_service.py`
- `backend/app/services/external_connection_auth_service.py`
- `backend/app/services/tool_source_service.py`
- `backend/scripts/check_external_ingress_bypass.py`

## 1. 运维入口

Agent / Skill 控制面：

- `GET /api/external-connections/health`
- `GET /api/external-connections/governance`
- `GET /api/external-connections/agents/families/{family}/versions`
- `GET /api/external-connections/skills/families/{family}/versions`
- `POST /api/external-connections/agents/{agent_id}/promote`
- `POST /api/external-connections/skills/{skill_id}/promote`
- `POST /api/external-connections/agents/{agent_id}/set-fallback`
- `POST /api/external-connections/skills/{skill_id}/set-fallback`
- `POST /api/external-connections/agents/{agent_id}/rollout-policy`
- `POST /api/external-connections/skills/{skill_id}/rollout-policy`
- `POST /api/external-connections/agents/{agent_id}/rollback`
- `POST /api/external-connections/skills/{skill_id}/rollback`
- `POST /api/external-connections/agents/{agent_id}/deprecate`
- `POST /api/external-connections/skills/{skill_id}/deprecate`
- `POST /api/external-connections/agents/{agent_id}/recover`
- `POST /api/external-connections/skills/{skill_id}/recover`

外接入口：

- `POST /api/external-connections/agents/register`
- `POST /api/external-connections/skills/register`
- `POST /api/external-connections/agents/{agent_id}/heartbeat`
- `POST /api/external-connections/skills/{skill_id}/heartbeat`

MCP / tools 健康面：

- `GET /api/tools/health?refresh=true`
- `GET /api/tool-sources`
- `POST /api/tool-sources/scan`

## 2. 鉴权与安全约束

外接公开入口仅允许两种鉴权方式：

- `X-WorkBot-External-Token`
- `X-WorkBot-External-Timestamp` + `X-WorkBot-External-Signature`

签名规则：

- 对“原始请求 JSON”做 `sort_keys=True` 的紧凑序列化
- 按 `${timestamp}.${body}` 做 HMAC-SHA256
- 对 heartbeat 这类路径参数接口，服务端还会把 `agent_id` / `skill_id` 并入验签载荷

防护要求：

- 签名有 TTL，超时直接拒绝
- 支持 `nonce` / replay 防护，重复请求会被拒绝
- 生产环境禁止继续使用默认 `external_connection_shared_secret`
- 所有公开外接入口都必须通过 `check_external_ingress_bypass.py --strict`

## 3. 日常检查

上线前最低检查：

```bash
./.venv/bin/pytest \
  backend/tests/test_external_registries.py \
  backend/tests/test_external_connections.py \
  backend/tests/test_external_ingress_bypass.py \
  backend/tests/test_tool_source_service.py \
  backend/tests/test_tools_catalog.py -q

python3 backend/scripts/check_external_ingress_bypass.py --strict
```

运行时观察重点：

- `health` 中 `routable=false` 的能力数
- `circuit_state=open/half_open` 的能力数
- `consecutive_failures` 是否持续增长
- `next_retry_at` 是否异常延后
- `tools/health` 中 `mcp_server` / `mcp_registry` 的 `health_summary`

## 4. 故障处置

外接 Agent / Skill 熔断：

1. 先看 `/api/external-connections/health`，确认 `circuit_state`、`last_error`、`next_retry_at`。
2. 若目标版本故障，先切 `fallback` 或打开 `rollback` 到稳定版本。
3. 外部服务恢复后，执行 `recover`，再让外接实例主动发送一次 `heartbeat`。
4. 若仍不稳定，保持 `rollback` 生效，禁止继续灰度流量。

MCP bridge / registry 故障：

1. 先看 `/api/tools/health?refresh=true` 和 `/api/tool-sources`。
2. 若外部 `mcp_registry` 不健康，优先切回稳定 registry，必要时启用 local fallback。
3. `ToolSourceService` 的 fallback 观察点：
   - `governance_summary.mode`
   - `config_summary.source_mode`
   - `migration_summary`
   - `traffic_policy`
   - `rollback`

## 5. 灰度与回滚策略

灰度：

- 使用 `rollout_policy.canary_percent`
- 使用 `route_key` 固定灰度桶，避免同一会话抖动

回滚：

- 使用 `rollback_policy.active=true`
- 必须指定同 family 的 `target_version_id`
- rollback 生效后，路由应优先命中目标稳定版本

## 6. 自动化覆盖证据

已覆盖回归：

- `backend/tests/test_external_registries.py`
- `backend/tests/test_external_connections.py`
- `backend/tests/test_external_ingress_bypass.py`
- `backend/tests/test_tool_source_service.py`
- `backend/tests/test_tools_catalog.py`

已覆盖能力：

- Agent / Skill 注册、心跳、失败上报、掉线恢复、recover 闭环
- rollout / rollback / fallback / deprecate
- public ingress token / signature / nonce replay protection
- 外接控制面 health / governance 展示一致性
- MCP registry / tools health / local fallback 可观测性

## 7. 证据采集

可使用统一脚本留存本轮外接运维验收样本：

```bash
python3 backend/scripts/collect_external_tentacle_evidence.py \
  --backend-base-url http://127.0.0.1:8080 \
  --registry-path deploy/external-registry/workbot_external_sources.local.json \
  --access-token <operator_token> \
  --scan-sources \
  --strict
```

输出产物：

- `backend/docs/external_tentacle_evidence_*.json`
- `backend/docs/external_tentacle_evidence_*.md`

脚本会聚合：

- `/api/external-connections/health`
- `/api/external-connections/governance`
- `/api/tool-sources`
- `/api/tools/health`
- registry 文件与控制面 source 对账结果
