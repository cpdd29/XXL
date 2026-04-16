# Tenants Plan

## 目标

为当前 WorkBot 项目补齐多租户能力，支持不同企业分别接入不同渠道、拥有各自独立的工作流、用户、Agent 配置、消息数据与审计数据，避免串租户。

一句话原则：

- 所有外部消息必须先识别 `tenant`
- 所有后续链路必须在 `tenant` 作用域内执行

## 适用范围

本清单聚焦当前项目的“基础工作流闭环 + Agent 调配 + 渠道接入”场景，不展开后续计费、套餐、发票等 SaaS 商业层能力。

## 核心设计原则

### 1. 先识别租户，再做任何业务处理

- webhook 入站时先解析 `tenant_key` 或等价租户标识
- 未识别租户时直接拒绝请求，不进入统一消息标准化
- `tenant_id` 必须成为后续所有对象的基础字段

### 2. 配置分层

- 平台级配置：系统默认值、平台管理员、默认 Agent 模板、默认模型供应商配置
- 租户级配置：渠道接入、工作流、用户绑定、会话、记忆、审计日志、租户 Agent 覆盖配置
- 继承策略：优先租户配置，缺失时回退平台默认

### 3. 默认隔离优先

- 数据隔离优先于功能复用
- 查询必须默认按 `tenant_id` 过滤
- 平台管理员可跨租户查看；租户管理员只能操作所属租户

### 4. 先做显式租户路由，不做隐式猜测

推荐 webhook 路径：

- `/api/webhooks/{tenant_key}/telegram`
- `/api/webhooks/{tenant_key}/dingtalk`
- `/api/webhooks/{tenant_key}/wecom`
- `/api/webhooks/{tenant_key}/feishu`

不要一开始依赖“根据 secret 或 bot token 反推 tenant”作为唯一方案。

## 当前系统需要改造的关键点

### A. 渠道接入配置当前仍偏全局

现状：

- 当前渠道接入配置页已经存在
- 但其本质仍是平台级配置，不适合直接承载多租户

改造要求：

- 将渠道接入配置从全局设置迁移为租户设置
- 每个租户独立维护 Telegram / DingTalk / WeCom / Feishu 的配置
- 前端配置页必须增加租户上下文

### B. 工作流当前需要租户隔离

现状：

- 工作流已可创建与执行
- 但还未显式声明归属租户

改造要求：

- workflow 必须带 `tenant_id`
- webhook / message / schedule 触发时只在当前租户范围内匹配 workflow
- workflow run 必须带 `tenant_id`

### C. 用户、消息、记忆当前需要租户作用域

改造要求：

- 用户绑定必须区分租户
- 同一外部平台账号在不同租户下允许存在不同绑定关系
- 消息、任务、记忆、审计日志都必须带 `tenant_id`

### D. Agent 配置当前需要“平台默认 + 租户覆盖”

改造要求：

- `Agent API 配置` 继续保留平台默认能力
- 新增租户级 Agent 配置覆盖层
- 运行时解析 Agent 配置时，按“租户优先，平台兜底”读取

## 数据模型设计清单

### 1. 租户主模型

新增：

- `tenants`

建议字段：

- `id`
- `key`
- `name`
- `status`
- `created_at`
- `updated_at`
- `archived_at`

### 2. 租户成员关系

新增：

- `tenant_memberships`

建议字段：

- `id`
- `tenant_id`
- `user_id`
- `role`
- `status`
- `joined_at`

角色建议：

- `platform_admin`
- `tenant_admin`
- `tenant_operator`
- `tenant_viewer`

### 3. 租户渠道接入配置

新增：

- `tenant_channel_integrations`

建议字段：

- `id`
- `tenant_id`
- `channel`
- `enabled`
- `settings_payload`
- `updated_by`
- `updated_at`

说明：

- `settings_payload` 存加密后的配置
- 每个租户每个渠道一条记录，或一租户一整包 payload，二选一即可

### 4. 业务数据补 `tenant_id`

必须补到这些对象：

- `users` 的租户绑定关系表或等价映射
- `messages`
- `tasks`
- `task_steps`
- `workflow_runs`
- `memory_entries`
- `audit_logs`
- `operational_logs`
- `security_incidents`

### 5. 工作流与 Agent 配置

