# WorkBot 八爪鱼拆解执行清单（deconstruct）

版本：v1.0  
更新时间：2026-04-11  
目标：落地“一个封闭大脑 Agent + 多个外置触手 + 协议统一（MCP）”

## 1. 目标边界（必须坚持）

- 大脑只保留一个消息处理 Agent（接待 + 项目经理）。
- 大脑只做：接待、澄清、路由、编排、回传、审计，不做重执行。
- 触手全部外置：搜索、PDF、写作、天气、专业查询、后续浏览器自动化。
- 所有执行统一走 Tool Gateway / MCP Runtime，不允许主链直接调用具体工具实现。

## 2. 当前差距摘要（现状）

- 自由工作流中仍有大量内置 Skill handler（搜索/PDF/写作/天气/任务查询）。
- MCP Runtime 当前以 mock 风格 client 为主，真实远程调用能力需要加强。
- 专业工作流仍偏“准入与说明”，真实专业触手执行链未完整闭环。
- 触手配置存在文件/路径耦合，未完全收口为统一运行态真源。
- `pdf-mcp` 与 `search-mcp` 已有独立目录，但主系统注册与部署链路未完全产品化。

## 3. 分阶段任务拆解

## S0 基线冻结与准入规则

- [x] D-S0-01 冻结大脑职责边界文档  
  输出：职责矩阵（大脑/触手/网关/任务中心）  
  验收：评审通过，后续需求不得突破边界。

- [x] D-S0-02 建立“禁止新增内置重 Skill”规则  
  输出：开发规范条目 + CI 校验脚本（关键目录关键词扫描）  
  验收：新增 `*_skill` 重执行 handler 时 CI 失败。

- [x] D-S0-03 建立迁移台账  
  输出：能力清单（保留/桥接中/已外置/延后）  
  验收：工具库可见同一状态字段并与台账一致。

## S1 大脑封闭（单入口 Agent）

- [x] D-S1-01 固化唯一消息入口 Agent（接待+项目经理）  
  输出：统一入口流程图 + 代码路径说明  
  验收：所有入站消息先进入同一入口决策链。

- [x] D-S1-02 统一 `route_decision` 结构  
  输出：标准字段集合  
  必含：`workflow_mode`、`required_capabilities`、`requires_permission`、`execution_scope`、`approval_required`、`execution_plan`  
  验收：任务、运行详情、审计日志都可读到同结构。

- [x] D-S1-03 清理主链直接执行残留  
  输出：代码清理提交  
  验收：`master_bot_service`/`workflow_execution_service` 不含具体工具执行逻辑。

## S2 自由工作流触手外置

- [x] D-S2-01 外置 `web_search_skill`  
  输出：`search-mcp` 生产化接线（注册、调用、回滚）  
  验收：默认走 MCP，可一键回滚内置。

- [x] D-S2-02 外置 `pdf_read_skill` + `pdf_summary_skill` + `pdf_to_docx`  
  输出：`pdf-mcp` 生产化接线（双跑、灰度、切流、回滚）  
  验收：工具库可见健康、延迟、调用统计；异常可降级。

- [x] D-S2-03 外置 `speech_writer_skill` 与 `general_writer_skill`  
  输出：`writer-mcp`（或合并至现有文本触手）  
  验收：写作类请求默认不在主进程执行。

- [x] D-S2-04 外置 `weather_skill`  
  输出：`weather-mcp`（含超时与缓存策略）  
  验收：天气查询链路完全通过 MCP。

- [x] D-S2-05 评估 `task_status_skill`/`task_list_skill` 去向  
  输出：保留或外置决策记录  
  验收：若保留，明确为“大脑只读轻能力”；若外置，给出迁移计划。

## S3 MCP Runtime 真实化与治理

- [x] D-S3-01 实现真实 MCP 客户端  
  输出：HTTP/SSE/stdio 执行器（非 mock）  
  验收：调用链路出现真实远程请求与错误码。

- [x] D-S3-02 完善治理能力  
  输出：超时、重试、熔断、降级、健康检查机制  
  验收：触手宕机时主链不断，用户收到可读降级结果。

- [x] D-S3-03 统一双跑/灰度/切流/回滚策略  
  输出：通用流量策略模块  
  验收：任意触手都可复用同一迁移控制能力。

- [x] D-S3-04 工具库观测增强  
  输出：每触手的健康/调用量/成功率/平均延迟面板  
  验收：页面可直接判断是否可切流。

## S4 专业触手闭环（只读优先）

