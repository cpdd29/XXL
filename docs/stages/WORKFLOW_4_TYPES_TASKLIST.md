# 四类工作流开发任务清单（AGENTS 规范版）

更新时间：2026-04-21

## 执行边界

- 仅开发四类工作流分层与治理，不新增无关能力
- 仅走可视化工作流主路径，废弃暗路由
- 遵循“基础优先、先收口再扩展”

## 开发任务状态追踪

- [x] T0 任务清单规范化（按 AGENTS 下发格式重写）
- [ ] T1 基础工作流（重中之重）上线
- [ ] T2 专业工作流（租户不共享、默认空、本地保留）上线
- [ ] T3 自由工作流（租户共享、默认配置）上线
- [x] T4 Agent 专属工作流（必有输入、必有输出）上线
- [x] T5 父子模块化、嵌套触发、可视化链路上线
- [x] T6 暗路由清理与全链路回归通过
- [x] T1.1 基础主链契约收口（request/tenant/security context + workflow-first 路由回归收口）
- [x] T1.2 基础工作流可视化模块主链收口（模块路由、子模块封装、上下文透传与重复标签节点状态修复）
- [x] T5.1 `sub_workflow/trigger_workflow` 节点别名兼容（后端执行 + 路由识别 + 前端编辑器类型）
- [x] T5.2 后端嵌套/触发语义回归测试与任务清单更新
- [x] T5.3 前端父子/触发可视化链路收口

## T1 基础工作流（重中之重）

任务：实现基础主链统一入口与统一状态机  
文件路径：`backend/app/services/message_ingestion_service.py`、`backend/app/services/workflow_execution_service.py`、`backend/app/services/workflow_dispatcher_service.py`、`backend/app/services/channel_outbound_service.py`  
功能描述：固化 `渠道接入 -> 安全网关 -> 对话澄清 -> 主脑裁决 -> 调度执行 -> 完成判定 -> 回传 -> 审计归档` 主链，所有请求都必须落到该链路。  
接口定义：输入 `UnifiedMessage`；输出 `route_decision + execution_plan + run_id + task_id + dispatch_contract`；失败返回统一 `failure_stage/failure_message/retryable`。  
完成标准：任一请求可生成完整运行链路与失败定位信息，且不存在绕行主链的执行路径。

任务：实现基础节点输入输出契约  
文件路径：`backend/app/schemas/messages.py`、`backend/app/schemas/workflows.py`、`backend/app/schemas/tasks.py`、`backend/tests/test_messages.py`  
功能描述：统一请求上下文、租户上下文、安全上下文、执行上下文字段，保障节点间契约一致。  
接口定义：统一字段包含 `tenant_id`、`route_decision`、`execution_plan`、`dispatch_context`、`status_reason`。  
完成标准：基础链路关键节点字段对齐，测试覆盖契约透传与失败场景。

## T2 专业工作流（租户不共享、默认空、本地保留）

任务：实现专业工作流类型与租户隔离  
文件路径：`backend/app/services/workflow_service.py`、`backend/app/services/professional_workflow_service.py`、`backend/app/services/workflow_execution_service.py`、`backend/tests/test_professional_workflow.py`  
功能描述：新增 `workflow_type=professional` 能力，专业工作流默认不预置模板，需租户显式创建。  
接口定义：创建/查询/触发接口必须携带并校验 `tenant_id + workflow_type`。  
完成标准：A 租户不能读取、触发、复用 B 租户专业工作流，跨租户请求被拦截并审计。

任务：实现专业结果防泄露约束  
文件路径：`backend/app/services/security_service.py`、`backend/app/services/channel_outbound_service.py`、`backend/tests/test_security.py`  
功能描述：专业工作流结果进入出站前必须进行租户边界校验与脱敏。  
接口定义：输出包含 `security_verdict`、`tenant_scope_check`、`audit_trace_id`。  
完成标准：专业流运行结果和日志无跨租户泄露。

## T3 自由工作流（租户共享、默认配置）

任务：实现自由工作流类型与默认模板  
文件路径：`backend/app/services/free_workflow_service.py`、`backend/app/services/workflow_service.py`、`backend/app/services/mandatory_workflow_registry_service.py`、`backend/tests/test_free_workflow.py`  
功能描述：新增 `workflow_type=free` 并提供共享默认模板。  
接口定义：默认模板覆盖 6 类能力：理解需求、文字处理、方案建议、信息整理、对话协助、通用答疑。  
完成标准：新租户开箱可用默认自由工作流。

任务：实现自由工作流默认运行配置  
文件路径：`backend/app/services/free_workflow_service.py`、`backend/app/services/settings_service.py`、`backend/tests/test_messages.py`  
功能描述：统一自由流超时、降级、回传结构，命中后直接执行，不回退接待暗路由。  
接口定义：统一输出 `title/summary/content/bullets/references/execution_trace`。  
完成标准：同类请求稳定命中对应自由模板并返回结构化结果。

