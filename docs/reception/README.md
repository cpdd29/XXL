# 接待层文档目录

更新时间：2026-05-03

当前目录用于承接“平台渠道接入 -> 客户准入 -> 安全监听 -> Hermes 接待 -> 输出监听 -> 任务中心”的接待层文档。

## 当前文档

- `RECEPTION_FULL_CHAIN_VALIDATION_CHECKLIST.md`
  - 接待层全链路联调清单、接口入口、页面观察点、验收标准

## 适用范围

- 多租户平台接待层
- 外接 `Hermes` 接待智能体
- 客户准入确认层
- 输入 / 输出安全监听
- 接待后任务落库与任务中心联动

## 相关前端入口

- `/intake`
- `/tasks`
- `/settings/admission-template`
- `/settings/intake-security`
- `/settings/channel-integration`
- `/settings/tenants`

## 相关后端接口

- `GET /api/intake/overview`
- `GET /api/intake/traces/{trace_id}`
- `WS /api/intake/realtime`
- `POST /api/webhooks/dingtalk/callback`
- `GET /api/customer-access/settings`
- `PUT /api/customer-access/settings`
- `GET /api/tasks`
- `WS /api/tasks/realtime`

## 使用约束

- 本目录用于联调、验收与运营收口，不替代模块源码说明。
- 接待层当前只保留“继续接待 / 转任务”两种正式结果。
- `Hermes` 不直接接任何渠道，所有渠道收发由平台负责。
