---
agent_id: "general_assistant"
label: "web_query_lookup"
version: "1.0.0"
---
用户输入：
“帮我联网查一下最近的出口物流新闻。”

期望行为：

- 识别为非专业查询。
- 走联网查询并给出可引用结果。
- 输出结果摘要和来源线索。

示例输出：

```json
{
  "query_mode": "web_query",
  "assistant_reply": "已整理最近的出口物流相关新闻摘要，并保留来源线索供继续查看。",
  "references": [
    "web_search_reader"
  ]
}
```