- [x] D-S4-01 落地首个专业只读触手 `order-query-mcp`  
  输出：独立服务 + MCP 注册 + 查询 Schema  
  验收：专业查询请求真实走外部触手并返回结构化结果。

- [x] D-S4-02 落地第二个专业触手 `crm-query-mcp`  
  输出：客户信息只读查询触手  
  验收：客户实体识别后可命中 CRM 触手。

- [x] D-S4-03 权限与身份受控传递  
  输出：短时效令牌 + scope 限制 + 审计链  
  验收：大脑不持有长期业务凭证；日志无敏感凭证。

- [x] D-S4-04 审批节点接线  
  输出：`requires_approval` 节点与消息确认链路  
  验收：高风险请求必须人工确认后继续。

## S5 配置真源与部署收口

- [x] D-S5-01 统一运行态真源为数据库 registry  
  输出：source/tool registry 读写规范  
  验收：不再依赖硬编码外部路径作为主真源。

- [x] D-S5-02 补齐触手部署编排  
  输出：`docker-compose`/部署清单纳入 `pdf-mcp`、`search-mcp`、后续触手  
  验收：一套命令可启动完整“脑+触手”联调环境。

- [x] D-S5-03 统一配置导入机制  
  输出：文件模板仅作导入，运行态只读 registry  
  验收：无“yaml+代码+数据库”长期并存。

## S6 清理与最终验收

- [x] D-S6-01 删除已完成外置的内置 Skill 实现  
  输出：代码清理提交  
  验收：目标 Skill 不再存在主系统 handler。

- [x] D-S6-02 全链路回归测试  
  输出：测试集（自由流/专业流/回滚/降级/审批）  
  验收：关键测试全通过并可重复运行。

- [x] D-S6-03 发布验收报告  
  输出：阶段完成说明 + 风险清单 + 回滚手册  
  验收：可按文档执行演练并成功回滚。

## 4. 推荐执行顺序（8个迭代）

1. Sprint-1：S0 + S1  
2. Sprint-2：S2（搜索、PDF）  
3. Sprint-3：S2（写作、天气） + S3 基础  
4. Sprint-4：S3 完整治理  
5. Sprint-5：S4（order-query）  
6. Sprint-6：S4（crm-query + 审批）  
7. Sprint-7：S5（配置与部署收口）  
8. Sprint-8：S6（删除内置 + 最终验收）

## 5. 每项任务统一验收模板

- 输入：请求样例、权限上下文、所需能力标签  
- 执行：路由决策、触手调用、失败处理、回传  
- 观测：trace、审计、健康、调用统计  
- 回滚：触发条件、开关路径、恢复时长  
- 结果：通过/失败、问题单、修复结论

## 6. 渐进式重构（最快最全执行版）

目标：不推翻现有系统，在最短路径内完成“新分层 + 外置触手 + 主链收口”。

### 6.0 当前大脑内保留能力清单（最终状态）

说明：

- 当前主仓已完成“重执行能力出脑”，不再保留任何 transitional builtin fallback。
- 生产目标是 `external_only`，大脑中只允许存在轻量只读能力。

只读保留（可长期存在，但必须保持轻量只读）：

- `task_status_skill`
  用途：读取当前任务状态与进度视图。
  原因：属于大脑查询视图，不是外部触手重执行。

- `task_list_skill`
  用途：列出最近任务。
  原因：属于大脑查询视图，不是外部触手重执行。

已纯外接（主仓中已删除 builtin fallback，仅允许 external runtime 执行）：

- `weather_skill`
  目标归宿：`weather-mcp`

- `web_search_skill`
  目标归宿：`search-mcp`

- `pdf_read_skill`
  目标归宿：`pdf-mcp`

- `pdf_summary_skill`
  目标归宿：`pdf-mcp`

- `speech_writer_skill`
  目标归宿：`writer-mcp`

- `general_writer_skill`
  目标归宿：`writer-mcp`

当前治理规则（已落地）：

- 新增 builtin `*_skill` 不允许直接进入主仓，架构检查会失败。
- `local-agents` 与 `local-mcp-services` 只作为 `legacy/manual fallback` 展示与应急兜底。
- 自由工作流默认不会把 legacy fallback source 当作 runtime 主路径，除非显式切到 `local_only`。
- 当系统处于 `external_only` 时，重执行能力必须走 external runtime，缺少 external runtime 会直接报 `external_runtime_required`。
- 当前主仓只保留 `task_status_skill` 与 `task_list_skill` 两个只读保留项。

