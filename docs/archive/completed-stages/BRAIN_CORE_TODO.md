# Brain Core Task List

更新时间：2026-04-14
目标：把当前“已具备接入层 + 安全网关 + 基础任务/工作流能力”的框架，推进成“主脑封闭、触手外置、协议统一”的正式主脑。

当前状态补充：

- 开发包 A-D 已完成，`manager_packet / route_decision / execution_plan / fallback history` 已贯通主链。
- 主脑执行计划可视化已落地到协作页，运行态 `execution_plan_snapshot` 已能从 task/run 真源读出。
- 当前主开发主线已切换到 `NEXT_STAGE_3_TODO.md` 的 `Package M：主脑主链收口`。

## 一、主脑边界红线

以下能力必须保留在本地主脑，禁止外置到 `XXL_ExternalConnection` 或任何远端触手：

- 最终接单权
- 最终路由裁决权
- 最终放行/拦截裁决权
- 审计真源
- 处罚状态真源
- 任务真源
- run 真源
- step 真源
- 记忆真源
- manager_packet 真源
- brain_dispatch_summary 真源
- 安全策略真源

以下能力可以外接，但只能以“被主脑调度的执行单元”存在：

- MCP 服务
- Skill 服务
- 外接 Agent Worker
- HTTP 专业服务
- 浏览器自动化
- 搜索/抓取
- 文档处理
- CRM/ERP/知识库查询

原则：

- 大脑封闭：所有决策都在本地完成
- 触手外置：所有执行能力都可以远端部署
- 协议统一：主脑只认统一注册协议、能力协议、调度协议、回传协议

## 二、目标架构拆分

### 1. 本地主脑层

职责：

- 接收统一消息对象 `UnifiedMessage`
- 安全网关五层处理
- 项目经理 Agent 接待/澄清/确认/继续
- 路由器做任务形态判断
- 编排引擎生成执行计划
- 任务中心保存事实状态
- 记忆系统注入上下文
- 调度器把执行任务发给外接触手
- 审计中心记录全过程

代码层建议：

- `backend/app/brain_core/reception/`
  - 接待态
  - 对话澄清
  - 继续会话
- `backend/app/brain_core/manager/`
  - 项目经理 Agent
  - `manager_packet`
  - 需求澄清/确认/接单
- `backend/app/brain_core/routing/`
  - 自由工作流/专业工作流/直答路由
  - 技能/触手选择
- `backend/app/brain_core/orchestration/`
  - 执行计划
  - 编排调度
  - 失败回退
- `backend/app/brain_core/security/`
  - 本地安全裁决
  - 审计落地
- `backend/app/services/task_service.py`
  - task 真源
- `backend/app/services/workflow_execution_service.py`
  - run 真源
- `backend/app/services/collaboration_service.py`
  - 协作真源
- `backend/app/services/message_ingestion_service.py`
  - 统一入口收口

### 2. 外接触手层

职责：

- 不做裁决
- 不保留主状态
- 只接受主脑调度
- 回传结构化结果
- 可以独立部署到别的服务器

建议归并到：

- `/Users/xiaoyuge/Documents/XXL_ExternalConnection/agents/`
- `/Users/xiaoyuge/Documents/XXL_ExternalConnection/skills/`
- `/Users/xiaoyuge/Documents/XXL_ExternalConnection/mcp/`
- `/Users/xiaoyuge/Documents/XXL_ExternalConnection/connectors/`

## 三、开发顺序

## P0 主脑主线必须先完成

- [x] 项目经理 Agent 正式闭环
- [x] 路由器升级为统一调度中枢
- [x] 外接 Skill 注册中心
- [x] 外接 Agent 注册中心
- [x] 任务中心状态机统一
- [x] 记忆系统接入项目经理和路由器
- [x] 主脑内 NATS 事件协议规范化

## P1 高价值增强

- [x] 主脑执行计划可视化
- [x] 外接触手健康检查与摘除
- [x] 外接能力版本管理
- [x] 调度失败自动回退
- [x] 多触手并发编排
- [x] 主脑对外接触手的租约/心跳机制

## P2 体系化建设

- [x] 主脑 RBAC 分层
- [x] 主脑配置中心治理
- [x] 主脑调度成本统计
- [x] 主脑 SLA 指标
- [x] 灰度切换与回滚
- [x] 主脑/触手跨机房容灾预案

## 四、开发包拆分

### 开发包 A：项目经理 Agent 闭环

目标：

- 所有消息先进入项目经理 Agent
- 项目经理决定：直接回复 / 澄清 / 建任务 / 进入工作流

范围：

- `backend/app/brain_core/manager/`
- `backend/app/brain_core/reception/`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/schemas/messages.py`
- `backend/app/schemas/tasks.py`

要做的事：

- [x] 明确“接待态”和“执行态”
- [x] 建立需求澄清状态机
- [x] 建立确认/取消/继续状态机
- [x] 所有任务生成统一 `manager_packet`
- [x] `manager_packet` 写入 task / run / collaboration / logs
- [x] 项目经理结论接入前端接待页和协作页

验收标准：

- 用户每条消息都能看到项目经理动作
- 澄清型消息不会误入执行
- 专业工作流必须先确认再执行
- 所有入口都有可追溯 `manager_packet`

### 开发包 B：统一路由与调度中枢

目标：

- 主脑能统一决定“由谁做、怎么做、失败怎么办”

范围：

- `backend/app/brain_core/routing/`
- `backend/app/brain_core/orchestration/`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/services/agent_execution_service.py`

