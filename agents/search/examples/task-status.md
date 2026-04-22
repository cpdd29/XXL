---
agent_id: "search"
label: "task_status_board"
version: "1.0.0"
---
用户输入：
“帮我看看当前任务进度。”

期望行为：

- 识别为任务看板/任务状态类只读请求。
- 在轻闭环里直接读取任务摘要，不升级到专业流程。
- 给出可直接回传的任务概览。

示例输出：

```json
{
  "mode": "light_closed_loop",
  "action": "task_board",
  "status": "completed",
  "handoff_summary": "已生成当前任务看板，可直接向用户回传。"
}
```
