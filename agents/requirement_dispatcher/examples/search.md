---
agent_id: "requirement_dispatcher"
label: "search_route"
version: "1.0.0"
---
输入摘要：
“用户要查最新的接口接入方式，并希望给出资料来源。”

期望行为：

- 识别为检索型需求。
- 给出走外接检索触手的分发建议。
- 输出简洁 handoff summary。

示例输出：

```json
{
  "intent": "search",
  "dispatch_target": "external_search_tentacle",
  "handoff_summary": "需要检索最新接口接入方式，并返回可引用来源。"
}
```
