# Package D External Acceptance Template

更新时间：2026-04-16

用途：

- 外接 Agent / Skill / MCP 正式运维验收留痕
- registry 对账、心跳、掉线恢复、灰度、回滚、recover 闭环记录
- Header 透传、签名链路、网关配置复核归档

## 1. 基本信息

- 验收日期：
- 验收窗口：
- 环境名称：
- 验收负责人：
- 外接仓版本：
- registry 文件：

## 2. 验收范围

- [ ] Agent 注册 / 心跳 / 恢复
- [ ] Skill 注册 / 心跳 / 恢复
- [ ] MCP bridge 健康探测
- [ ] 灰度发布
- [ ] rollback / fallback / recover
- [ ] Header / 签名 / 反向代理复核

## 3. 前置检查

- [ ] `python3 backend/scripts/check_external_ingress_bypass.py --strict`
- [ ] `python3 backend/scripts/collect_external_tentacle_evidence.py --backend-base-url <url> --registry-path <registry> --strict`

前置检查结果摘要：

```text
粘贴终端输出或报告文件路径
```

## 4. registry 对账

| 能力族 | family | registry 版本 | 控制面版本 | 结果 | 备注 |
| --- | --- | --- | --- | --- | --- |
| Agent |  |  |  |  |  |
| Skill |  |  |  |  |  |
| MCP |  |  |  |  |  |

## 5. 核心验收项

| 验收项 | 预期 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| Agent 注册成功 | 控制面可见且 routable |  |  |
| Agent 心跳更新 | last_seen / health 正常刷新 |  |  |
| Agent 掉线恢复 | 离线后可 recover |  |  |
| Skill 注册成功 | 控制面可见且 routable |  |  |
| Skill 心跳更新 | last_seen / health 正常刷新 |  |  |
| Skill 掉线恢复 | 离线后可 recover |  |  |
| MCP bridge 健康探测 | tools/health 正确反映状态 |  |  |
| fallback / rollback | 主脑路由可降级且能恢复 |  |  |
| Header / 签名链 | 透传与校验无绕过 |  |  |

## 6. 灰度 / 回滚记录

| 操作 | 目标 family | 目标版本 | 结果 | 证据 |
| --- | --- | --- | --- | --- |
| canary promote |  |  |  |  |
| set fallback |  |  |  |  |
| rollback |  |  |  |  |
| recover |  |  |  |  |

## 7. 证据索引

- `/api/external-connections/health`：
- `/api/external-connections/governance`：
- `/api/tool-sources`：
- `/api/tools/health`：
- evidence JSON：
- evidence Markdown：

## 8. 结论

- [ ] Package D 验收通过
- [ ] 需要补做复验
- [ ] 存在 blocker，禁止进入 production_ready

阻塞项 / 待办：

1. 
2. 
3. 

