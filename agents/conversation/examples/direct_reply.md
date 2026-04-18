---
agent_id: "conversation"
label: "direct_reply_with_handoff"
version: "1.0.0"
---
用户输入：
“继续昨天那封给客户的邮件，语气改得更稳一些。”

期望行为：

- 识别为续聊和明确任务，不重复追问明显已知上下文。
- 自然确认会继续处理，但不暴露内部执行链路。
- 为后续角色整理出简短 handoff summary。

示例输出：

```json
{
  "text": "可以，我会沿着昨天那封邮件继续收一下语气，让整体更稳、更适合发给客户。"
}
```
