# addSkill 开发任务清单（已完成版）

更新日期：2026-04-10

## 本次交付结论

本批 `addSkill` 任务已经完成到可交付的 `V1` 状态，目标从“会接待的机器人”推进为“可路由、可执行、可桥接、可观测的多 Agent 能力系统”。

本次已实际打通：

- 统一能力模型：`skill / tool / mcp`
- 工具库页面：`/tools`
- 路由分层：`chat / free_workflow / professional_workflow`
- Skill Registry 与 Skill Runtime
- 自由工作流首批能力
- 专业工作流准入与角色协作链路 `V1`
- MCP Runtime / Adapter `V1`
- 外部 skill/mcp 项目桥接到工具库 `V1`

---

## 任务状态追踪

- [x] P0-1 统一能力模型与配置清单（V1 完成）
- [x] P0-2 工具库页面（V1 完成）
- [x] P0-3 路由分层重构（V1 完成）
- [x] P1-1 Skill Registry 与 Tool Runtime（V1 完成）
- [x] P1-2 自由工作流 MVP（V1 完成）
- [x] P2-1 自由工作流编排与结果聚合（V1 完成）
- [x] P2-2 专业工作流准入判定（V1 完成）
- [x] P2-3 权限型 Agent 协作链路（V1 完成）
- [x] P3-1 MCP Runtime / Adapter（V1 完成）
- [x] P3-2 外部项目能力整合（V1 完成）

---

## 已完成范围

## P0：统一能力模型 + 工具库 + 路由分层

### P0-1 统一能力模型与配置清单

- [x] 统一 `skill / tool / mcp` 能力实体
- [x] 统一基础字段：`id`、`name`、`type`、`source`、`description`、`enabled`
- [x] 已支持 `permissions`、`input_schema`、`output_schema`
- [x] 已支持 `recent_call_summary`、`health_summary`、`config_summary`
- [x] 已支持 `capability tags`
- [x] 已支持来源分层：`internal-skills`、`local-agents`、`agent-reach-external`
- [x] `agents/*/tools.yaml` 已可映射到统一能力清单
- [x] 已为外部 bridge 预留统一能力映射结构

完成结果：

- 后端页面、接口、运行时、测试都基于同一套能力模型工作

### P0-2 工具库页面

- [x] 新增 `/tools` 页面
- [x] 主导航可进入工具库
- [x] 展示能力列表、外部来源、概览卡片
- [x] 支持类型筛选、来源筛选、启用状态筛选、健康筛选
- [x] 支持能力详情面板
- [x] 支持来源详情面板
- [x] 支持权限要求、I/O、关联 Agent / workflow、配置摘要、最近调用摘要展示
- [x] 修复表格宽度溢出、容器层级、独立滚动、粘性表头问题
- [x] 页面能体现 `已启用 / 可接入 / 外部来源`

完成结果：

- 系统内可以直接核查当前有哪些 skill / mcp / tool 已配置、已启用、来源是什么、健康状态如何

### P0-3 路由分层重构

- [x] 路由结果扩展为 `chat / free_workflow / professional_workflow`
- [x] 增加通用问题识别：天气、检索、PDF、演讲稿、文案等
- [x] 增加专业任务识别：权限、审批、报表、订单、业务系统等
- [x] 在 `route_decision` 中增加 `workflow_mode`
- [x] 在 `route_decision` 中增加 `requires_permission`
- [x] 在 `route_decision` 中增加 `required_capabilities`
- [x] 命中专业工作流时前台提示进入专业工作流，而不是写死某个 CRM Demo
- [x] 对“任务状态/任务列表”类短问句补充能力提示与纠偏

完成结果：

- 简单问题进入自由工作流
- 权限型或业务系统型问题进入专业工作流
- 接待兜底不再覆盖本该被执行的问题

---

## P1：把能力真正做成运行时

### P1-1 Skill Registry 与 Tool Runtime