### 6.1 新代码层（先建骨架，再迁移）

目录建议（目标形态）：

```text
backend/app/
  brain_core/
    reception/
    routing/
    orchestration/
    task_view/
  execution_gateway/
    contracts.py
    runtime_router.py
    policy.py
  tentacle_adapters/
    search_adapter.py
    pdf_adapter.py
    writer_adapter.py
    weather_adapter.py
    order_adapter.py
    crm_adapter.py
  infrastructure/
    persistence/
    messaging/
    http_clients/
    config/
```

层职责与禁止项（必须执行）：

- `brain_core`  
  负责：接待、澄清、路由、工作流编排、任务状态推进、结果聚合与回传。  
  禁止：直接发 HTTP、直接连数据库、直接调用触手具体实现、直接写技能 handler。

- `execution_gateway`  
  负责：统一执行入口、协议适配选择、流量策略（双跑/灰度/切流/回滚）、超时重试熔断。  
  禁止：做业务决策、做会话接待、写具体领域规则。

- `tentacle_adapters`  
  负责：每个触手的请求/响应 schema 映射、错误语义归一、trace补全。  
  禁止：做路由决策、存储长期状态、持有业务长期凭证。

- `infrastructure`  
  负责：DB/Redis/NATS/HTTP Client/配置加载/密钥获取等外部依赖。  
  禁止：写业务规则、写工作流编排逻辑。

现有代码迁移映射（先迁移，不改行为）：

- `master_bot_service.py` -> `brain_core/routing/*`
- `message_ingestion_service.py`（接待段）-> `brain_core/reception/*`
- `workflow_execution_service.py`（编排段）-> `brain_core/orchestration/*`
- `agent_execution_service.py`（执行分发段）-> `execution_gateway/runtime_router.py`
- `mcp_runtime_service.py` -> `execution_gateway/*` + `infrastructure/http_clients/*`
- `free_workflow_service.py` 内具体技能实现 -> `tentacle_adapters/*` 或外置MCP服务
- `task_service.py`（查询视图段）-> `brain_core/task_view/*`
- `persistence_service.py` / NATS / Redis 相关 -> `infrastructure/*`

调用方向（强约束）：

1. `brain_core -> execution_gateway`
2. `execution_gateway -> tentacle_adapters`
3. `tentacle_adapters -> infrastructure`
4. `brain_core` 可读 `infrastructure` 的仓储接口，但不能越过 `execution_gateway` 触发执行

验收：主链调用路径必须是 `brain_core -> execution_gateway -> tentacle_adapters`，并通过架构边界检查。

### 6.1.1 每层“干什么/不干什么”快速对照

- `brain_core` 干什么：  
  接待消息、生成 `route_decision`、创建任务、推进状态、组织用户回复。

- `brain_core` 不干什么：  
  不解析 PDF、不发搜索请求、不拼触手 URL、不写 SQL 细节。

- `execution_gateway` 干什么：  
  统一 `invoke()`、选主路径/影子路径、记录调用统计、执行降级回滚。

- `execution_gateway` 不干什么：  
  不决定“要不要查订单”，只执行“已决定要查订单”。

- `tentacle_adapters` 干什么：  
  将统一 payload 转成触手协议，收敛错误为统一错误码。

- `tentacle_adapters` 不干什么：  
  不维护会话，不做产品层话术，不做权限策略判定。

- `infrastructure` 干什么：  
  提供连接能力与存取能力，保证可靠性与可观测性。

- `infrastructure` 不干什么：  
  不承担业务流程分支判断。

### 6.2 最快路径（4周压缩计划）

1. Week-1：建层与“零行为变更迁移”  
   动作：创建新目录与接口；把现有逻辑按原样搬迁，不改功能。  
   输出：模块映射表（旧文件 -> 新层文件）。  
   验收：全量回归通过，线上行为无变化。

2. Week-2：自由工作流重执行能力外置  
   动作：搜索/PDF/写作/天气改走 `execution_gateway`，启用双跑与灰度。  
   输出：触手接入清单、切流开关、回滚开关。  
   验收：默认路径可切到 MCP，失败可秒级回滚。

3. Week-3：专业触手闭环  
   动作：上线 `order-query-mcp`、`crm-query-mcp`（只读）；打通鉴权与审计。  
   输出：专业流程准入与执行链路文档。  
   验收：专业请求可真实外部执行，凭证不落地大脑。

