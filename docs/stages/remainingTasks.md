# Remaining Tasks

## Scope

这个清单只记录当前项目里真正还没有收口、会影响“基础工作流闭环 + Agent 调配 + 渠道接入可用性”的任务。

不重复记录已经存在底座但仍可继续深化的能力，例如：

- NATS 已有事件总线、dispatcher、worker 基础设施
- Memory 已有短中长期记忆、Chroma 检索、distill 基础链路
- Security 已有 Prompt Injection 检测、内容脱敏、RBAC、审计、限流
- Channel 已有统一消息结构、webhook 路由、adapter registry

## P0: 必须完成的闭环缺口

### 1. Master Bot 直达 Agent fallback `[done]`

现状：

- 当前消息会走 `安全网关 -> 记忆 -> Master Bot -> workflow 选择 -> workflow run`
- 当没有合适 workflow，或者 workflow 有但没有可执行 agent 时，系统不会自动退化为“直接调用某个 Agent”

收口结果：

- 已支持无 workflow 时按 intent 直达 execution agent
- 已支持 workflow 不可执行时 fallback 到 direct agent execution
- 已补齐 direct agent execution 的 task/run/dispatch context/result 回写
- 已复用现有 Agent Worker 与执行链路，未新起平行底座

验收结果：

- 已满足：消息在无可用 workflow 时仍可创建任务并进入 direct agent 执行
- 已满足：任务 / workflow run 保持统一结构，前端可继续读取执行状态
- 已满足：route decision 明确标识 `routing_strategy=workflow_or_direct_agent_fallback`

### 2. 钉钉真实双向对话闭环 `[done]`

现状：

- DingTalk webhook 入站已存在
- DingTalk adapter 的出站发送仍未实现，当前无法形成稳定双向对话

收口结果：

- 已实现 DingTalk adapter 的 `send_message`
- 已打通从 webhook 入站到任务执行再到钉钉回发的主链路
- 已复用现有鉴权、错误处理、回发失败审计链路
- 已明确钉钉回发优先使用 `sessionWebhook`，`conversationId` 仅作会话识别不再误用于出站发送

验收结果：

- 已满足：钉钉发送一条消息后，系统可创建任务并通过 `sessionWebhook` 回发结果
- 已满足：回发成功和失败继续复用统一审计/实时日志
- 已满足：回发目标优先锁定原会话 `sessionWebhook`，避免 `conversationId/sessionWebhook` 混淆

### 3. 统一“渠道消息 -> 任务 -> 执行 -> 回传”主链路状态 `[done]`

现状：

- 主链路已存在，但 workflow 路由、agent 执行、渠道回传的状态定义还不够统一

收口结果：

- 已统一任务侧派生字段：`current_stage`、`dispatch_state`、`failure_stage`、`failure_message`、`delivery_status`、`delivery_message`、`status_reason`
- 已统一 workflow run / dispatch context 的失败归因与出站回传状态记录
- 已将调度失败、执行失败、执行超时、渠道回传失败明确写回主链路上下文
- 已在 dashboard / tasks / collaboration 页面展示具体失败阶段与状态原因，而不再只显示笼统 `failed`

验收结果：

- 已满足：任意失败都能定位到调度、执行、回传等具体层级
- 已满足：任务详情、任务列表、协作页、仪表盘均可看到统一状态归因
- 已满足：completed 但 outbound failed 的场景可单独识别，不再和 execution failure 混淆

## P1: 直接影响“智能调度感”的核心能力

### 4. Master Bot 动态调度升级 `[done]`

现状：

- 已有 intent classifier
- 已有 workflow candidate 选择
- 但仍以 workflow 驱动为主，不是动态多 Agent 协同

收口结果：

- 已增加 Master Bot 动态 planner，可识别“检索 + 写作/说明”复合请求并生成 `execution_plan`
- 已支持在运行时选择单 Agent 或多 Agent 编排，而不是只依赖静态 workflow
- 已支持 `serial` / `parallel` 两种多 Agent 执行计划表达，并复用现有 direct-agent 执行链路
- 已支持多 Agent 子结果聚合，最终仍产出统一 `task.result`
- 已把动态规划、协同执行、结果聚合写入 execution trace 与 task steps，便于后续观测

验收结果：

- 已满足：同一类请求可按上下文动态选择不同 agent 组合
- 已满足：多 agent 协同结果会被聚合成单一最终回复
- 已满足：普通单意图请求仍保持原 workflow / direct fallback 路由，不被动态 planner 误伤

### 5. Agent Inbox / Outbox 协议化 [done]

