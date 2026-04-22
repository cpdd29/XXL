---
agent_id: "general_assistant"
label: "professional_query_lookup"
version: "1.0.0"
---
用户输入：
“帮我查一下系统里的送货单专业流程应该怎么走。”

期望行为：

- 识别为专业查询。
- 优先走系统内专业知识库和专业流程说明。
- 输出简洁结论，不伪造外部来源。

示例输出：

```json
{
  "query_mode": "professional_query",
  "assistant_reply": "已根据系统内专业流程整理出送货单处理步骤，可继续按流程推进。",
  "references": [
    "professional_process_reader"
  ]
}
```