4. Week-4：删除遗留与治理加固  
   动作：删除内置重 Skill handler；启用 CI 架构守卫规则。  
   输出：删除清单、架构 lint 规则、最终验收报告。  
   验收：大脑层不再 import 具体工具实现；所有执行统一出口。

### 6.3 并行推进方式（最快）

- 轨道A（架构轨）：新层目录、接口契约、依赖倒置、CI 守卫。
- 轨道B（能力轨）：按触手逐个迁移（search/pdf/writer/weather -> order/crm）。
- 轨道C（保障轨）：测试、监控、灰度、回滚脚本。

并行规则：A 先给接口与约束，B 按接口迁移，C 每日回归；任何触手切流必须先有回滚脚本。

### 6.4 强制门禁（不满足不得合并）

- 禁止在主系统新增内置重执行 Skill。
- 禁止从 `brain_core` 直接调用 `tentacle` 实现细节。
- 禁止没有双跑/灰度/回滚的触手直接全量切流。
- 禁止专业写操作在审批节点上线前进入生产链路。

### 6.5 里程碑完成定义（Done）

- M1：新代码层落地且主链稳定。  
- M2：自由工作流重执行能力全部外置。  
- M3：只读专业触手闭环（订单+CRM）上线。  
- M4：内置重 Skill 清零，统一协议执行达成。  

## 7. Agent工单分发版（可直接执行）

## 7.1 角色分工

- Agent-A（架构轨）：代码分层、接口契约、依赖边界、CI门禁。
- Agent-B（能力轨）：触手外置（search/pdf/writer/weather/order/crm）与主链接线。
- Agent-C（保障轨）：测试、灰度、回滚、监控、发布验收。
- Commander（你）：合并审查、冲突协调、最终验收。

## 7.2 工单状态模板

- `TODO` 工单ID｜负责人｜预计工时｜依赖
- [~] `DOING` 工单ID｜负责人｜开始时间
- [x] `DONE` 工单ID｜负责人｜完成时间｜验收结果

## 7.3 Wave-1（Week-1：新层骨架 + 零行为迁移）

- [x] W1-A1｜Agent-A｜6h｜无  
  任务：建立新分层目录与基础模块。  
  路径：`backend/app/brain_core/`、`backend/app/execution_gateway/`、`backend/app/tentacle_adapters/`、`backend/app/infrastructure/`。  
  验收：项目可启动，旧功能行为不变。

- [x] W1-A2｜Agent-A｜6h｜W1-A1  
  任务：抽出执行协议接口（统一调用出口）。  
  路径：`backend/app/execution_gateway/contracts.py`、`backend/app/execution_gateway/service.py`。  
  验收：主链存在唯一执行入口接口。

- [x] W1-A3｜Agent-A｜4h｜W1-A2  
  任务：抽出路由决策DTO并统一字段。  
  路径：`backend/app/schemas/messages.py`、`backend/app/services/master_bot_service.py`。  
  验收：`route_decision` 字段统一且可序列化。

- [x] W1-C1｜Agent-C｜4h｜W1-A1  
  任务：新增架构边界检查脚本。  
  路径：`backend/scripts/check_architecture_boundaries.py`、`.github/workflows/*`（如有）。  
  验收：检测到 `brain_core` 直连触手实现时CI失败。

- [x] W1-C2｜Agent-C｜4h｜W1-A3  
  任务：补齐Week-1回归测试。  
  路径：`backend/tests/test_messages.py`、`backend/tests/test_agent_execution_service.py`。  
  命令：`cd backend && ../.venv/bin/pytest -q tests/test_messages.py tests/test_agent_execution_service.py`。  
  验收：测试通过，行为不回退。

## 7.4 Wave-2（Week-2：Search/PDF外置）

- [x] W2-B1｜Agent-B｜6h｜W1-A2  
  任务：Search链路强制走 execution_gateway + MCP。  
  路径：`backend/app/services/free_workflow_service.py`、`backend/app/execution_gateway/*`。  
  验收：`web_search_skill` 默认 MCP，可回滚。

- [x] W2-B2｜Agent-B｜8h｜W1-A2  
  任务：PDF链路强制走 execution_gateway + MCP。  
  路径：`backend/app/services/free_workflow_service.py`、`pdf-mcp/**`。  
  验收：`pdf_read/pdf_summary/pdf_to_docx` 可双跑、灰度、切流、回滚。

- [x] W2-B3｜Agent-B｜4h｜W2-B1,W2-B2  
  任务：注册与流量策略收口。  
  路径：`backend/app/services/tool_source_service.py`、`backend/app/services/tool_catalog_service.py`。  
  验收：工具库显示迁移阶段、流量策略、回滚配置。

