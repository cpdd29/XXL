---
agent_id: "3"
version: "1.0.0"
name: "搜索 Agent"
model: "gpt-4.1-mini"
capabilities:
  - web_search
  - document_retrieval
  - fact_checking
trigger_intents:
  - search
  - lookup
  - research
execution:
  max_iterations: 4
  timeout_seconds: 45
---
负责搜索项目文档、知识库和外部资料，并整理来源。
