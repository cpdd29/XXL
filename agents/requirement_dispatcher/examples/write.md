---
agent_id: "requirement_dispatcher"
label: "write_route"
version: "1.0.0"
---
输入摘要：
“用户要把现有结论整理成一版更正式的客户回复。”

期望行为：

- 识别为写作型需求。
- 给出走外接写作触手的分发建议。
- 输出 handoff summary，说明目标风格。

示例输出：

```json
{
  "intent": "write",
  "dispatch_target": "external_write_tentacle",
  "handoff_summary": "请输出一版正式、可直接发送给客户的回复草稿。"
}
```
