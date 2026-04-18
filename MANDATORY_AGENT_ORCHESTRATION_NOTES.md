# 必备 Agent 编排注意事项

## 背景

这份文档用于整理“年底需要注册在大脑中的必备 Agent”相关架构注意事项。目标不是泛泛讨论 AI Agent，而是结合当前仓库已有实现，明确哪些能力应该作为业务 Agent 注册，哪些能力必须继续留在本地控制面。

当前拟定的 4 个必备 Agent：

1. 对话 Agent
2. 安全 Agent
3. 创建工作流 Agent
4. 记忆 Agent

结论先行：

- 这 4 个 Agent 的方向是合理的。
- 但它们本身还不够，必须再补齐编排、审批、执行边界、租户隔离、审计回放等控制面机制。
- “注册在大脑中”更适合解释为“注册为主脑可调度的运行时角色”，而不是继续把实现硬塞进 `brain_core` 内部。

## 一、当前仓库已经具备的基础

### 1. 主脑不是单一 Agent，而是接待 + 路由 + 项目经理包 + 编排

当前主脑入口已经拆成 reception、routing、manager、orchestration 等职责：

- `backend/app/brain_core/coordinator/service.py`
- `backend/app/brain_core/manager/service.py`
- `backend/app/brain_core/orchestration/service.py`

其中：

- `BrainCoordinatorService.build_dispatch_plan()` 负责统一接待和路由，生成 dispatch plan。
- `BrainManagerService.build_manager_packet()` 已经在产出“项目经理 Agent”语义的 manager packet。
- `build_execution_plan_snapshot()` 已经有 planner、aggregator、steps、fallback、route rationale 等编排概念。

这说明当前系统的主脑更接近“控制中枢”，而不是“一个万能对话 Agent”。

### 2. 当前仓库已经有强约束的架构边界

`backend/scripts/check_architecture_boundaries.py` 已明确限制：

- `brain_core` 禁止直接 import `app.tentacle_adapters`
- `brain_core` 禁止直接 import `app.services.master_bot_service`
- `brain_core` 禁止直接 import `app.services.workflow_execution_service`

因此后续新增必备 Agent 时，不能为了图快把执行逻辑继续堆进 `brain_core`，而应该走现有的 execution gateway / runtime / registry 边界。

### 3. 安全并不是空白区，而是已有本地安全网关

`backend/app/services/security_gateway_service.py` 已具备：

- rate limit
- auth scope guard
- prompt injection 检测
- content policy 改写放行
- audit
- realtime event
- block / penalty

这意味着安全 Agent 可以存在，但它不能替代本地安全网关作为最终裁决层。

### 4. 工作流规划已经有现成基础

`backend/app/services/professional_workflow_service.py` 里已经存在：

- `planner_agent`
- `system_agent`
- `document_agent`
- `delivery_agent`

并且已有：

- admission
- required capabilities
- permission requirement
- approval requirement
- execution scope
- runtime tool selection

这与“创建工作流 Agent”的目标高度接近，说明不用从零发明一套新的编排模型。

### 5. Agent 配置约定已经成型

`backend/app/services/agent_config_service.py` 当前约定的 Agent 配置目录包含：

- `agent.md`
- `soul.md`
- `tools.yaml`
- `memory_rules.md`
- `examples/`

这说明后续不应该只让记忆 Agent 带 `soul.md`，而应该把这套配置约定应用到所有必备 Agent。

### 6. 记忆与租户治理已经有底座

记忆：

- `backend/app/services/memory_service.py`

租户：

- `backend/app/services/tenancy_service.py`
- `docs/tenants.md`

当前仓库已经明确：

- 长期记忆只允许 `distillation` 写入
- 有大量 local-only 规则，阻止密钥、私钥、调试日志等进入中长期记忆
- 多租户目标是“先识别 tenant，再进入业务链路”

因此记忆 Agent 和工作流 Agent 天然都必须是 tenant-aware。

## 二、对 4 个必备 Agent 的逐项建议

### 1. 对话 Agent

定位建议：

- 负责接待、理解需求、澄清意图、补齐缺失上下文
- 负责把用户自然语言整理成结构化需求包
- 不负责高权限决策
- 不直接替代主脑调度层

原因：

- 当前主脑已经有 reception + routing + manager packet 机制
- manager packet 里已经有 `clarify_required`、`next_owner`、`handoff_summary`
- 如果让对话 Agent 同时兼任调度中枢，后期多 Agent 编排会失控

