# 对话入口与拟人化呈现改造清单

## 当前落地状态

- 已完成代码侧 P0 / P1 改造：
  - 问候与轻咨询已切入 `chat mode`
  - 入站链路已写入 `interaction_mode`
  - 已新增 `chat_reply` 结果协议
  - 渠道出站已按聊天回复直出自然正文
  - provider / fallback 已区分执行痕迹
  - 多轮续聊已优先并入当前上下文
  - 工作流对 `chat_reply` 已兼容，不再强依赖 `title`
  - 失败回退文案已改为自然对话口吻
- 已完成环境侧 P2 补齐：
  - Redis 已通过本地 Docker Compose 启动并验证 `PONG`
  - 后端 `RedisProvider` 已验证可连通真实 Redis
  - Chroma 长期记忆已恢复为本地持久化模式
  - 长期记忆写入 / 查询已完成实测

说明：

- 本文档最初作为改造清单创建，当前代码实现已覆盖其中主要代码项。
- P2 中的 Redis 依赖已通过本机容器启动完成。
- Chroma 在本地开发环境下已切换为持久化实现，不再强依赖额外服务进程。

## 背景判断

当前项目已经完成了钉钉渠道的基础闭环：

- 入站消息可以通过 webhook 或 DingTalk Stream 进入系统
- 消息会进入统一的消息摄取、路由、任务、工作流 / Agent 执行链路
- 出站消息已经支持 DingTalk adapter，且具备 `sessionWebhook` 回传与 OpenAPI 直发能力

但当前“聊天体验”仍然偏后台任务系统，而不是拟人化 Agent 对话，主要表现为：

- 问候语会被固定短路为硬编码回复
- 渠道回传默认使用 `title + summary + content` 的任务结果格式
- 用户虽然在“聊天”，系统对外呈现仍然像“任务结果通知”
- provider 能力已接入，但并未稳定成为聊天主路径

## 现状证据

- 问候语被固定识别并直接返回预设结果：
  - `backend/app/services/agent_execution_service.py`
- 消息默认进入任务化执行链路：
  - `backend/app/services/message_ingestion_service.py`
- 渠道回传默认按任务结果结构渲染：
  - `backend/app/services/channel_outbound_service.py`
- 钉钉已接入 webhook + stream：
  - `backend/app/api/routes/webhooks.py`
  - `backend/app/services/dingtalk_stream_service.py`
- 钉钉出站已支持 OpenAPI 与 `sessionWebhook` fallback：
  - `backend/app/adapters/dingtalk.py`

## 改造目标

把当前的“渠道消息 -> 任务结果回传”收口为“像人在聊天”的 Agent 对话体验。

目标状态：

- 用户发送“你好”“你是谁”“你能做什么”，回复应是自然对话，不应出现 `【问候回复】`
- 用户发送追问、补充说明、上下文续聊时，应保持会话连续性
- 用户发送明确任务时，仍可进入结构化任务执行，但对外表达应优先自然
- 内部依然允许多 Agent 协同，但对外统一由一个人格输出
- provider 可用时优先走真实 Agent 推理；provider 不可用时才优雅降级

## 验收标准

### A. 聊天入口

- “你好 / 您好 / 在吗 / 你能做什么”不再命中固定模板问候
- 短消息、闲聊、澄清、继续追问可进入 chat mode
- chat mode 不强制表现为工单或报告

### B. 聊天呈现

- 钉钉聊天回复不再默认使用 `【标题】 + 摘要 + 正文`
- 闲聊型回复默认直接输出自然正文
- 只有明确要求“报告 / 纪要 / 草稿 / 清单”时才使用结构化格式

### C. Agent 真实性

- provider 可用时，chat mode 优先走真实模型推理
- 日志中可区分本次回复是 provider 生成还是 fallback 生成
- fallback 回复不再暴露系统内部术语

### D. 会话连续性

- 用户连续 2 到 3 轮追问时，能承接上一轮上下文
- 补充说明优先进入同一对话上下文，而不是轻易拆成新任务
- 长期记忆 / 短期记忆不可用时有清晰降级，但不破坏聊天口吻

## 任务拆解

## P0: 把聊天入口真正切到对话模式

### 1. 去掉问候语硬编码短路

目标：

- 不再把问候语直接映射为固定回复
- 问候语也能进入真实 Agent 对话

涉及文件：

- `backend/app/services/agent_execution_service.py`

改造点：

