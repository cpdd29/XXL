# dispatch/execution_support

调度执行辅助目录。

这里承载调度运行时使用的轻量辅助能力，例如项目文档检索、语言识别等，不直接负责任务编排或状态持久化。

- `document_search_service.py`：为执行阶段提供本地项目文档检索与兜底知识块。
- `language_service.py`：为执行阶段提供轻量语言识别能力。

当前执行辅助能力已经统一收敛到本目录，新代码应直接从 `app.modules.dispatch.execution_support` 引用。
