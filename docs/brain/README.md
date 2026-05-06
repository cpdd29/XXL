# 主脑文档目录

更新时间：2026-04-30

当前目录用于承接知识库阶段 8 / 阶段 9 的测试、验收、上线与运营文档。

## 当前文档

- `KNOWLEDGE_BASE_TEST_MATRIX.md`
  - 知识库测试矩阵、上线前验收项、灰度观测项
- `KNOWLEDGE_BASE_OPERATIONS_SOP.md`
  - 知识库上线运营 SOP、日常维护流程、异常处理与复盘要求
- `KNOWLEDGE_BASE_PILOT_ACCEPTANCE_CHECKLIST.md`
  - 试点当天可直接执行的验收清单、Go / No-Go 判断项

## 适用范围

- 多租户接入层
- `Hermes` 外接接待智能体
- 平台知识库模块
- `Obsidian` / Markdown 知识源接入

## 相关入口

- 管理台知识库设置：`/settings/knowledge`
- 能力接入知识树：`/knowledge`
- 接入层运营视图：`/intake`
- 租户设置：`/settings/tenants`

## 相关后端接口

- `GET /knowledge/vaults`
- `POST /knowledge/vaults`
- `POST /knowledge/vaults/{vault_id}/scan-preview`
- `POST /knowledge/vaults/{vault_id}/sync`
- `GET /knowledge/sync-jobs`
- `POST /knowledge/retrieve`
- `GET /knowledge/retrieval-logs`

## 使用约束

- 本目录只记录文档化流程，不替代代码实现状态。
- 阶段 8 / 阶段 9 文档已补齐，不等于测试、灰度、试点上线已经执行完成。
- 具体执行时必须保留截图、日志、任务编号或接口响应，作为验收证据。
