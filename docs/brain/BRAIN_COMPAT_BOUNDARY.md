# Brain Compat Boundary

更新时间：2026-04-16

## 1. 文档目的

本文件定义主脑兼容层边界，避免历史命名和旧入口反向成为新主链。

适用范围：

- `backend/app/brain_core/`
- `backend/app/services/master_bot_service.py`
- `backend/app/services/message_ingestion_service.py`
- `backend/app/services/workflow_execution_service.py`

---

## 2. 兼容壳清单（仅保留薄壳）

以下对象属于兼容壳，不是主链裁决层：

- `backend/app/services/master_bot_service.py`：历史服务入口壳，保持最小转发，不承载新增业务裁决。
- `backend/app/services/message_ingestion_service.py`：入口适配壳，职责是接入与转发到 `brain_core/coordinator`。
- `backend/app/services/workflow_execution_service.py` 中历史兼容常量：
- `LEGACY_AGENT_DISPATCH_WORKFLOW_ID = "__direct_agent_fallback__"`
- `LEGACY_DIRECT_AGENT_DISPATCH_TYPE = "direct_agent_dispatch"`
- `LEGACY_DIRECT_AGENT_FALLBACK_MODE = "direct_agent_fallback"`
- `backend/app/brain_core/routing/service.py` 中 routing strategy 历史别名：
- `chat_direct_agent`（canonical 为 `chat_agent_dispatch`）
- `workflow_or_direct_agent_fallback`（canonical 为 `workflow_or_agent_dispatch_fallback`）
- `backend/app/brain_core/coordinator/service.py` 的 `brain_dispatch_summary.dispatch_type_legacy`：仅作为兼容读字段，不得回流为新的内部状态名。

约束：

- 兼容壳只能做输入归一化、别名映射、主链转发。
- 兼容壳不得新增裁决状态机、调度分支、审计写入策略。

---

## 3. 主链正式入口与正式执行路径

### 3.1 正式入口（唯一）

主消息正式入口链：

- 外部入口（API/Webhook/Channel）  
- `message_ingestion_service`（薄接入层）  
- `brain_core/coordinator`（主脑统一入口）

`coordinator` 内部正式裁决链：

- `reception` -> `routing` -> `orchestration` -> `manager/task_view`

### 3.2 正式执行路径（唯一）

主链执行出口固定为：

- `brain_core -> execution_gateway -> tentacle_adapters`

约束：

- 外接 Agent / Skill / MCP 仅执行，不接管主脑裁决权。
- 不允许绕过 `execution_gateway` 直接执行外接触手。

---

## 4. `direct_agent_*` 历史别名冻结与迁移

### 4.1 历史别名语义（兼容输入可读）

- `dispatch_context.type: direct_agent_dispatch` -> canonical: `agent_dispatch`
- `fallback_policy.mode: direct_agent_fallback` -> canonical: `agent_dispatch_fallback`
- `routing_strategy: workflow_or_direct_agent_fallback` -> canonical: `workflow_or_agent_dispatch_fallback`
- `routing_strategy: chat_direct_agent` -> canonical: `chat_agent_dispatch`
- `workflow_id: __direct_agent_fallback__` -> 历史 fallback 哨兵值（只读兼容）
- `brain_dispatch_summary.dispatch_type: direct_agent` -> canonical: `agent_dispatch`（兼容读字段：`dispatch_type_legacy`）

### 4.2 冻结策略（立即生效）

- 新代码禁止新增任何 `direct_agent_*` 命名、字段、事件类型。
- 内部写路径统一写 canonical 语义；别名只保留在读路径/兼容转换层。
- `direct_agent_dispatch` 不得重新回流为内部属性名、函数入参或运行态状态名。
- 已移除的历史 wrapper / 属性别名 / 入参别名不得重新引入。

### 4.3 迁移策略（分阶段，含下一轮清理清单）

- 阶段 1（已完成）：文档与守卫先行（本文件 + 架构检查脚本），阻止新别名扩散。
- 阶段 2（已完成）：盘点 `direct_agent_*` 存量并按类别收敛，已移除历史 wrapper、属性别名与兼容入参别名，生产残留从 9 条降到 4 条。
- 当前分类口径固定为：
- `constant_alias`：历史常量定义与常量赋值行。
- `string_literal`：历史字符串字面量（事件类型、fallback mode、workflow sentinel）。
- `test_wrapper`：测试代码中的兼容别名引用。
- `identifier_alias`：上述未覆盖的标识符残留。
- 阶段 3（当前状态）：进入防回流守卫期，允许测试夹具覆盖 legacy 读兼容，但生产代码只允许保留常量级兼容字符串。
- 阶段 4（收尾）：确认外部无依赖后，移除剩余 `constant_alias` 与冗余历史字符串映射。

下一轮 alias 清理准入门槛：

- 盘点报告中不允许出现“新增” `direct_agent_*` 引用（只允许存量下降）。
- canonical 写路径覆盖率达到 100%（别名仅可出现在兼容读路径与测试夹具）。
- 清理 PR 必须附带分类盘点前后对比与回滚点说明。

当前冻结基线（由 `backend/scripts/check_compatibility_boundaries.py --strict` 守卫）：

- 生产残留总数固定为 4 条，只允许继续下降，不允许新增或扩散到新文件。
- 允许保留的仅有：
- `workflow_execution_service.py` 中 3 个 legacy 常量字符串残留：
- `__direct_agent_fallback__`
- `direct_agent_dispatch`
- `direct_agent_fallback`
- `routing/service.py` 中 1 个历史 fallback alias 常量：
- `workflow_or_direct_agent_fallback`
- 以上 4 条全部收敛为 `constant_alias`，不再包含可执行 wrapper、属性别名或兼容入参写路径。

守卫策略：

- 严格模式现在不只检查 import 越界，也会检查 `direct_agent_*` 生产残留是否超出冻结基线。
- 若残留数量增加、扩散到新文件、或新增新的 legacy alias 形态，`check_compatibility_boundaries.py --strict` 会直接失败。

---

## 5. 不可外置/不可回流清单（主脑安全区红线）

以下能力绝不能从主脑安全区外置，或由外接触手回流覆盖：

- 安全策略裁决权：认证、限流、注入检测、脱敏策略及其放行/拦截判定。
- 审计真源：allow/rewrite/block 事件及关键 metadata 的落库与保真。
- 路由与编排裁决：`route_decision`、`manager_packet`、`execution_plan` 的最终裁决。
- 调度控制真源：dispatch/execution/agent job 生命周期与状态机写入。
- 租户/项目/环境隔离边界：scope 校验与访问控制。
- 记忆治理策略：可写入范围、脱敏规则、召回隔离策略。

禁止行为：

- 外接 Agent / Skill / MCP 直接写主脑真源状态（task/run/audit/security）。
- 外接触手返回结果后反向改写主脑安全判定或审计结论。
- 在主脑外部复制并演化第二套路由/编排裁决链。