要做的事：

- [x] 统一三类路由：直答 / 自由工作流 / 专业工作流
- [x] 路由理由结构化
- [x] 执行计划结构化
- [x] 失败回退策略
- [x] 单触手、多触手、串并行调度
- [x] 结果汇总与交付协议

验收标准：

- 任意任务都能解释为什么走这个路由
- 任意执行失败都能看到回退决策
- 调度链路里没有“外接能力自己决定下一步”的情况

### 开发包 C：外接 Skill / Agent 注册中心

目标：

- 外接能力不再靠目录扫描和手工认文件，而是有正式注册、发现、心跳、能力声明

范围：

- `backend/app/services/agent_service.py`
- `backend/app/services/master_bot_service.py`
- `backend/app/services/tool_catalog_adapters/`
- 新增：
  - `backend/app/services/external_skill_registry_service.py`
  - `backend/app/services/external_agent_registry_service.py`

要做的事：

- [x] Skill 注册协议
- [x] Agent 注册协议
- [x] 能力清单 schema
- [x] 健康检查
- [x] 心跳/租约
- [x] 超时摘除
- [x] 版本字段
- [x] 远端地址与调用方式标准化

验收标准：

- 主脑可查看所有在线外接 Skill/Agent
- 下线的外接能力不会继续被调度
- 主脑只基于注册信息调度，不依赖本地目录结构

### 开发包 D：任务中心与记忆接入

目标：

- task/run/step/collaboration/memory 形成统一事实层

范围：

- `backend/app/services/task_service.py`
- `backend/app/services/collaboration_service.py`
- `backend/app/services/workflow_execution_service.py`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/memory_*`

要做的事：

- [x] task/run/step 状态机统一
- [x] brain_dispatch_summary 统一写入
- [x] 记忆注入白名单
- [x] 短期/中期/长期记忆使用边界
- [x] 上下文补丁审计化
- [x] 记忆命中数和来源可观测

验收标准：

- 每条任务都能追到执行 run、step、协作记录
- 每次记忆注入都能看到来源和摘要
- 记忆不会绕过安全与项目经理直接驱动执行

## 五、代码层明确分工

### 1. `message_ingestion_service`

干什么：

- 统一消息入口
- 把平台消息转成主脑内部处理对象
- 调用安全网关
- 把消息送进项目经理 Agent

不干什么：

- 不直接决定外接触手执行细节
- 不直接保存复杂调度策略

### 2. `brain_core/manager`

干什么：

- 接待
- 澄清
- 判断是否建任务
- 生成 `manager_packet`

不干什么：

- 不自己执行具体业务
- 不直接调用外接能力

### 3. `brain_core/routing`

干什么：

- 根据任务目标选择直答/工作流/触手
- 生成结构化路由结论

不干什么：

- 不保存任务真源
- 不做最终审计收口

### 4. `brain_core/orchestration`

干什么：

- 把路由结论编排成执行计划
- 串行/并行/回退

不干什么：

- 不绕过任务中心直接修改状态

### 5. `task_service`

干什么：

- 管 task 真源
- 管 task 生命周期

不干什么：

- 不直接做策略判断

### 6. `workflow_execution_service`

干什么：

- 管 run 真源
- 管执行节点状态

不干什么：

- 不替代项目经理做接待和澄清

### 7. `collaboration_service`

干什么：

- 聚合 task / run / logs / manager_packet
- 给前端协作页展示

不干什么：

- 不当事实真源替代 task/run

### 8. `security_gateway_service`

干什么：

- 安全五层
- 审计
- 处罚

不干什么：

- 不负责业务编排

### 9. `external_*_registry_service`

干什么：

- 管外接 Skill / Agent 注册信息
- 心跳、版本、能力声明

不干什么：

- 不持有裁决权
- 不持有任务真源

## 六、当前承接策略

开发包 A-D 已完成，当前按最快最全方式应继续下面顺序：

1. `NEXT_STAGE_3_TODO.md` -> `Package M` 主脑主链收口
2. `NEXT_STAGE_3_TODO.md` -> `Package N` 外接能力控制面前端
3. `NEXT_STAGE_3_TODO.md` -> `Package O` 容灾演练自动化
4. `NEXT_STAGE_3_TODO.md` -> `Package P` 架构守卫与技术债清理

原因：

- 当前最重要的不是再补新能力，而是把主脑唯一正式路径彻底收干净
- `message_ingestion_service.py`、`workflow_execution_service.py` 和 `task_view` 仍有收口空间
- 完成这一步后，主脑代码层才算真正稳定

## 七、下一轮验收命令

每完成一包后，至少做以下验收：

- [x] `pytest`
- [x] `npm run build`
- [x] `python3 backend/scripts/check_architecture_boundaries.py --root backend`
- [x] 主脑边界检查：确认没有把裁决、审计、处罚真源外置

## 八、下一步直接开工建议

下一步优先开发：

- [ ] `Package M`：继续迁空 `message_ingestion_service.py`
- [ ] `Package M`：继续迁空 `master_bot_service.py`
- [ ] `Package M`：统一 `route_decision / execution_plan / task_view` 产出路径
- [ ] `Package M`：清理兼容层直接分发或直接执行残留
- [ ] `Package M`：固化唯一执行路径 `brain_core -> execution_gateway -> tentacle_adapters`
