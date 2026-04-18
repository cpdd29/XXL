---
agent_id: "workflow_designer"
label: "draft_tenant_workflow_proposal"
version: "1.0.0"
---
用户需求：
“给销售团队做一个流程：每天汇总新订单，拉 CRM 客户信息，生成日报并发到群里。”

期望行为：

- 只使用当前租户已启用且健康的能力。
- 产出节点拆解、依赖关系、审批点和回滚点。
- 输出为提案草稿，不直接发布执行。

示例输出摘要：

```json
{
  "proposal_name": "daily_order_crm_digest",
  "steps": [
    "读取订单增量",
    "拉取 CRM 客户信息",
    "生成日报草稿",
    "审批通过后发送到群"
  ],
  "approval_checkpoints": [
    "跨系统数据聚合",
    "外发通知前人工确认"
  ],
  "rollback_plan": [
    "停止定时触发",
    "撤销未发送日报",
    "保留审计记录"
  ]
}
```