## T4 Agent 专属工作流（必有输入、必有输出）

任务：实现 Agent 与工作流绑定  
文件路径：`backend/app/services/agent_service.py`、`backend/app/services/workflow_service.py`、`backend/app/schemas/agents.py`、`backend/tests/test_agents_runtime.py`  
功能描述：为每个可运行 Agent 建立 `agent_workflow_id` 绑定关系。  
接口定义：Agent 元数据新增 `agent_workflow_id`、`input_contract`、`output_contract`。  
完成标准：无专属工作流绑定的 Agent 禁止启用执行。

任务：实现输入输出契约校验与运行留痕  
文件路径：`backend/app/services/agent_execution_service.py`、`backend/app/services/workflow_execution_service.py`、`backend/tests/test_workflows.py`  
功能描述：保存和发布时校验契约，运行时写入输入输出快照与版本号。  
接口定义：执行记录新增 `contract_version`、`input_snapshot`、`output_snapshot`。  
完成标准：任一 Agent 执行均有明确输入输出与版本可追溯记录。

## T5 模块化、嵌套触发、可视化

任务：实现父子工作流模型  
文件路径：`backend/app/services/workflow_service.py`、`backend/app/schemas/workflows.py`、`backend/tests/test_workflows.py`  
功能描述：支持父流程挂子流程，形成可复用模块。  
接口定义：节点支持 `node_type=sub_workflow`、字段 `sub_workflow_id`。  
完成标准：父流程可复用安全 Agent 子流程并可独立调试。

任务：实现流程内触发其他流程  
文件路径：`backend/app/services/workflow_dispatcher_service.py`、`backend/app/services/workflow_execution_service.py`、`backend/tests/test_workflow_dispatcher.py`  
功能描述：支持 `trigger_workflow` 节点在运行中触发目标流程。  
接口定义：节点支持 `node_type=trigger_workflow`、字段 `target_workflow_id + trigger_payload`。  
完成标准：嵌套与触发流程具备可追踪 run 链路。

任务：实现全可视化链路  
文件路径：`reception/components/workflow/workflow-editor.tsx`、`reception/components/workflow/nodes.tsx`、`reception/components/workflow/workflow-inspector.tsx`、`reception/hooks/use-workflow-realtime.ts`  
功能描述：可视化展示父子关系、触发关系、运行状态与故障节点。  
接口定义：前端节点需支持 `sub_workflow`、`trigger_workflow` 类型渲染与状态展示。  
完成标准：任一执行路径都能在流程图中定位。

当前状态：

- 已补齐 `backend/tests/test_workflows.py` 中 `sub_workflow/workflow` 与 `trigger_workflow` 的后端回归覆盖
- `sub_workflow` 已验证父流程等待子流程完成并回收结果，同时 child run 暴露 `parentWorkflowId/parentRunId/parentNodeId/workflowRelationType`
- `trigger_workflow` 已验证父流程触发后继续推进，同时 parent run `dispatchContext.workflowRelations` 记录 `target workflow/run/task/status`
- 前端 `workflow-editor/nodes/workflow-inspector` 已可区分 `sub_workflow/trigger_workflow`，展示父流程、子流程/触发流程关系、相关 run 状态与 Collaboration 跳转入口
- T5 后端链路语义、父子/触发元数据与前端可视化消费已全部收口

## T6 暗路由清理与回归

任务：清理暗路由与非工作流执行入口  
文件路径：`backend/app/brain_core/routing/service.py`、`backend/app/brain_core/routing/rules.py`、`backend/tests/test_brain_core.py`、`backend/tests/test_messages.py`  
功能描述：渠道接入只允许命中对应工作流定义路径。  
接口定义：`route_decision` 必须包含命中的工作流信息与策略来源。  
完成标准：不存在绕过工作流定义的执行路径。

任务：执行守卫与回归  
文件路径：`backend/scripts/check_architecture_boundaries.py`、`backend/scripts/check_todo_sync.py`、`backend/tests/test_architecture_boundaries.py`、`backend/tests/test_todo_sync.py`、`backend/tests/test_package_p_smoke.py`  
功能描述：执行架构边界、TODO 同步、关键 smoke 回归。  
接口定义：命令固定为：

- `python3 backend/scripts/check_architecture_boundaries.py`
- `python3 backend/scripts/check_todo_sync.py --strict`
- `python3 -m pytest -q backend/tests/test_architecture_boundaries.py backend/tests/test_todo_sync.py backend/tests/test_package_p_smoke.py`

完成标准：全部命令通过。

## 执行顺序

1. T1 基础工作流
2. T5 父子模块化与嵌套触发
3. T4 Agent 专属输入输出契约
4. T2 专业工作流隔离与防泄露
5. T3 自由工作流默认模板与共享
6. T6 暗路由清理与全链路回归

## 开发日志

