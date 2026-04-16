# Package E Security Acceptance Template

更新时间：2026-04-16

用途：

- 安全网关正式生产验收留痕
- allow / rewrite / block 三类审计样本归档
- bypass 人工复核、网关配置复核与 sign-off 闭环记录

## 1. 基本信息

- 验收日期：
- 验收窗口：
- 环境名称：
- 验收负责人：
- 参与角色：
- change / release id：

## 2. 入口范围

| 入口类型 | 路径 / 渠道 | 是否经过统一安全网关 | 备注 |
| --- | --- | --- | --- |
| API message ingress |  |  |  |
| workflow webhook |  |  |  |
| Telegram / DingTalk / 企微 Adapter |  |  |  |
| 外接公开入口 |  |  |  |

## 3. 前置检查

- [ ] `python3 backend/scripts/check_security_entrypoints.py --strict`
- [ ] `python3 backend/scripts/check_security_controls.py --strict`
- [ ] `python3 backend/scripts/check_security_audit_persistence.py --strict`
- [ ] `python3 backend/scripts/check_external_ingress_bypass.py --strict`
- [ ] `python3 backend/scripts/collect_security_acceptance_evidence.py --backend-base-url <url> --strict`

前置检查结果摘要：

```text
粘贴终端输出或报告文件路径
```

## 4. 核心控制验收

| 控制项 | 预期 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| 限流 | 高频请求被限流，风险等级可追踪 |  |  |
| 认证 | 未授权请求被拒绝，scope 校验生效 |  |  |
| 注入检测 | 高风险提示注入被拦截或升级处置 |  |  |
| 脱敏 | 敏感字段在日志 / 记忆 / 审计前已改写 |  |  |
| 审计 | allow / rewrite / block 均可回读 |  |  |
| 主脑阻断 | block 请求不会继续进入主脑编排 |  |  |

## 5. 审计样本

| 样本类型 | 请求摘要 | 审计结果 | 真源回读字段 | 证据 |
| --- | --- | --- | --- | --- |
| allow |  |  | trace / decision / metadata |  |
| rewrite |  |  | trace / rewrite diff / metadata |  |
| block |  |  | trace / reason / metadata |  |

## 6. Bypass / Manual Review Closure

| 复核项 | 来源 | 结论 | 责任人 | 证据 |
| --- | --- | --- | --- | --- |
| bypass scan 人工项 | `check_external_ingress_bypass.py` |  |  |  |
| Header 透传 | 网关 / 反向代理 |  |  |  |
| 签名校验 | webhook / external ingress |  |  |  |
| token 轮换 | 认证配置 |  |  |  |
| DB 审计真源权限与备份 | DBA / 运维 |  |  |  |

## 7. 风险与阻塞项

1. 
2. 
3. 

## 8. 证据索引

- `check_security_entrypoints`：
- `check_security_controls`：
- `check_security_audit_persistence`：
- `check_external_ingress_bypass`：
- security acceptance evidence JSON：
- security acceptance evidence Markdown：
- 审计样本截图 / SQL 回读：

## 9. Sign-Off

- [ ] Package E 验收通过
- [ ] 需要补做复验
- [ ] 存在 blocker，禁止进入 production_ready

签字 / 备注：

- 安全负责人：
- 发布负责人：
- 结论说明：