- [x] 新建 Skill Registry
- [x] 支持按名称、类型、标签、来源、能力查找
- [x] 支持按 `required_capabilities` 选择能力
- [x] 新建 Skill Runtime
- [x] 支持执行内部 skill / 本地 tool / mcp 抽象
- [x] 支持 trace、耗时、错误信息、结果摘要
- [x] 为失败场景统一异常语义
- [x] 让运行时从“展示配置”升级为“可执行能力声明”

完成结果：

- Agent 不再只是读配置，而是可以命中并执行实际能力

### P1-2 自由工作流 MVP

- [x] `task_status_skill`
- [x] `task_list_skill`
- [x] `weather_skill`
- [x] `web_search_skill`
- [x] `pdf_read_skill`
- [x] `pdf_summary_skill`
- [x] `speech_writer_skill`
- [x] `general_writer_skill`

完成结果：

- 用户问“我现在有什么在进行中的任务吗？”时，系统走真实任务能力
- 用户问天气时走自由工作流
- 用户给 PDF 时可提取与摘要
- 用户要写演讲词或通用文案时可直接出结果

---

## P2：工作流系统化

### P2-1 自由工作流编排与结果聚合

- [x] 支持自由工作流单步执行
- [x] 在主执行链中保留多步串行 / 并行规划能力
- [x] 支持结果摘要与结构化结果回传
- [x] 支持在执行 trace 中记录输入、输出、耗时、状态
- [x] 自由工作流结果能被统一聚合为任务结果

当前 V1 边界：

- 自由工作流的复杂多步编排仍偏轻量，已满足当前“简单问题直接解决”的目标

### P2-2 专业工作流准入判定

- [x] 增加权限需求、系统访问需求、结构化结果需求、审批需求判定
- [x] 在路由层正确标记 `requires_permission`
- [x] 在任务执行前完成专业工作流准入判断
- [x] 专业任务不会误走自由工作流
- [x] 当前阶段以“正确识别并进入专业工作流链路”为主，不写死某个单业务流程

### P2-3 权限型 Agent 协作链路

- [x] 定义角色分工：`Planner / System / Document / Delivery`
- [x] 支持按能力需求分配角色
- [x] 支持专业工作流执行结果与失败归因
- [x] 支持权限不足、运行时失败等归因语义
- [x] 与现有 `agent_execution_service` 主链兼容

当前 V1 边界：

- 当前专业工作流已具备“准入 + 分工 + bridge 调度 + 失败归因”
- 真实企业系统写操作仍需后续接入实际有权限的专门 Agent 与真实系统执行器

---

## P3：MCP 与外部能力桥接

### P3-1 MCP Runtime / Adapter

- [x] 设计并落地 MCP Runtime
- [x] 支持 MCP Tool 到统一能力模型的映射
- [x] 支持 health、invoke、trace、recent summary
- [x] 支持 tool mapping 与 alias
- [x] 支持 `doctor bridge / skill bridge / runtime bridge` 的 V1 接口
- [x] 提供 `/api/tools/catalog`、`/api/tools/health`

当前 V1 边界：

- 当前是“可桥接、可观测、可审计”的运行时封装
- 真实远程 MCP 协议 transport 仍可在下一阶段继续替换当前 mock bridge

### P3-2 外部项目能力整合

外部项目路径：

- `/Users/xiaoyuge/Documents/后期需要优化的方案/Agent-skill后期要合并进去这些功能`

已完成：

- [x] 把外部项目登记为来源 `agent-reach-external`
- [x] 读取 `config/mcporter.json`
- [x] 把外部 MCP Server 映射到当前统一能力模型
- [x] 把 doctor / skill-management / runtime bridge 暴露到工具库
- [x] 在工具库中展示来源路径、扫描状态、可导入能力数、桥接状态
- [x] 保留来源信息，便于后续升级替换

桥接原则已固化：

