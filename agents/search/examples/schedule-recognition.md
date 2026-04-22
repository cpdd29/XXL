---
agent_id: "search"
label: "schedule_recognition"
version: "1.0.0"
---
用户输入：
“每周五下午三点提醒我发周报。”

期望行为：

- 识别到这是定时/提醒意图。
- 说明当前轻闭环只负责识别，不负责真正创建调度。
- 输出升级建议，交给后续专业流程或调度链路。

示例输出：

```json
{
  "mode": "upgrade_required",
  "reason": "已识别定时任务意图，需要升级到专业流程创建真实调度",
  "handoff_summary": "定时提醒需求已识别，建议进入专业流程处理。"
}
```
