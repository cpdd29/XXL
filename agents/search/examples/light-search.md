---
agent_id: "search"
label: "light_search_close_loop"
version: "1.0.0"
---
用户输入：
“帮我查一下广州七天内的天气预报。”

期望行为：

- 识别为可轻闭环处理的实时查询。
- 走搜索/轻执行能力，不升级到专业流程。
- 输出可直接回传的结果摘要。

示例输出：

```json
{
  "mode": "light_closed_loop",
  "action": "weather_lookup",
  "status": "completed",
  "handoff_summary": "已完成广州天气查询，可直接向用户回传结果。"
}
```