- [x] W2-C1｜Agent-C｜4h｜W2-B1,W2-B2  
  任务：补齐外置链路回归测试。  
  路径：`backend/tests/test_free_workflow.py`、`backend/tests/test_mcp_runtime.py`。  
  命令：`cd backend && ../.venv/bin/pytest -q tests/test_free_workflow.py tests/test_mcp_runtime.py tests/test_tool_catalog.py`。  
  验收：双跑/灰度/回滚路径测试通过。

- [x] W2-C2｜Agent-C｜3h｜W2-B2  
  任务：部署编排纳入触手。  
  路径：`docker-compose.yml`、`run-*.sh`。  
  验收：一套命令可拉起 brain + pdf-mcp + search-mcp 联调环境。

## 7.5 Wave-3（Week-3：Writer/Weather + 专业触手首条）

- [x] W3-B1｜Agent-B｜6h｜W1-A2  
  任务：外置 writer（speech/general）触手并接线。  
  路径：`writer-mcp/**`（新建）、`backend/app/services/free_workflow_service.py`。  
  验收：写作请求默认不在主进程执行。

- [x] W3-B2｜Agent-B｜4h｜W1-A2  
  任务：外置 weather 触手并接线。  
  路径：`weather-mcp/**`（新建）、`backend/app/services/free_workflow_service.py`。  
  验收：天气能力默认走 MCP。

- [x] W3-B3｜Agent-B｜8h｜W1-A2  
  任务：落地 `order-query-mcp` 只读触手。  
  路径：`order-query-mcp/**`（新建）、`backend/app/services/professional_workflow_service.py`。  
  验收：专业查询请求可真实返回结构化订单信息。

- [x] W3-C1｜Agent-C｜4h｜W3-B3  
  任务：专业流程端到端回归。  
  路径：`backend/tests/test_professional_workflow.py`、`backend/tests/test_messages.py`。  
  命令：`cd backend && ../.venv/bin/pytest -q tests/test_professional_workflow.py tests/test_messages.py tests/test_tasks.py`。  
  验收：准入、执行、通知、失败归因通过。

## 7.6 Wave-4（Week-4：CRM触手 + 清理内置 + 最终收口）

- [x] W4-B1｜Agent-B｜8h｜W3-B3  
  任务：落地 `crm-query-mcp` 只读触手。  
  路径：`crm-query-mcp/**`（新建）、`backend/app/services/professional_workflow_service.py`。  
  验收：客户实体识别后可命中CRM触手。

- [x] W4-A1｜Agent-A｜6h｜W2-B1,W2-B2,W3-B1,W3-B2  
  任务：删除已外置内置重Skill实现。  
  路径：`backend/app/services/free_workflow_service.py`。  
  验收：主系统不再包含对应 handler 实现。

- [x] W4-A2｜Agent-A｜6h｜W1-A2  
  任务：MCP Runtime从mock升级为真实执行器。  
  路径：`backend/app/services/mcp_runtime_service.py`。  
  验收：调用链路具备真实远程调用、超时、重试、熔断语义。

- [x] W4-C1｜Agent-C｜4h｜W4-A1,W4-A2  
  任务：最终全链路回归。  
  路径：`backend/tests/*.py`（关键集）。  
  命令：`cd backend && ../.venv/bin/pytest -q tests/test_tool_source_service.py tests/test_tool_catalog.py tests/test_mcp_runtime.py tests/test_free_workflow.py tests/test_professional_workflow.py tests/test_messages.py tests/test_workflow_scheduler.py tests/test_workflows.py tests/test_security.py tests/test_tasks.py tests/test_agent_execution_service.py`。  
  验收：关键链路全绿，失败可定位，回滚可执行。

## 7.7 交付清单（每张工单必须提交）

- 变更文件列表（绝对路径）
- 测试命令与结果
- 回滚方式（开关、配置、恢复步骤）
- 风险与后续待办（最多3条）

## 8. 完成报告（2026-04-11）

