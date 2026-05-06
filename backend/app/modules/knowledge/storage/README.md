# knowledge/storage

知识库模块存储层。

这里后续用于抽象：

- vault 注册信息存储
- 文档主记录存储
- chunk 存储
- 同步任务记录存储
- 检索命中日志存储

当前已落地：

- `system_setting_vault_store.py`
  - 基于 `system_settings` 的知识仓注册存储
  - 用于支撑 `vault registry` 的最小可用能力
- `system_setting_document_store.py`
  - 知识文档主记录存储
- `system_setting_chunk_store.py`
  - 知识切片存储
- `system_setting_sync_job_store.py`
  - 知识同步任务存储
- `system_setting_retrieval_log_store.py`
  - 知识检索日志存储

本层只负责数据读写抽象，不负责：

- Markdown 解析
- 检索排序
- 接待层注入逻辑

如果后续存储方案调整，只改本层，尽量不影响 application 层。
