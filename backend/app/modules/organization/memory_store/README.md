# organization/memory_store

组织模块记忆存储目录。

这里承载组织模块自己的中长期记忆存储实现，不属于平台底座，也不属于通用数据库接入层。

- `sqlite_memory_store.py`：中期记忆的 SQLite 存储实现。
- `chroma_memory_store.py`：长期记忆的 Chroma / 本地持久化存储实现。

这些实现当前主要被 `organization/application/memory_service.py` 调用。