必须补到这些对象：

- `workflows`
- `workflow_triggers`
- `agent_bindings`
- `agent_runtime_preferences`
- `agent_api_overrides`

## 接口与后端改造任务

## P0: 多租户最小闭环

### 1. 租户基础表与租户上下文 `[todo]`

任务：

- 新增 `tenants`、`tenant_memberships`
- 增加 `TenantContext` 解析能力
- 统一支持通过 `tenant_key` / `tenant_id` 进入租户作用域

验收：

- 平台可创建租户
- 请求链路中可解析出明确租户上下文

### 2. webhook 路由租户化 `[todo]`

任务：

- 将 webhook 路径升级为 `/api/webhooks/{tenant_key}/{channel}`
- webhook secret 改为租户级读取
- webhook 守卫、鉴权、审计日志写入 `tenant_id`

验收：

- A 租户钉钉消息不会进入 B 租户链路
- 错误租户路径或 secret 直接拒绝

### 3. UnifiedMessage / Task / WorkflowRun 补 `tenant_id` `[todo]`

任务：

- `UnifiedMessage` 增加 `tenant_id`
- task 创建时带入 `tenant_id`
- workflow run / dispatch context / result 都带 `tenant_id`

验收：

- 从入站消息到任务执行到回传，全链路可看到同一 `tenant_id`

### 4. 工作流匹配改为租户内匹配 `[todo]`

任务：

- workflow 查询接口默认按 `tenant_id` 过滤
- Master Bot 路由只查当前租户可用 workflow
- direct agent fallback 也只能使用当前租户可用配置

验收：

- 不同租户可配置不同 workflow，互不干扰

### 5. 租户级渠道接入配置中心 `[todo]`

任务：

- 将现有全局渠道设置下沉为租户设置
- 新增租户级渠道配置读写接口
- 运行时出站/入站 adapter 改读租户配置

验收：

- 租户 A 可接钉钉
- 租户 B 可接企业微信
- 两者互不影响

## P1: 数据隔离与权限收口

### 6. 用户绑定租户化 `[todo]`

任务：

- 用户平台账号绑定增加 `tenant_id`
- 同一平台账号允许在不同租户拥有独立关系
- 用户画像查询默认限制在当前租户

验收：

- 同名用户在不同租户不会串画像

### 7. 记忆系统租户化 `[todo]`

任务：

- 短期记忆、中期记忆、长期记忆都带 `tenant_id`
- 检索时必须按 `tenant_id` 过滤
- distill/summary 任务按租户范围运行

验收：

- A 租户历史对话不会出现在 B 租户检索结果中

### 8. 审计与安全日志租户化 `[todo]`

任务：

- 审计日志、操作日志、安全事件增加 `tenant_id`
- 安全看板支持租户过滤
- 平台管理员支持跨租户查看，租户管理员仅看本租户

验收：

- 审计日志可按租户准确筛选

### 9. RBAC 升级为平台级 + 租户级 `[todo]`

任务：

- 平台管理员与租户管理员权限分层
- 设置、工作流、用户管理、渠道配置都受租户边界限制
- 所有写操作校验 membership

验收：

- 非所属租户用户无法修改他租户配置

## P1: 产品与前端改造

### 10. 租户管理页面 `[todo]`

任务：

- 新增租户列表页
- 支持创建租户、启停租户、查看租户基础信息
- 支持租户成员管理

验收：

- 平台管理员可在 UI 中创建并管理租户

### 11. 前端租户切换器 `[todo]`

任务：

- 在全局布局中加入当前租户选择器
- 将当前租户写入路由、状态或请求头
- 页面切换租户时自动刷新租户级数据

验收：

- 切换租户后，工作流、用户、渠道配置同步切换

### 12. 渠道接入配置页租户化 `[todo]`

任务：

- 将现有“设置 > 渠道接入配置”升级为“当前租户的渠道接入配置”
- 页面明确区分入站配置与出站配置
- 对 Telegram / DingTalk / WeCom / Feishu 展示租户专属配置

验收：

- 在不同租户下进入同一页面，看到的是不同配置

### 13. 工作流页面租户化 `[todo]`

任务：

- 工作流列表与编辑器增加租户上下文
- 只允许查看和编辑当前租户 workflow
- workflow 触发入口和调试入口都带租户信息

