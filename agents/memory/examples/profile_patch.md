---
agent_id: "memory"
label: "profile_patch"
version: "1.0.0"
---
输入片段：
“这已经是用户第三次要求默认用英文输出周报，并且都主动修正为英文。”

期望行为：

- 识别为重复出现的稳定偏好。
- 仅输出偏好摘要、置信度和 profile patch，不保留原始长对话。
- 写入前保持 tenant scope 和审计信息完整。

示例输出：

```json
{
  "profile_patch": {
    "preference_key": "report_language",
    "value": "en",
    "confidence": 0.95
  },
  "write_memory": true
}
```
