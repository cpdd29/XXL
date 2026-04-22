---
agent_id: "search"
label: "professional_workflow_escalation"
version: "1.0.0"
---
用户输入：
“xx 客户下了 200 个鼠标垫的订单，帮我推进下单流程并同步给仓库。”

期望行为：

- 识别为专业工作流，不在轻闭环里硬做。
- 明确说明需要升级到专业流程。
- 给出可供后续节点使用的升级原因和交接摘要。

示例输出：

```json
{
  "mode": "upgrade_required",
  "reason": "涉及客户订单、业务流程推进和跨系统协同",
  "handoff_summary": "客户订单流程需进入专业工作流，由后续派工链路处理。"
}
```