注意事项：

- 它的输出应是结构化需求，而不是直接调用执行工具
- 它应支持“追加上下文”和“继续澄清”，但不要直接改写工作流状态
- 它最好只拥有有限的只读能力和澄清能力

### 2. 安全 Agent

定位建议：

- 负责语义级安全审查
- 负责高风险请求解释和升级人工审批
- 负责对异常请求给出风险说明
- 不作为最终 allow / block 真相源

原因：

- 当前本地安全网关已经有硬拦截和审计机制
- `inspect_text_entrypoint()` 已串起 rate limit、auth scope、prompt injection、redaction、audit
- 安全 Agent 更适合做补充判断，而不是替换网关

注意事项：

- 最终拦截权仍归 `SecurityGatewayService`
- 安全 Agent 可以输出 `risk_label`、`risk_reason`、`approval_recommended`
- 对于 API Key、用户文件、特殊工作流、主脑架构、接入渠道信息等敏感内容，应尽量走本地规则优先
- 不要让安全 Agent 直接读取全部系统秘密配置

### 3. 创建工作流 Agent

定位建议：

- 更准确的名字应是“工作流设计 Agent”或“工作流提案 Agent”
- 它负责读取已启用能力，生成 workflow proposal
- 它负责产出节点拆解、依赖关系、审批点、回滚点
- 它不应自动发布 workflow

原因：

- 当前专业工作流服务已经有 admission、role split、governance、execution scope
- 当前仓库已经明确有 `approval_required` 和 `requires_permission`
- 工作流自动创建如果没有人工审批，风险极高

注意事项：

- 它只能读取 `enabled`、租户允许、权限允许的 skill/tool/mcp
- 它不能默认读取全部内部隐藏能力
- 它不能绕过 `approval_required`
- 它不能直接越过 execution gateway 调用外部系统

### 4. 记忆 Agent

定位建议：

- 负责人员画像蒸馏
- 负责偏好、决策、任务结果、关键事件的抽取
- 负责整理租户下的画像视图
- 不直接保存原始对话为长期记忆

原因：

- 当前 `MemoryService` 已限制长期记忆写入源为 `distillation`
- 记忆蒸馏会过滤 local-only 内容
- 记忆天然要区分 tenant scope 与 global scope

注意事项：

- `soul.md` 是 Agent 人格，不是用户画像
- 不要把“Agent 自我设定”和“租户人员画像”混存
- 记忆 Agent 应只把结构化、高置信、可留存信息写入中长期记忆
- 对文件片段、密钥、调试日志、临时上下文应默认不入长期记忆

## 三、除了 4 个 Agent 之外，必须补齐的 5 个控制面机制

### 1. 编排 / 项目经理层

这是当前最不能缺的一层。

建议职责：

- 接收对话 Agent 整理后的需求
- 判断是否需要继续澄清
- 判断走 direct agent 还是 workflow
- 维护 `next_owner`
- 管理 handoff summary

当前仓库里这部分语义已经存在于 `BrainManagerService`。

### 2. 审批治理

至少以下场景必须带审批：

- 创建新工作流
- 修改高权限工作流
- 执行写操作或跨系统动作
- 调用高风险外部能力
- 改写租户级关键配置

建议治理字段：

- `approval_required`
- `approval_status`
- `approver`
- `approval_comment`
- `approved_at`
- `rollback_plan`

### 3. 执行边界

必须坚持：

- 主脑做编排
- execution gateway 做执行入口
- tool / mcp / external agent 通过 registry 和 runtime 调用

不要让任何新增 Agent 直接穿透到：

- `tentacle_adapters`
- `workflow_execution_service`
- `master_bot_service`

### 4. 租户隔离

你前面已经明确系统未来是“卖给不同公司”，那么这几个必备 Agent 都必须受租户约束。

必须做到：

- 先识别 `tenant`
- 所有画像、任务、工作流、记忆、审计都带 `tenant_id`
- 工作流创建 Agent 只能读取当前租户可见能力
- 记忆 Agent 只能在当前租户作用域内整理画像

### 5. 审计与回放

年底一旦进入多 Agent 编排阶段，问题排查会非常依赖运行轨迹。

建议确保每次调度都有：

- trace id
- audit id
- route decision snapshot
- execution plan snapshot
- 审批记录
- 记忆蒸馏审计
- fallback 记录

