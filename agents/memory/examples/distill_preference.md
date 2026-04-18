---
agent_id: "memory"
label: "distill_preference"
version: "1.0.0"
---
输入片段：
“以后每周一上午用中文提醒我发周报。”

期望行为：

- 识别为稳定偏好。
- 以结构化方式写入 tenant 作用域记忆。
- 不保留无关原话，只保留蒸馏后的事实。

示例输出：

```json
{
  "memory_type": "user_preference",
  "scope": "tenant",
  "fact": {
    "language": "zh",
    "reminder_schedule": "weekly_monday_morning",
    "topic": "weekly_report"
  },
  "confidence": 0.93
}
```
