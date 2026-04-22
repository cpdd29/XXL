---
agent_id: "search"
doc_type: "memory_rules"
version: "1.0.0"
---
# Memory Rules

- 只读取当前会话上下文、路由快照、任务只读视图、文件引用摘要和已治理过的 grounding summary。
- 不直接写长期记忆，不把实时检索结果、天气数据、任务瞬时状态当作稳定事实沉淀。
- 文件处理只保留结构化结果摘要，不保留原始文件内容、长文本片段或敏感附件正文。
- 定时/提醒识别结果应进入当前任务或路由元数据，而不是写入长期记忆。
- 升级到专业流程时，只输出结构化 `professional_handoff_decision`，不携带不必要的原始上下文。
