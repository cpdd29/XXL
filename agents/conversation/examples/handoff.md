---
agent_id: "conversation"
label: "handoff"
version: "1.0.0"
---
用户输入：
“帮我整理一下这个需求：客户要一个审批后才能发出的日报流程。”

期望行为：

- 在需求已经足够明确时，不再反复追问。
- 输出简洁的 handoff summary，包含目标、约束、风险点和下一责任方。
- 不直接承诺已经完成工作流创建或发布。

示例输出摘要：

```json
{
  "handoff_summary": {
    "goal": "设计日报工作流草案",
    "constraints": [
      "发送前需要审批",
      "仅使用当前租户可见能力"
    ],
    "risk_points": [
      "外发通知属于可见性较高的动作"
    ],
    "next_owner": "workflow_designer"
  }
}
```