验收：

- 不会看到其他租户工作流

## P2: Agent 与配置继承

### 14. Agent API 配置支持租户覆盖 `[todo]`

任务：

- 平台继续维护默认供应商配置
- 租户可覆盖自己的 OpenAI / Claude / Codex / Kimi / MiniMax 等配置
- 运行时调用模型时优先读租户覆盖

验收：

- 不同租户可使用不同模型供应商与密钥

### 15. Agent 路由与调度租户化 `[todo]`

任务：

- Agent 可见性增加租户边界
- 调度器只调度当前租户允许的 Agent
- heartbeat / operational log 关联租户

验收：

- 调度器不会跨租户调用不该使用的 Agent

## P2: 迁移与兼容

### 16. 全局配置迁移到租户默认空间 `[todo]`

任务：

- 设计默认租户或“平台演示租户”
- 将现有全局渠道配置迁移进默认租户
- 将现有 workflow / users / tasks / logs 回填到默认租户

验收：

- 老数据在迁移后仍可使用

### 17. 旧接口兼容层 `[todo]`

任务：

- 为旧 webhook 路由保留过渡期兼容
- 为旧设置接口返回明确弃用提示
- 后端日志记录旧入口调用情况

验收：

- 升级过程中旧联调脚本不至于立即全部失效

## 运行时设计建议

### 1. 请求链路

建议统一为：

`Inbound Channel -> Resolve Tenant -> Auth/Guard -> Normalize UnifiedMessage -> Route Workflow/Agent -> Execute -> Outbound By Tenant`

### 2. 配置读取链路

建议统一为：

`tenant override -> platform default -> hardcoded fallback`

### 3. 钉钉特殊说明

- 钉钉出站优先依赖会话级 `sessionWebhook`
- 租户级配置只决定该租户是否允许接入、secret 如何校验、默认 API 地址等
- 不应误以为“全局配一个钉钉 webhook key”就能替代会话回传

### 4. 用户标识说明

- 同一 `platform_user_id` 不应跨租户直接共享
- 推荐唯一键包含：`tenant_id + channel + platform_user_id`

## 实施顺序建议

### 第一阶段：最小闭环

1. 建租户表与 membership
2. webhook 路径租户化
3. 消息 / 任务 / workflow run 补 `tenant_id`
4. 工作流查询按租户过滤
5. 渠道接入配置改为租户级

### 第二阶段：数据与权限收口

1. 用户绑定租户化
2. 记忆租户化
3. 审计日志租户化
4. RBAC 升级

### 第三阶段：产品与体验

1. 租户管理页面
2. 全局租户切换器
3. 渠道配置页租户化
4. 工作流页面租户化

### 第四阶段：高级能力

1. Agent API 租户覆盖
2. Agent 调度租户化
3. 历史数据迁移与兼容层

## 建议的最小验收场景

### 场景 1：双租户双渠道

- 租户 A 配置钉钉
- 租户 B 配置企业微信
- 两边分别发消息
- 各自触发自己的工作流并独立回传

### 场景 2：相同用户名不串租户

- A、B 两个租户都有“张三”
- 两边都发消息
- 用户画像、记忆、任务互不混淆

### 场景 3：租户管理员权限隔离

- 租户 A 管理员不能查看或修改租户 B 配置
- 平台管理员可跨租户查看

## 当前推荐结论

当前项目要做多租户，最先动的不是前端页面，而是：

1. `tenant` 基础模型
2. webhook 路由租户化
3. 全链路 `tenant_id`
4. 租户级渠道配置
5. 租户内工作流匹配

如果这五步没完成，多租户只是表面 UI，多数核心链路仍会串租户。

## 开发任务分解表

## Milestone 1: 多租户最小可运行闭环

目标：

- 两个租户可接入不同渠道
- 两个租户可跑各自 workflow
- 消息、任务、回传不串租户

任务拆分：

### M1-1. 数据库与持久化

- 新增 `tenants`
- 新增 `tenant_memberships`
- 为 `messages / tasks / workflow_runs / audit_logs / operational_logs` 增加 `tenant_id`
- 给关键表增加索引：`tenant_id`、`tenant_id + status`、`tenant_id + created_at`