## 四、最关键的风险点

### 1. 安全 Agent 不能替代本地安全真相源

如果让安全 Agent 直接决定 allow / block，会出现：

- 模型波动导致策略不稳定
- 无法保证审计一致性
- 对抗输入容易绕过

正确做法：

- 本地安全网关负责最终裁决
- 安全 Agent 提供补充判断和说明

### 2. 工作流创建 Agent 不能自动发布

否则很容易出现：

- 错误绑定高权限工具
- 生成循环工作流
- 未经审批直接接入外部系统
- 误伤租户隔离边界

正确做法：

- 只生成提案
- 强制人工审批
- 支持回滚

### 3. 记忆 Agent 不能直接保留原始敏感内容

仓库当前已经对以下内容有明显排斥：

- API Key
- Bot Token
- Bearer Token
- Password
- Private Key
- Session Secret
- 调试日志

因此记忆 Agent 必须遵守现有 local-only 和 distillation 规则。

### 4. `soul.md` 和人员画像必须分离

错误做法：

- 把 Agent 的人格配置当成用户画像保存
- 把用户偏好写回 `soul.md`

正确做法：

- `soul.md` 只描述 Agent 的人格、原则、语气
- 用户画像进入记忆层或租户画像体系

### 5. 防止 Agent 自触发循环

要特别限制：

- 谁可以创建任务
- 谁可以发起再编排
- 谁可以调用工作流创建 Agent
- 谁可以写回路由结果

否则很容易出现：

- 对话 Agent 触发创建工作流 Agent
- 创建工作流 Agent 再召回对话 Agent
- 安全 Agent 重复加审
- 记忆 Agent 因蒸馏事件再触发工作流

## 五、推荐的最小编排链路

建议按下面的链路设计：

1. 对话 Agent 接待并澄清需求
2. 本地安全网关做预检
3. 项目经理 / 路由层判断是 direct agent 还是 workflow
4. 创建工作流 Agent 只负责生成 workflow proposal
5. 人工审批
6. execution gateway / runtime 执行
7. 记忆 Agent 做蒸馏与画像更新
8. 审计、trace、运行摘要回写

一句话概括：

`对话负责理解，安全负责审查，项目经理负责分发，工作流 Agent 负责提案，执行层负责真正调用，记忆 Agent 负责蒸馏。`

## 六、建议的必备 Agent 注册规范

建议给每个必备 Agent 固定一套注册元数据：

### 1. 基础信息

- `agent_id`
- `agent_family`
- `version`
- `release_channel`
- `compatibility`
- `tenant_scope`

### 2. 能力声明

- `trigger_intents`
- `capabilities`
- `supported_inputs`
- `supported_outputs`
- `requires_permission`
- `approval_required`

### 3. 工具与执行限制

- 可用 `tools`
- 可用 `mcp`
- 是否允许直接执行
- 是否只允许提案
- 是否允许写记忆
- 是否允许发起再编排

### 4. 配置文件

- `agent.md`
- `soul.md`
- `tools.yaml`
- `memory_rules.md`
- `examples/`

### 5. 运行治理

- 默认版本
- fallback 版本
- rollout policy
- heartbeat
- health status
- 审计策略

## 七、最终建议

如果按当前仓库来推进，最推荐的落地方式不是“新增 4 个并列的超级 Agent”，而是：

- 保留现有主脑控制面
- 把 4 个必备 Agent 注册为主脑可编排的运行时角色
- 让安全、审批、执行边界、租户隔离继续留在本地控制面

这样做的好处是：

- 不破坏现有 `brain_core` 边界
- 能复用当前的 security gateway、memory governance、tool registry、external agent registry
- 后续做多租户和版本灰度时更稳

## 八、相关代码定位

- `backend/app/brain_core/coordinator/service.py`
- `backend/app/brain_core/manager/service.py`
- `backend/app/brain_core/orchestration/service.py`
- `backend/app/services/security_gateway_service.py`
- `backend/app/services/professional_workflow_service.py`
- `backend/app/services/skill_registry_service.py`
- `backend/app/services/tool_source_service.py`
- `backend/app/services/agent_config_service.py`
- `backend/app/services/external_agent_registry_service.py`
- `backend/app/services/memory_service.py`
- `backend/app/services/tenancy_service.py`
- `backend/scripts/check_architecture_boundaries.py`
- `docs/tenants.md`
