# 接待层全链路联调清单

更新时间：2026-05-03

## 1. 目标

本清单用于把当前接待层做一次完整收口，确认以下主链已经稳定：

`渠道消息 -> 输入安全监听 -> 客户准入 -> Hermes 接待 -> 输出安全监听 -> 渠道回复 / 转任务入平台`

联调阶段不处理以下范围：

- 不新增 Hermes 能力
- 不新增需求分发 Agent 编排
- 不恢复“转人工”能力

## 2. 当前主规则

1. 平台负责所有渠道输入与输出，Hermes 不直接接渠道。
2. 客户进入 Hermes 前，必须先经过客户准入确认层。
3. 安全监听只负责监听、阻断、审计，不负责代替 Hermes 回复。
4. Hermes 只输出两类正式结果：
   - `stay_in_reception`：继续接待
   - `dispatch_task`：转任务
5. 任务型结果进入平台任务中心；非任务型结果由平台回传到渠道。
6. 人员画像是平台长期记忆，Hermes 当前按 `platform_stateless` 模式运行，不持有租户长期记忆。

## 3. 联调范围

### 3.1 页面

- `/intake`
- `/tasks`
- `/settings/admission-template`
- `/settings/intake-security`
- `/settings/channel-integration`
- `/settings/tenants`

### 3.2 后端接口

- `GET /api/intake/overview`
- `GET /api/intake/traces/{trace_id}`
- `WS /api/intake/realtime`
- `GET /api/customer-access/settings`
- `PUT /api/customer-access/settings`
- `GET /api/tasks`
- `WS /api/tasks/realtime`
- 渠道回调入口

### 3.3 关键模块

- `backend/app/modules/reception/channel_ingress`
- `backend/app/modules/reception/customer_access`
- `backend/app/modules/reception/security_monitor`
- `backend/app/modules/reception/agent_entry/hermes_reception_agent_service.py`
- `backend/app/modules/reception/application/message_ingestion_service.py`
- `backend/app/modules/reception/application/intake_console_service.py`
- `backend/app/modules/dispatch/application/task_service.py`
- `reception/modules/intake/pages/intake-layer-page.tsx`
- `reception/modules/dispatch/pages/tasks-page.tsx`

## 4. 测试数据准备

联调前至少准备以下数据：

1. 1 个已绑定渠道的试点租户
2. 1 个该租户下可用的服务识别码
3. 1 个未注册客户渠道账号
4. 1 个已注册客户渠道账号
5. 1 个 Hermes 外接智能体配置
6. 1 套输入安全监听规则
7. 1 套输出安全监听规则
8. 至少 1 条租户知识库数据与 1 条通用知识库数据

## 5. 联调场景

### 5.1 场景 A：未注册客户首次准入

操作：

1. 从渠道发送首条消息
2. 平台返回准入模板
3. 客户按模板填写：
   - 服务识别码
   - 用户名称
   - 用户电话号

期望：

1. `/intake` 出现 `pending_verification -> bound` 的准入事件
2. 租户管理中新增或绑定对应人员画像
3. 后续消息不再重复要求填写模板

### 5.2 场景 B：已注册客户直接接待

操作：

1. 从已注册客户渠道发送消息
2. 仅填写服务识别码，或直接从已绑定链路发起消息

期望：

1. 平台直接识别租户与客户
2. Hermes 进入正式接待
3. `/intake` 中可看到当前租户、客户、渠道、当前阶段

### 5.3 场景 C：普通问答接待

操作：

1. 发送查询型消息，例如 FAQ、产品咨询、知识问答

期望：

1. Hermes 返回正常接待回复
2. `task_signal=stay_in_reception`
3. `/intake` 中显示 `接待回复`
4. 不创建任务中心任务

### 5.4 场景 D：需求型消息转任务

操作：

1. 发送明确需求型消息，例如做官网、做方案、写文档、出 PPT

期望：

1. Hermes 识别为任务型
2. `task_signal=dispatch_task`
3. `/intake` 中当前阶段显示 `已转任务`
4. `/tasks` 中出现新任务
5. `/api/tasks/realtime` 可实时看到任务刷新

### 5.5 场景 E：知识命中辅助接待

操作：

1. 发送一个需要租户知识库支持的问题

期望：

1. Hermes 请求前已注入平台返回的知识命中
2. `/intake` 中显示本次 `knowledge_hits`
3. 回复内容体现租户专用知识优先，其次通用知识
4. 知识命中失败时，不应阻断主接待链

### 5.6 场景 F：输入安全阻断

操作：

1. 发送高危内容，例如明显 Prompt 注入、XSS、异常频控样本

期望：

1. Hermes 不被调用
2. 渠道收到阻断类结果
3. `/intake` 记录 `安全阻断`
4. 审计中可查看命中规则、阻断方向、阻断原因

### 5.7 场景 G：Hermes 输出安全阻断

操作：

1. 构造会导致 Hermes 输出违规内容的测试样本

期望：

1. 平台监听 Hermes 输出
2. 命中风险时直接阻断，不下发到渠道
3. `/intake` 记录输出侧阻断事件
4. 审计中保留风险报告

## 6. 运营台核对项

在 `/intake` 必须能看清以下信息：

1. 当前 Hermes 正在服务哪个租户
2. 当前 Hermes 正在服务哪个客户
3. 当前消息来自哪个渠道
4. 当前阶段是接待中还是已转任务
5. 本次是否命中知识库，命中了哪些摘要
6. 本次是否被输入侧或输出侧安全监听阻断
7. 当前关联任务是否已创建成功

## 7. 通过标准

满足以下条件，视为接待层联调通过：

1. 查询类消息稳定回复，不重复回复
2. 需求类消息稳定建单，不漏单
3. 未注册客户能稳定进入准入模板流程
4. 已注册客户能稳定跳过重复注册
5. 安全监听对输入与输出都可生效
6. `/intake` 与 `/tasks` 的实时数据可观察
7. 不出现跨租户画像串用、知识串用、任务串用

## 8. 联调后下一步

接待层收口完成后，再进入以下开发：

1. Hermes 分流规则固化与样本沉淀
2. 安全监听规则可视化配置
3. 需求分发 Agent 正式接入
4. 接待层与任务中心的 NATS 事件闭环
