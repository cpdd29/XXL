# WorkBot 主脑与触手安全边界清单（deconstruct2）

版本：v1.1  
更新时间：2026-04-14  
目标：明确“什么必须留在主脑本地、什么必须外置”，并形成可执行的安全红线。

## 1. 总原则

- 划分依据不是“代码是否好拆”，而是“是否属于安全域”。
- 凡是涉及身份、权限、审批、记忆、任务状态、审计、路由决策的能力，必须留在主脑本地。
- 凡是已经得到主脑明确授权后，去执行具体能力的模块，才允许外置。
- 外置触手只能执行，不能裁决。
- 外置触手可以返回结果，但不能掌握系统真相。

## 2. 两个安全域

### 2.1 Brain Trusted Zone

定义：

- 主脑可信域
- 有状态
- 有权限
- 有审计
- 有任务真相
- 有决策权

主脑可信域的责任：

- 接收消息
- 统一身份
- 安全检查
- 意图识别
- 需求澄清
- 工作流路由
- 编排决策
- 审批控制
- 任务状态推进
- 记忆管理
- 审计留痕

### 2.2 Tentacle Execution Zone

定义：

- 外置执行域
- 只负责具体能力执行
- 不持有主脑真相
- 不拥有最终权限决策权
- 不直接面向平台回传主链结果

触手执行域的责任：

- 接收主脑下发的明确执行请求
- 执行具体能力
- 返回结构化结果、错误、健康状态、观测信息

## 3. 必须留在主脑本地的模块

以下内容必须留在 `/Users/xiaoyuge/Documents/XXL`。

### 3.1 接入与安全

- 接入层 Adapter
- UnifiedMessage 统一消息对象
- 安全网关
- 限流
- 认证
- Prompt Injection 检测
- 脱敏
- 审计日志

### 3.2 主脑决策

- 项目经理 Agent
- 意图识别
- 需求澄清
- 工作流路由器
- 自由/专业工作流判定
- 工作流编排引擎
- 执行计划生成
- 是否需要审批的判定
- 是否允许调用触手的最终决定权

### 3.3 状态与真相

- Task 真源
- Run 真源
- Step 真源
- 用户资料映射
- Session 真源
- Profile 真源
- 记忆系统
- 短期/中期/长期记忆
- route_decision
- dispatch_context
- approval_status
- audit_id
- trace_id
- idempotency_key

### 3.4 连续性与上下文

- active task 判定
- 上下文续写判断
- `_append_context_patch`
- 当前任务上下文吸收
- 对话到任务的连续性管理

### 3.5 主脑内部基础设施

- NATS 内部消息总线
- Tool Gateway 的决策层
- Runtime Router 的治理层
- 熔断/降级/切流的主决策

## 4. 允许外置的模块

以下内容应外置到 `/Users/xiaoyuge/Documents/XXL_ExternalConnection` 或其他独立部署位置。

- PDF 处理触手
- 搜索触手
- 浏览器自动化触手
- CRM 查询触手
- 订单查询触手
- 写作触手
- 天气触手
- future MCP 触手
- future skill 执行端
- future agent 执行端

这些模块的共同特点：

- 只做执行
- 不做权限裁决
- 不保存主脑状态真相
- 不保留核心记忆真相
- 不直接改主任务状态

## 5. 可留本地但必须轻量的能力

这些能力允许留在主脑，但必须保持只读、轻量、无高风险副作用。

- `task_status_skill`
- `task_list_skill`
- task view 聚合
- 结果说明包装
- 任务视图摘要

限制规则：

- 不做重执行
- 不访问高风险外部业务系统
- 不持有额外敏感凭证
- 不改变业务事实状态

## 6. 严格禁止外置的对象

以下对象禁止进入外置触手：

- `route_decision`
- `dispatch_context` 真源
- `approval_required` 的最终判定权
- `approval_status` 真源
- `audit_id`
- `trace_id`
- `idempotency_key`
- active task 状态真相
- 记忆真源
- task/run/step 真源
- 用户身份映射真源
- 平台会话真相
- 安全网关规则
- 权限判断规则

原因：

- 一旦这些对象被外置，主脑就失去安全收口能力
- 会造成权限扩散、状态漂移、审计断裂

## 7. 严格禁止留在主脑的对象

以下对象不应再回流到主脑重执行：

- 搜索执行实现
- PDF 解析实现
- PDF 转换实现
- 浏览器自动化执行实现
- 写作生成执行实现
- CRM/订单具体查询实现
- 外部工具 SDK 的业务实现层
- 各类重型 skill handler

原因：

- 会导致主脑变重
- 会扩大安全面
- 会破坏“封闭大脑、外置触手”原则

## 8. 当前项目的明确划分

### 8.1 主脑本地

- `backend/app/adapters/*`
- `backend/app/brain_core/reception/*`
- `backend/app/brain_core/routing/*`
- `backend/app/brain_core/orchestration/*`
- `backend/app/brain_core/task_view/*`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/security_gateway_service.py`
- `backend/app/services/memory_service.py`
- `backend/app/services/task_service.py`
- `backend/app/services/persistence_service.py`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/execution_gateway/*` 中的治理/策略部分
- `backend/app/schemas/*`
- `backend/app/db/*`

### 8.2 外置触手

- `search-mcp`
- `pdf-mcp`
- `writer-mcp`
- `weather-mcp`
- `order-query-mcp`
- `crm-query-mcp`
- 浏览器自动化 MCP
- 未来新增 MCP / skill / agent 执行端

## 9. 外置触手的硬限制

所有外置触手必须满足：

- 只能接收主脑下发的明确请求
- 不能自己判定是否允许执行
- 不能自己变更主任务状态
- 不能绕过主脑直接回平台
- 不能保存主脑记忆真相
- 不能持有长期主业务凭证
- 只能保留最小运行时上下文

## 10. 新模块接入判定规则

以后新增任何模块，必须先问两个问题：

1. 它是否在决定“能不能做”？
2. 它是否在保存“系统真相”？

判定：

- 任一答案是“是”，必须留在主脑本地。
- 两个答案都是否，且它只是执行具体能力，才允许外置。

## 11. 当前重构方向

当前重构必须坚持：

- `master_bot_service` 只保留为本地主脑兼容入口，不外置
- `brain_core` 才是真正的主脑内核
- `_append_context_patch` 这类上下文连续性逻辑只能做本地重构，不能外置
- 自由工作流与专业工作流的执行分流已经并入 `execution_gateway`，后续不得再把 runtime/builtin 主执行路径写回 service 层
- `execution_gateway` 只负责执行分流与治理，不负责审批、路由、记忆、任务真源
- route / orchestration / memory / task 真源必须继续向主脑内核收口
- 所有触手继续保持“外置执行、主脑裁决”

## 12. 最终一句话边界

- 主脑负责裁决
- 触手负责执行
- 真相留在主脑
- 能力放到触手