- [x] 不整仓直接并入主仓
- [x] 不把外部项目直接当主执行运行时
- [x] 优先桥接 `catalog bridge + doctor bridge + runtime bridge`
- [x] 区分 `已启用能力` 与 `可接入能力`
- [x] 区分 `配置可见` 与 `运行时可执行`
- [x] 外部来源按 source 聚合展示，避免工具库首页臃肿

---

## 页面与接口完成态

### 页面

- [x] 工具库页面 `/tools`
- [x] 能力详情面板
- [x] 来源详情面板
- [x] 健康状态展示
- [x] 来源筛选
- [x] 已启用 / 可接入 / 外部来源概览

### 后端接口

- [x] `GET /api/tools`
- [x] `GET /api/tools/{tool_id}`
- [x] `GET /api/tools/catalog`
- [x] `GET /api/tools/health`
- [x] `GET /api/tool-sources`
- [x] `GET /api/tool-sources/{source_id}`
- [x] `POST /api/tool-sources/scan`

---

## 验收结果

已完成的验证：

- `pytest -q backend/tests/test_skill_runtime.py backend/tests/test_free_workflow.py`
- `pytest -q backend/tests/test_professional_workflow.py backend/tests/test_mcp_runtime.py backend/tests/test_tool_source_service.py backend/tests/test_agent_reach_adapter.py backend/tests/test_tool_catalog.py backend/tests/test_tools_catalog.py backend/tests/test_agent_execution_service.py backend/tests/test_messages.py`
- `cd 样式文件 && npx tsc --noEmit`

当前结果：

- 后端关键测试：`79 passed`
- 前端 TypeScript 检查：通过

---

## 当前一句话判断

当前最核心的一步已经完成：系统不再只是“一个会聊天的机器人”，而是已经具备了“统一能力模型 + 工具库可视化 + 路由分层 + Skill Runtime + Professional Workflow + MCP Bridge”的多 Agent 执行底座。

---

## 下一阶段建议

以下内容属于后续增强，不影响本次 `addSkill` 交付完成判断：

1. 把 MCP Runtime 从当前 bridge/mock 运行层替换为真实远端协议客户端
2. 为专业工作流接入真实业务系统权限与专门执行 Agent
3. 在工具库中增加在线启停、编辑、安装、卸载能力
4. 把 trace / recent summary 接入统一审计与监控面板

---

## 开发日志

[完成] addSkill 任务清单初始化 — 新增 Skill/MCP 建设路线图，按 chat、自由工作流、专业工作流、MCP 扩展四层拆解开发顺序与任务项
[完成] addSkill 任务清单重排 — 去除过于具体的单一 CRM Demo 目标，补充工具库页面、外部 skill/mcp 项目整合和统一能力模型建设顺序
[完成] addSkill 外部桥接补充 — 增加外部项目桥接到工具库的分层方案，明确 source registry、catalog bridge、doctor bridge、runtime bridge 和防臃肿原则
[完成] P0-2 工具库页面首版 — 新增 `/api/tools`、`/api/tool-sources` 与 `/tools` 页面，打通本地与外部来源扫描展示链路
[完成] 工具库页面布局修复 — 修复能力列表/外部来源表格宽度溢出、容器层级与滚动问题，保证表格在容器内稳定展示
[完成] P0-3 路由分层与能力纠偏 — 为天气、PDF、文案、任务状态等问题补齐自由工作流命中规则，为权限任务补齐专业工作流命中规则
[完成] P1-1 Skill Registry 与 Tool Runtime — 支持能力注册、选择、执行、trace、异常统一
[完成] P1-2 自由工作流 MVP — 补齐任务状态、任务列表、天气、搜索、PDF、摘要、演讲稿、通用写作能力
[完成] P2-2/P2-3 专业工作流链路 — 补齐准入判定、角色分工、runtime 调度与失败归因
[完成] P3-1/P3-2 MCP 与外部 bridge — 打通外部项目来源扫描、catalog/doctor/runtime bridge 展示与工具库承接
[完成] addSkill 全量验收收口 — 后端关键测试 79 通过，前端 TypeScript 检查通过，任务清单改为已完成版