- 完成状态：`S0-S6` 全部勾选完成，`Wave-1` 到 `Wave-4` 工单全部完成。
- 架构结果：已新增 `brain_core / execution_gateway / tentacle_adapters / infrastructure` 分层骨架与边界检查脚本。
- 触手结果：`writer-mcp`、`weather-mcp`、`order-query-mcp`、`crm-query-mcp` 完成并通过端点测试；`pdf-mcp`、`search-mcp` 已纳入统一治理。
- 运行时结果：`MCP runtime` 完成真实 HTTP 执行、重试与最小熔断；`tool_source/catalog` 增加本仓触手注册、流量策略、回滚与观测字段。
- 部署结果：`docker-compose` 已纳入 `order-query-mcp` 与 `crm-query-mcp`，形成“脑+触手”联调编排。
- 验收结果：后端关键回归通过，触手端点测试通过（见下方命令记录）。

### 8.1 验收命令记录

1. `cd backend && ../.venv/bin/pytest -q tests/test_architecture_boundaries.py tests/test_mcp_runtime.py tests/test_tool_source_service.py tests/test_tool_catalog.py tests/test_tools_catalog.py tests/test_free_workflow.py tests/test_messages.py tests/test_professional_workflow.py tests/test_tasks.py tests/test_agent_execution_service.py`
2. `cd writer-mcp && ../.venv/bin/pytest -q tests/test_endpoints.py`
3. `cd weather-mcp && ../.venv/bin/pytest -q tests/test_endpoints.py`
4. `cd order-query-mcp && ../.venv/bin/pytest -q tests/test_endpoints.py`
5. `cd crm-query-mcp && ../.venv/bin/pytest -q tests/test_endpoints.py`
6. `cd backend && ../.venv/bin/python scripts/check_architecture_boundaries.py`

## 9. 外接部署模式（跨服务器）

目标：将 brain（大脑）与 tentacle/skill（触手能力）拆到不同仓库、不同服务器，统一通过 external registry 接入，最终收敛到 external_only。

### 9.1 基本原则

- 大脑仓库（brain repo）只保留唯一消息入口 Agent（接待 + 项目经理），以及路由、编排、审计、回传能力。
- 触手仓库（tentacle/skill repo）独立发布，承载 MCP 服务、技能型工具、专业查询工具。
- 大脑不再依赖触手源码路径，不再直接 import/执行触手实现。
- 统一通过 external registry（URL + credentials）做发现、鉴权、健康检查、能力注册。

### 9.2 仓库与运行职责分离

- Brain 仓库：
  - 消息入口：唯一接待 Agent（必须保留在 brain）。
  - 工作流决策：`workflow_mode`、`required_capabilities`、`approval_required`。
  - 执行网关：只做协议桥接与流量治理，不承载业务工具实现。
- Tentacle/Skill 仓库：
  - 提供 MCP endpoint 与 skill-like tool endpoint。
  - 对外暴露 registry 元数据（source、tool、permissions、schema、health）。
  - 独立伸缩、独立灰度、独立发布。

### 9.3 external registry 接入规范

- registry 作为唯一外部能力发现入口，至少包含：
  - `registry.url`：可访问地址（HTTPS）。
  - `registry.credentials`：token/basic/mTLS 等认证参数。
  - `sources[]`：`external_repo` 与 `mcp_registry` 等 source 定义。
  - `tools[]`：能力项（writer/weather/order/crm + skill-like tool）及权限、schema、回滚策略。
- 大脑启动与刷新时只读取 registry，不扫描跨仓本地目录。
- 所有外接能力必须可观测：`health_summary`、`recent_call_summary`、`traffic_policy`、`rollback`。

### 9.4 迁移步骤：`hybrid -> external_only`

1. `hybrid`（双源阶段）
   - 保留本地 source（local_mcp/local_agents）+ external source 并行注册。
   - 关键能力先启用 dual-run 与灰度，确保结果一致性与稳定性。
2. `external_preferred`（外接优先）
   - `traffic_policy.mode` 切为 `runtime_primary`，外接为主、本地为回退。
   - 观测通过后逐步将 canary 从 20% 提升到 100%。
3. `external_only`（完全外接）
   - 下线本地触手 source（仅保留 brain 的消息入口 Agent 和编排能力）。
   - 工具真源统一为 external registry，主链只保留 external 调用路径。
   - 回滚仅通过 registry/traffic policy，不允许恢复为“主链内置执行”。

### 9.5 强制验收点

- 唯一消息入口 Agent 仍在 brain（接待 + 项目经理），且所有入站消息先经过该入口。
- 大脑仓库无触手实现依赖（无跨仓路径耦合、无直接工具执行代码）。
- external registry 不可用时可降级但主链不断；可通过统一开关回滚到 external_preferred/hybrid。
- 专业触手（order/crm）继续保持只读优先，写操作必须在审批链路之后开放。