建议验收：

- 所有新表和新字段具备 migration
- 数据查询默认支持按租户过滤

### M1-2. 租户解析与请求上下文

- 新增 `TenantContext`
- 在 webhook、REST API、后台页面请求链中统一解析租户
- 统一在 request state 或等价上下文里传递 `tenant_id`

建议验收：

- 任一租户请求都可在日志中看到 `tenant_id`

### M1-3. webhook 多租户化

- 新增租户化 webhook 路径
- 所有渠道 secret 改为从租户配置读取
- webhook guard 审计增加 `tenant_id`

建议验收：

- A 租户用钉钉 secret 调 B 租户 webhook 必须失败

### M1-4. 主链路补租户字段

- `UnifiedMessage` 增加 `tenant_id`
- `message_ingestion_service` 全链路透传 `tenant_id`
- `task_service / workflow_service / dispatch_context / result` 全部透传 `tenant_id`

建议验收：

- 一个任务从消息到回传的所有记录都能串出同一租户

### M1-5. workflow 与回传租户化

- workflow 查询默认带租户过滤
- workflow trigger 只命中当前租户 workflow
- outbound 回传按租户读取配置与渠道能力

建议验收：

- A 租户 workflow 永远不会处理 B 租户消息

## Milestone 2: 配置中心与前端可操作

目标：

- 平台管理员可创建租户
- 租户管理员可维护自己租户的渠道与工作流
- 前端有明确租户上下文

任务拆分：

### M2-1. 租户管理 API

- 新增租户列表、详情、创建、启停接口
- 新增租户成员管理接口
- 平台管理员专用权限校验

建议验收：

- 平台管理员可创建两个租户并给成员授权

### M2-2. 租户级渠道配置 API

- 新增 `GET /api/tenants/{tenant_id}/channel-integrations`
- 新增 `PUT /api/tenants/{tenant_id}/channel-integrations`
- 或等价的“当前租户设置接口”

建议验收：

- 两个租户保存不同渠道配置后，运行时立即生效

### M2-3. 前端租户切换器

- 增加全局租户选择器
- 当前租户进入查询 key、请求 header 或路由参数
- 切换租户后缓存正确失效

建议验收：

- 切换租户后，页面数据全部刷新，不残留旧租户缓存

### M2-4. 渠道接入配置页租户化

- 将当前页面从平台设置改为租户设置
- 明确显示当前租户名称
- 保存接口切到租户作用域

建议验收：

- A、B 两个租户页面显示不同配置，互不影响

### M2-5. 工作流页面租户化

- 列表、详情、编辑器全带租户上下文
- 创建 workflow 时写入 `tenant_id`
- 编辑和删除时校验租户归属

建议验收：

- 一个租户看不到另一个租户的 workflow

## Milestone 3: 数据隔离与权限收口

目标：

- 用户、记忆、审计、安全都完成租户隔离
- 平台权限与租户权限完全分层

任务拆分：

### M3-1. 用户绑定租户化

- 外部平台账号绑定表改为包含 `tenant_id`
- 用户资料接口按当前租户读取绑定
- 人工绑定/解绑接口按租户校验

### M3-2. 记忆租户化

- 短期会话、长期记忆、向量检索都补 `tenant_id`
- retrieval / distill / weekly summary 都按租户处理

### M3-3. 审计与安全租户化

- 审计日志、安全事件、限流记录补 `tenant_id`
- 安全中心查询接口支持租户过滤

### M3-4. RBAC 分层

- 平台管理员：跨租户管理
- 租户管理员：本租户管理
- 租户操作员：本租户使用
- 租户查看者：只读

建议验收：

- 任意跨租户越权操作都返回明确拒绝

## Milestone 4: Agent 与配置继承

目标：

- 不同租户可使用不同模型供应商与 Agent 组合

任务拆分：

### M4-1. Agent API 租户覆盖层

- 平台默认配置保留
- 租户级 override 独立存储
- 运行时按“租户优先，平台兜底”解析

### M4-2. Agent 可见性与调度租户化

- agent binding 加租户维度
- dispatcher 只调度当前租户允许的 agent
- heartbeat / runtime metrics 可按租户查看

### M4-3. 协同链路租户透传