- 删除或降级 `GREETING_EXACT_MATCHES` 的短路优先级
- `execute_task()` 中不要在最前面直接 `return build_greeting_result()`
- 将问候语纳入 chat mode，而不是独立的固定结果分支
- 保留 `build_greeting_result()` 仅作为 provider 不可用时的最后降级兜底

验收：

- 用户发送“你好”时，不再返回硬编码问候模板

### 2. 为消息入口增加 `chat mode / task mode` 路由

目标：

- 区分“聊天”与“明确任务”

涉及文件：

- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/master_bot_service.py`

改造点：

- 在 `ingest_unified_message` 之前或路由阶段增加入口分类
- 新增 `interaction_mode`，至少包含：
  - `chat`
  - `task`
  - `workflow`
- 对短问候、轻咨询、澄清式追问优先标为 `chat`
- 对“写一封 / 帮我查 / 生成 / 总结 / 输出报告”优先标为 `task`
- 将 `interaction_mode` 写入 `dispatch_context` 与 `route_decision`

验收：

- 系统日志和上下文里可以看到当前消息是 `chat` 还是 `task`

### 3. chat mode 优先命中真实 provider

目标：

- 聊天消息默认走真实 Agent 推理，而不是本地拼接式结果

涉及文件：

- `backend/app/services/agent_execution_service.py`
- `backend/app/services/settings_service.py`

改造点：

- 为 `chat` 模式建立专门执行分支
- provider 可用时，优先执行 `_try_provider_result()`
- provider 失败时记录明确降级原因
- 若所有 provider 都不可用，再走本地 fallback

验收：

- chat mode 下可在 execution trace 中看到 provider 执行痕迹

## P0: 把聊天呈现改成 IM 风格

### 4. 新增 `chat_reply` 结果协议

目标：

- 让聊天回复不再强依赖 `title/summary/content`

涉及文件：

- `backend/app/services/agent_execution_service.py`
- `backend/app/services/channel_outbound_service.py`
- `backend/app/schemas/messages.py`
- 视情况补充 `backend/app/schemas/tasks.py` 或 workflow schema

改造点：

- 新增结果类型：
  - `chat_reply`
  - 保留 `search_report`
  - 保留 `draft_message`
  - 保留 `help_note`
- `chat_reply` 的核心字段建议为：
  - `kind`
  - `text`
  - `references`
  - `execution_trace`
- 不强制要求 `title` 和 `summary`

验收：

- chat mode 结果可以只有自然正文

### 5. 渠道出站渲染区分聊天与报告

目标：

- 钉钉聊天里输出自然回复，而不是后台结果卡片

涉及文件：

- `backend/app/services/channel_outbound_service.py`

改造点：

- 在 `render_task_result_text()` / `_render_result_text()` 中识别 `kind`
- `kind == chat_reply` 时：
  - 直接输出 `text`
  - 不拼 `【标题】`
  - 不拼“已返回轻量问候消息”
- `kind == search_report / draft_message / help_note` 时保留结构化渲染
- 对钉钉渠道增加短文本优先渲染策略

验收：

- 用户在钉钉里收到的闲聊型回复只是一段自然文字

### 6. 构建统一对外人格

目标：

- 避免不同 Agent 的口吻像多个后台模块轮流说话

涉及文件：

- `backend/app/services/agent_execution_service.py`
- `agents/*/agent.md`
- `agents/*/soul.md`

改造点：

- 引入统一对外 persona，建议为单一“主助理人格”
- 对 search / write / help / output 的对外语言风格设统一约束
- 明确：
  - 语气：自然、简洁、不端着
  - 长度：先短后长
  - 优先用对话口吻，不用系统公告口吻
  - 不主动暴露“任务执行 / 工作流 / 调度 / Agent Worker”等内部术语

验收：

- 多种意图下的回复看起来像同一个机器人在说话

## P1: 增强多轮对话连续性

### 7. 继续完善上下文续聊判定

目标：

- 用户补充说明、继续追问时，优先续接当前会话

涉及文件：

- `backend/app/services/message_ingestion_service.py`

改造点：

- 在现有 context patch 规则上补一层“chat continuation”
- 将以下类型优先判为续聊：
  - “那你帮我……”
  - “换个更正式的说法”
  - “继续”
  - “那如果是钉钉群聊呢”
- 降低 chat mode 下误开新任务的概率

验收：

- 用户 2 到 3 轮聊天都能承接上下文

### 8. 给 provider prompt 新增聊天专用模板

目标：

- 让模型输出更像聊天，而不是任务报告

涉及文件：

- `backend/app/services/agent_execution_service.py`

改造点：

- 新增 `mode = chat`
- 单独定义 `chat` 模式的 system prompt 和 user prompt
- 重点约束：
  - 先自然回答
  - 不用标题
  - 不默认列 bullet
  - 不把内部执行过程告诉用户
  - 若用户表述含糊，先澄清，不急着产出结构化大段文本

验收：

- 相同问题在 `chat` 模式下输出明显比当前更自然

### 9. 对外统一“单说话人”，对内保留多 Agent

目标：

- 内部多 Agent 协作，对外仍像一个机器人

涉及文件：

- `backend/app/services/master_bot_service.py`
- `backend/app/services/agent_execution_service.py`

改造点：

- 多 Agent 协同时，最终输出统一走聚合人格
- 聚合时不暴露：
  - “搜索 Agent 子任务”
  - “写作 Agent 子任务”
  - “Master Bot 动态编排已启用”
- 这些信息只留在 trace / collaboration / dashboard 中

验收：

- 用户端看到的是一条自然回复，而不是内部编排摘要

## P1: provider 与降级路径透明化

### 10. 增强 provider 命中与可观测性

目标：

- 分清“真实 Agent 回复”和“fallback 回复”

涉及文件：

- `backend/app/services/agent_execution_service.py`
- `backend/app/services/operational_log_service.py`
- `backend/app/services/channel_outbound_service.py`

改造点：

- execution trace 中明确记录：
  - `provider_live`
  - `provider_failed`
  - `fallback_local`
- 后台日志中可快速看到本轮回复是否真实命中 provider
- 如 provider 失败，不要把异常细节直接发给用户

验收：

- 开发者可通过日志区分体验问题到底出在 provider 还是呈现层

### 11. 优化 fallback 文案

目标：

- fallback 时仍然像真人，不像系统提示

涉及文件：

- `backend/app/services/agent_execution_service.py`
- `backend/app/services/channel_outbound_service.py`

改造点：

- 所有 fallback 文案去掉：
  - “问候回复”
  - “已返回轻量问候消息”
  - “任务执行失败”
  - “结果已生成，但……”
- 改为对用户友好的自然表述
- 内部原因放日志，不放主回复正文

验收：

- 即使 fallback，用户也不会明显感知到“系统模板感”

## P2: 记忆与基础设施补齐

### 12. 补齐 Redis，稳定短期会话能力

目标：

- 提升对话连续性与上下文保持能力

涉及范围：

- 运行环境
- `backend/app/core/redis_client.py`
- `backend/app/services/memory_service.py`
- `backend/app/services/security_gateway_service.py`

改造点：

- 启动 Redis
- 确保短期记忆、限流、活跃会话状态不再长期运行在内存 fallback

验收：

- 控制台不再持续出现 Redis connection refused

### 13. 补齐 Chroma，恢复长期记忆检索

目标：

- 让机器人能积累长期偏好与历史知识

涉及范围：

- 运行环境
- `backend/app/core/chroma_memory_store.py`
- `backend/app/services/memory_service.py`

改造点：

- 安装 `chromadb`
- 确保长期记忆可正常写入与检索

验收：

- 控制台不再出现 `chromadb package is not installed`

## 推荐实施顺序

1. 去掉问候硬编码短路
2. 增加 `interaction_mode = chat/task`
3. 新增 `chat_reply` 结果协议
4. 改渠道出站渲染
5. 新增 chat mode prompt
6. 统一主人格
7. 多 Agent 对外隐藏内部编排
8. 增强 provider / fallback 可观测性
9. 补 Redis
10. 补 Chroma

## 最终目标示例

### 当前效果

用户：

`你好`

机器人：

`【问候回复】`

`已返回轻量问候消息`

`你好，我在。`

### 目标效果

用户：

`你好`

机器人：

`你好，我在。现在你想让我帮你处理什么？`

用户：

`你能做什么`

机器人：

`我可以直接帮你查问题、整理信息、写回复，也可以继续跟着你当前这件事往下做。你如果有具体目标，直接发给我就行。`

用户：

`那帮我看看钉钉对话为什么还不像真人`

机器人：

`可以。我先从问候分支、聊天渲染和 provider 命中这三层帮你拆。`

## 一句话结论

这次改造的本质，不是再补一个渠道接口，而是把当前“任务系统外露”的体验，收口成“对外像一个连续对话的 Agent，对内仍保留 workflow 与多 Agent 执行底座”的产品形态。
