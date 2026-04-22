---
agent_id: "search"
label: "weather_lookup_light_close_loop"
version: "1.0.0"
---
用户输入：
“今天广州天气怎么样，会不会下雨？”

期望行为：

- 识别为轻量实时查询，优先在当前轮次闭环。
- 使用运行时天气能力返回结果，并给出检查时间或工具来源。
- 不把实时查询升级成专业流程。

示例输出：

```json
{
  "result_type": "weather_result",
  "tool": "weather_lookup",
  "summary": "已查询广州天气，当前多云，气温 26C，今晚降雨概率较低。",
  "checked_at": "<runtime timestamp>",
  "upgrade_to_professional_workflow": false
}
```