- multi-agent execution plan 增加 `tenant_id`
- 子任务、子结果聚合、协议消息都透传租户

## 数据库迁移任务清单

### DDL 任务 `[todo]`

- 新建 `tenants`
- 新建 `tenant_memberships`
- 新建 `tenant_channel_integrations`
- 新建 `tenant_agent_api_overrides`
- 为业务表补 `tenant_id`
- 为关键表建立租户索引
- 为平台账号绑定建立唯一约束：`tenant_id + channel + platform_user_id`

### 数据迁移任务 `[todo]`

- 设计默认租户，例如 `default` 或 `demo`
- 将现有全局配置落到默认租户
- 将历史 workflow、task、run、log、message 全量回填到默认租户
- 为无法识别归属的数据提供迁移日志和人工处理列表

### 兼容任务 `[todo]`

- 旧 webhook 路由兼容到租户默认空间
- 旧设置接口返回弃用提示
- migration 后保证现有 demo 环境可继续运行

## 接口设计任务清单

### 平台级接口 `[todo]`

- `GET /api/tenants`
- `POST /api/tenants`
- `GET /api/tenants/{tenant_id}`
- `PATCH /api/tenants/{tenant_id}`
- `GET /api/tenants/{tenant_id}/members`
- `POST /api/tenants/{tenant_id}/members`
- `PATCH /api/tenants/{tenant_id}/members/{membership_id}`

### 租户级配置接口 `[todo]`

- `GET /api/tenants/{tenant_id}/settings/channel-integrations`
- `PUT /api/tenants/{tenant_id}/settings/channel-integrations`
- `GET /api/tenants/{tenant_id}/settings/agent-api`
- `PUT /api/tenants/{tenant_id}/settings/agent-api`

### 租户级业务接口 `[todo]`

- workflow 列表、详情、创建、更新、删除接口按租户过滤
- users 列表、详情、绑定、解绑接口按租户过滤
- dashboard / security / audit / operational logs 接口按租户过滤

## 前端页面任务清单

### 平台管理区 `[todo]`

- 租户列表页
- 租户详情页
- 租户成员管理页

### 租户工作区 `[todo]`

- 顶部租户切换器
- 租户级渠道接入配置页
- 租户级 Agent API 配置页
- 租户级工作流列表与编辑器
- 租户级用户管理页
- 租户级安全中心视图

### 状态管理与缓存 `[todo]`

- React Query key 增加 `tenantId`
- 切换租户时失效相关缓存
- 避免“租户 A 数据显示在租户 B 页面”的缓存污染

## 测试任务清单

### 单元测试 `[todo]`

- 租户上下文解析测试
- 租户配置读取优先级测试
- workflow 按租户过滤测试
- 用户绑定唯一约束测试
- RBAC 跨租户拒绝测试

### 集成测试 `[todo]`

- 双租户双渠道 webhook 入站测试
- 双租户 workflow 隔离测试
- 双租户消息回传隔离测试
- 双租户记忆检索隔离测试

### 前端测试 `[todo]`

- 租户切换器行为测试
- 设置页在切换租户后的数据刷新测试
- query cache 隔离测试

### 回归测试 `[todo]`

- 单租户旧路径兼容测试
- 默认租户迁移后原功能可用性测试

## 不建议现在先做的内容

这些能力可以留到多租户主闭环完成之后：

- 计费与套餐
- 租户级资源配额
- 企业品牌主题定制
- 多租户自定义域名
- 复杂组织架构与部门树
- 跨租户共享知识库

## 推荐开发顺序

最优先顺序：

1. 租户表与租户上下文
2. webhook 路由租户化
3. 主链路对象补 `tenant_id`
4. workflow 查询与执行租户化
5. 租户级渠道配置
6. 前端租户切换器
7. 渠道配置页和工作流页租户化
8. 用户绑定与记忆租户化
9. RBAC 收口
10. Agent API 覆盖与 Agent 调度租户化

## 当前建议的一句话判断

如果你现在只想尽快支持“不同客户接不同渠道并各自对话”，那第一期只要完成：

1. 租户模型
2. 租户 webhook 路由
3. 全链路 `tenant_id`
4. 租户级渠道配置
5. 租户内 workflow 匹配

这五项完成后，就已经是一个真实可用的多租户基础版本了。