- [完成] 四类工作流任务清单制定 — 完成四类工作流拆解并固化硬约束。
- [完成] 四类工作流任务清单 AGENTS 规范化 — 按“任务/文件路径/功能描述/接口定义/完成标准”重构为可直接下发执行的任务单。
- [完成] T1.1 基础主链契约收口与回归修复 — 收口 `dispatchContext.request_context/tenant_context/security_context` 透传；修复 workflow-first 场景下 chat 直达误命中、专业流误判、executionPlan 丢失、执行代理契约不一致与送货单专业子流冗余工具调用问题，相关回归全部通过。
- [完成] T1.2 基础工作流可视化模块主链收口 — 基础工作流已重构为“渠道输入 -> 安全agent -> 对话agent -> 万事通/需求分发 -> 专业/自由工作流 -> 对话agent -> 安全agent -> 渠道输出”的可视化模块主链；执行器新增按可见节点 `routeWorkflowModes/routeDefault` 选边、模块子流程上下文透传与专业选择回灌，修复重复标签节点状态串台与出站复核覆盖结果问题，相关基础路由与架构守卫回归通过。
- [完成] T1 基础消息链路本地回退调度收口 — 恢复消息型工作流的异步推进与 context patch 语义；在 `persistence=false` 的本地单进程回退模式下跳过 NATS 发布超时，直接走进程内调度，修复任务重复创建、上下文补丁失效、`fallbackHistory` 缺失与搜索自动完成超时回归。
- [完成] T4 Agent 专属工作流绑定与契约收口 — Agent API 已支持 `agent_workflow_id/input_contract/output_contract/contract_version` 的显式解绑与重绑；补齐 create/list/status 序列化覆盖；执行结果保留 agent-specific `contract_version/input_snapshot/output_snapshot`，不再被主脑兜底快照覆盖。
- [完成] T5.1 节点别名兼容开发 — 新增 `sub_workflow/trigger_workflow` 到工作流节点类型，后端统一执行为 workflow 分支并补齐绑定字段解析，前端编辑器和配置面板已支持新节点类型。
- [完成] T5.2 后端嵌套/触发语义回归测试与任务清单更新 — 补齐 `sub_workflow` 等待回收与 `trigger_workflow` 非阻塞触发的 API 回归，验证 child run 父链元数据与 parent `dispatchContext.workflowRelations` 记录目标 workflow/run/task/status，并同步更新 T5 当前状态。
- [完成] T5.3 前端父子/触发可视化链路收口 — `workflow-inspector` 已展示父流程、子流程/触发流程关系、相关 run 状态、故障定位与 Collaboration 跳转；`workflow-editor/nodes` 已恢复 `sub_workflow/trigger_workflow` 节点类型、链路标记与 run 定位入口。
- [完成] T6 暗路由清理与全链路回归 — 渠道消息入口已移除 chat/direct agent 暗路由，`route_decision/brain_dispatch_summary/launch_plan` 统一收口为 workflow-only；补齐主链 fallback 到真实 workflow 的回归断言，并通过主脑消息链路与架构守卫检查。
- [完成] 工作流子工作流下拉空状态收口 — 配置弹窗“子工作流配置”中的“绑定子工作流”在无可绑定工作流时改为展示空状态，不再显示误导性的默认可选项。
- [完成] 需求分发流agent工作流注册与绑定 — 新增 `需求分发流agent工作流`，将 `requirement_dispatcher` 绑定到专属 agent workflow，并补齐顺序执行白名单与注册断言。
- [完成] 万事通agent工作流注册与绑定 — 新增 `general_assistant` mandatory agent、本体配置目录与 `万事通agent工作流`，并将基础工作流中的万事通模块真实绑定到该 agent。
- [完成] 万事通agent工作流执行回归 — 补齐专业查询 / 联网查询两条内部触发回归，验证工作流按可视化节点分支执行并产出对应结果。
- [完成] 专业agent工作流最小回归补齐 — 复核 `专业agent工作流` 已作为 mandatory workflow 注册；最小回归覆盖手动运行默认通过占位链路，验证可视化节点全量完成并返回“暂时默认通过”的占位结果。
- [完成] 专业agent工作流占位接口注册 — 新增 `专业agent工作流` 专业类型数据，按“专业工作流 -> 专业工作流下发任务 -> 找寻专业工作流 -> 执行专业工作流 -> 返回进程”落地最小骨架，当前默认通过并保留后续挂接接口。
- [完成] 自由agent工作流最小回归补齐 — 复核 `自由agent工作流` 已作为 mandatory workflow 注册；最小回归覆盖手动运行默认通过占位链路，验证可视化节点全量完成并返回“暂时默认通过”的占位结果。
- [完成] 自由agent工作流占位接口注册 — 新增 `自由agent工作流` 自由类型数据，按“自由工作流 -> 自由工作流下发任务 -> 在外接触手库中找寻对应的角色来 -> 执行自由工作流 -> 返回进程”落地最小骨架，当前默认通过并保留后续挂接接口。
