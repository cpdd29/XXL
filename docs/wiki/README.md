# XXL Wiki

`docs/wiki/` 是 XXL 的 LLM 可维护知识库层。

它不替代代码和原始设计文档，而是把高频、稳定、适合被搜索和引用的项目知识整理成更短、更清晰的 wiki 页面，让主脑现有的本地知识检索链路可以直接用到。

## 目标

- 让 `backend/app/services/document_search_service.py` 自动索引 `docs/wiki/**/*.md`
- 让 `search / write / help` 三类任务能直接引用 wiki 页面
- 把“长原文档 + 散落代码事实”整理成 LLM 更容易维护和召回的知识地图

## 三层结构

- 真源：
  - 代码
  - `README.md`
  - `docs/brain/*`
  - `docs/WorkBot_开发全指南.md`
  - `docs/开发指南补充.md`
- wiki：
  - `docs/wiki/**/*.md`
- 规则：
  - `docs/wiki/WIKI_SCHEMA.md`

## 使用方式

1. 改功能、改架构、改运维流程时，先改代码和原始真源文档。
2. 再把适合长期复用的结论补到 `docs/wiki/`。
3. 当搜索、写作、帮助类任务走本地知识检索时，系统会自动把 wiki 页面作为参考资料的一部分返回。

## 当前建议沉淀的主题

- 主脑边界与正式执行路径
- 启动方式与双仓协作入口
- 常见运维动作和正式验收入口
- 知识检索入口、真源边界和更新规则
