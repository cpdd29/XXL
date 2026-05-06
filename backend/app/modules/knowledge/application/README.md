# knowledge/application

知识库模块应用服务层。

这里后续承接的核心能力：

- vault 注册管理
- 知识源扫描
- Markdown / Frontmatter 解析
- 文档切片
- 两段检索（租户专用 -> 通用）
- `knowledge_hits` 结构化输出
- 接待层知识注入组装

当前已落地：

- `vault_registry_service.py`
  - 知识仓注册、更新、删除、解析生效范围
- `parser_service.py`
  - Frontmatter 解析、标题提取、标签/别名/双链提取
- `chunk_service.py`
  - 按标题段落切片，生成最小可用 chunk
- `sync_service.py`
  - 手动同步 knowledge vault，写入文档与 chunk，并记录 sync job
- `retrieval_service.py`
  - 两段检索：先租户专用，再通用知识
  - 返回统一 `KnowledgeHit` 结构
- `retrieval_log_service.py`
  - 记录检索日志，支撑调试与接待链观测
- `injection_service.py`
  - 生成 `knowledge_hits`
  - 写回接待链 `message.metadata`

当前接待层已挂接：

- `message_ingestion_service.py`
  - 客户准入通过后
  - Hermes 调用前执行知识检索
  - 将检索结果注入到 `knowledge_hits`

建议后续主要服务文件：

- `vault_registry_service.py`
- `sync_service.py`
- `parser_service.py`
- `chunk_service.py`
- `retrieval_service.py`
- `retrieval_log_service.py`
- `injection_service.py`

本层是知识库主脑，不直接暴露 HTTP 接口。
