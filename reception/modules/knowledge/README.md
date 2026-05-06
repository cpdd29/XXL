# 知识库模块（knowledge）

该模块负责平台知识库的前端管理能力。

当前职责：

- 承接能力接入侧的知识树浏览与上传入口
- 展示知识仓列表
- 新增 / 编辑 / 删除知识仓
- 支持“平台托管 / 外部接入”两种知识仓接入方式
- 平台托管知识仓支持 Markdown 文件导入
- 外部接入知识仓支持连通性校验
- 触发扫描预览与手动同步
- 查看同步后的文档列表、Frontmatter 与 Chunk 切片
- 查看同步任务与检索日志

目录说明：

- `hooks/use-knowledge.ts`：知识库接口访问与缓存管理
- `pages/knowledge-page.tsx`：组织设置下的知识库管理页
- `pages/knowledge-capability-page.tsx`：能力接入下的知识树、Obsidian 节点视图与内部文档上传页
