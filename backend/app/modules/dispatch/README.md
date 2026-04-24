# dispatch

调度模块，负责任务下发、需求分发，以及任务进入单 Agent / 多 Agent / workflow 运行内核后的执行推进。

核心要求：

- 需求分发节点必须支持绑定可替换的 `agent_id`
- 任务量小优先走单 Agent，任务量大或时效紧再进入多 Agent
- workflow 运行内核属于必须保留的执行底座，不再暴露旧工作流产品外壳