现状：

- 有 NATS publish/subscribe
- 有 workflow/agent execution worker
- 但缺少真正面向 agent 的统一消息协议

已完成：

- 已定义 workflow.execution / agent.execution 的统一 protocol envelope
- 已引入 request_id / correlation_id / attempt / max_attempts / dead-letter 基础语义
- 已区分 command、event、result 三类消息并补充成功/失败/死信事件
- 已补齐 poller / dispatcher / worker 的协议透传与 repair 兼容

保留说明：

- durable job 表结构本轮未升级为 message ledger，协议根信息先持久在 `run.dispatch_context.protocol`
- 真正 mailbox 级别的多消息持久化、独立 DLQ 表、细粒度幂等存储仍放在后续底座深化

验收标准：

- agent 间消息可以被明确追踪
- 同一任务的请求、执行、结果、失败都能串成完整链路

### 6. Agent Heartbeat 与运行时管理 [done]

现状：

- dashboard 有 heartbeat 样式数据
- 但没有完整 agent heartbeat 协议和状态保活机制

已完成：

- 已新增 `POST /api/agents/{agent_id}/heartbeat`，支持 heartbeat 上报运行状态、负载、队列长度与来源信息
- 已把 `runtime_status / runtime_status_reason / routable / runtime_metrics` 合并进 agent 列表与详情返回
- 已基于心跳时间窗实现 `online / degraded / offline / unknown` 判定，长时间无 heartbeat 会自动降级或离线
- 已把 dispatcher 的 agent 选择收口为优先健康节点、降级节点兜底、离线节点避让

验收标准：

- agent 管理页可真实反映在线状态
- dispatcher 可避开离线 agent

## P1: 渠道接入产品化缺口

### 7. WeCom / Feishu / DingTalk 出站能力补齐 [done]

现状：

- Telegram 出站已实现
- WeCom / Feishu / DingTalk 仍主要停留在 parse webhook 输入

已完成：

- 已为 WeCom / Feishu adapter 补齐 `send_message`，支持直接 webhook URL 或 bot key 形式的最小出站能力
- 已补充渠道级配置项：base URL、bot key、HTTP timeout
- 已在 `channel_outbound_service` 加入一次失败重试，并保持 realtime / audit trace 记录

验收标准：

- 三个渠道都具备最小可用的收发能力

### 8. 渠道身份映射与用户画像绑定收口 [done]

现状：

- 已有 unified message 和 profile 映射基础

已完成：

- 已将 `identity_mapping_status / source / confidence / last_identity_sync_at` 正式接入用户画像输出
- 已新增人工修正入口：`POST /api/users/{user_id}/platform-accounts/bind` 与 `/unbind`
- 已在绑定/解绑逻辑里同步 `source_channels`、去重平台账号、更新映射置信度并记录审计日志

验收标准：

- 用户画像页可看到来源渠道与绑定账号
- 错误映射可以被修正

## P2: 已有底座但需要深化的能力

### 9. Memory 质量提升 [done]

现状：

- 已有 memory 底座，不属于“未做”

已完成：

- 已增强句子规范化与摘要去重，减少标点/空格差异导致的重复偏好与重复摘要
- 已为 retrieval 增加候选指纹去重、稳定的 `matched_terms` 合并与 rerank 去重，避免近重复记忆污染注入
- 已补强偏好型记忆的聚焦排序，使用户偏好类记忆在相关查询下优先返回

### 10. Security 商用化加强 [done]

现状：

- 已有安全底座，不属于“未做”

已完成：

- 已加强 prompt injection 评估输出，补充 `risk_level / matched_signals`，提升审计与排障可读性
- 已补齐更细粒度 RBAC：`agents:heartbeat`、`users:write`、`users:block`
- 已为 webhook guard 增加限流拦截审计、trace 元数据，以及 payload 深度/列表/字典/字符串长度防护

## 建议执行顺序

1. P0-1：Master Bot direct-agent fallback
2. P0-2：钉钉出站回发，形成真实双向对话
3. P0-3：统一主链路状态与失败归因
4. P1-5：Agent inbox/outbox 协议化
5. P1-6：Agent heartbeat 与运行时管理
6. P1-4：动态多 Agent 调度
7. P1-7：补齐 WeCom / Feishu 出站
8. P1-8：用户画像绑定收口
9. P2-9：Memory 质量优化
10. P2-10：Security 商用化强化

## 当前一句话判断

当前项目已经有“可运行的底座系统”，但还没有完全收口成“自动调度 + 多 Agent + 多渠道双向对话”的产品闭环。
