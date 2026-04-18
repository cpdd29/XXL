# XXL 知识库接入路径

## 结论

XXL 的知识库不是一个独立外挂服务，而是挂在现有本地文档检索链路上的 wiki 层。

只要内容放进 `docs/wiki/**/*.md`，并且保持和真源一致，它就会被主脑当前的搜索、写作、帮助类任务自动引用。

## 实际入口

- 索引入口：
  - `backend/app/services/document_search_service.py`
- 结果引用入口：
  - `backend/app/services/agent_execution_service.py`
  - `backend/app/services/workflow_execution_service.py`
- wiki 内容目录：
  - `docs/wiki/`
- 当前长期真源目录：
  - `README.md`
  - `docs/brain/`
  - `docs/WorkBot_开发全指南.md`
  - `docs/开发指南补充.md`
  - `backend/app/`

## 接入后的工作流

1. 代码或架构变化先落到真源。
2. 把适合长期复用的结论提炼成 wiki 页面。
3. 主脑执行 `search / write / help` 时，会通过 `document_search_service` 召回这些页面。
4. 召回结果会进入参考资料列表，随任务结果一起输出。

## 适合写进 wiki 的内容

- 主脑正式边界
- 稳定启动路径
- 常见模块入口
- 运维/验收标准口径
- 高频问答的标准答案

## 不适合写进 wiki 的内容

- 一次性调试日志
- 临时演练输出
- 每日状态播报
- 尚未定稿的临时方案
