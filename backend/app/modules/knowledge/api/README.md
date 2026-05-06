# knowledge/api

知识库模块 API 层。

当前已落地的接口：

- `GET /knowledge/vaults`
- `GET /knowledge/vaults/{vault_id}`
- `POST /knowledge/vaults`
- `PUT /knowledge/vaults/{vault_id}`
- `DELETE /knowledge/vaults/{vault_id}`
- `POST /knowledge/vaults/{vault_id}/scan-preview`
- `GET /knowledge/documents`
- `GET /knowledge/documents/{document_id}`
- `GET /knowledge/sync-jobs`
- `GET /knowledge/sync-jobs/{sync_job_id}`
- `POST /knowledge/vaults/{vault_id}/sync`
- `POST /knowledge/retrieve`
- `POST /knowledge/retrieve/metadata-preview`
- `GET /knowledge/retrieval-logs`

这里后续继续承接：

- 同步任务触发与查看
- 文档列表与详情查看
- 检索命中详情查看

本层只做：

- 请求参数校验
- 调用 application service
- 返回统一响应结构

本层不做：

- 文件扫描
- Markdown 解析
- 检索排序
- 注入 `Hermes` 逻辑
