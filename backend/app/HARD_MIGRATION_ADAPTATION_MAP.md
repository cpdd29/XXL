# 后端硬搬迁适配清单

这份文档只服务当前阶段的目录整理，不讨论长期架构优化。

当前只采用 3 条规则：

1. 新目录里如果有明确对应的旧实现，就做硬搬迁。
2. 新目录里如果没有对应旧实现，就只记录缺口，后续新开发。
3. 凡是明显属于旧 `workflow` 主链语义的实现，先冻结，不迁入新结构。


## 一、状态定义

- `已硬搬/可继续沿用`：已经完成迁移，或者仍可直接从现有旧代码继续硬搬。
- `暂无旧实现`：新目录目标已存在，但旧代码里没有对应实现，只能后续新开发。
- `旧主链冻结`：旧代码存在，但明显带有旧 `workflow` 主链语义，当前不继续迁入新结构。
- `执行内核保留`：当前仍是基础运行底座，不作为本轮迁移删除对象。


## 二、modules 目录

### 1. reception

| 目标目录 | 当前判断 | 旧实现来源 / 备注 |
|---|---|---|
| `modules/reception/api` | 已硬搬/可继续沿用 | 已接入旧 `messages.py`、`webhooks.py` |
| `modules/reception/application` | 已硬搬/可继续沿用 | 已接入旧 `message_ingestion_service.py` |
| `modules/reception/security_monitor` | 已硬搬/可继续沿用 | 已接入旧 `security_gateway_service.py`、`security_service.py`、`webhook_guard_service.py` |
| `modules/reception/channel_ingress` | 部分已硬搬，部分暂无旧实现 | `dingtalk_stream_service.py` 已迁；Telegram/企微/飞书在 `app/adapters/*.py` 有适配代码，但没有同形态旧 service |
| `modules/reception/outbound` | 已硬搬/可继续沿用 | 已接入旧 `channel_outbound_service.py` |
| `modules/reception/agent_entry` | 暂无旧实现 | 没有独立的 Hermes / 接待 Agent 入口层旧实现 |
| `modules/reception/nats_bus` | 暂无旧实现 | 没有接待层内部 NATS 协作旧实现 |
| `modules/reception/schemas` | 暂无旧实现 | 只有零散 schema，没有完整的接待层内部结构目录 |

### 2. dispatch

| 目标目录 | 当前判断 | 旧实现来源 / 备注 |
|---|---|---|
| `modules/dispatch/api` | 已硬搬/可继续沿用 | 已接入旧 `tasks.py` |
| `modules/dispatch/application` | 已硬搬/可继续沿用 | 已接入旧 `task_service.py` |
| `modules/dispatch/execution_support` | 已硬搬/可继续沿用 | 已接入旧 `document_search_service.py`、`language_service.py` |
| `modules/dispatch/single_agent_runtime` | 已硬搬/可继续沿用 | 已接入旧 `agent_execution_service.py`、`agent_execution_worker_service.py`、`free_workflow_service.py` |
| `modules/dispatch/multi_agent_runtime` | 已硬搬/可继续沿用 | 已接入旧 `professional_workflow_service.py` |
| `modules/dispatch/skill_runtime` | 已硬搬/可继续沿用 | 已接入旧 `skill_runtime_service.py` |
| `modules/dispatch/requirement_dispatch_agent` | 暂无旧实现 | 没有独立的“需求分发 Agent 接入层”旧实现 |
| `modules/dispatch/schemas` | 暂无旧实现 | 只有散落 schema，没有调度专属结构目录 |
| `modules/dispatch/workflow_runtime` | 旧主链冻结 | 当前目录里的 `workflow_*` 运行时与旧执行主链强耦合，先不再作为新结构继续扩张 |

需要冻结的旧代码：

- `app/services/mandatory_workflow_registry_service.py`
- `app/services/mandatory_workflow_module_registry_service.py`
- `app/services/execution_directory_service.py`

这 3 个文件都和旧 `workflow` 主链强绑定，当前不应继续迁入新结构。

### 3. agent_config

| 目标目录 | 当前判断 | 旧实现来源 / 备注 |
|---|---|---|
| `modules/agent_config/api` | 已硬搬/可继续沿用 | 已接入旧 `agents.py`、`tools.py`、`tool_sources.py` |
| `modules/agent_config/registries` | 已硬搬/可继续沿用 | 已接入旧 `agent_service.py`、`brain_skill_service.py`、`tool_source_service.py`、`tool_catalog_service.py`、`mcp_runtime_service.py`、`external_*_registry_service.py`、`mandatory_agent_registry_service.py` |
| `modules/agent_config/node_bindings` | 暂无旧实现 | 目前没有独立的“节点绑定中心”旧实现，只能后续新开发 |

### 4. organization

| 目标目录 | 当前判断 | 旧实现来源 / 备注 |
|---|---|---|
| `modules/organization/api` | 已硬搬/可继续沿用 | 已接入旧 `profiles.py`、`users.py`、`memory.py` |
| `modules/organization/application` | 已硬搬/可继续沿用 | 已接入旧 `profile_service.py`、`user_service.py`、`tenancy_service.py`、`memory_service.py` |


## 三、platform 目录

| 目标目录 | 当前判断 | 旧实现来源 / 备注 |
|---|---|---|
| `platform/auth` | 已硬搬/可继续沿用 | 已接入旧 `auth_service.py`、`authz.py`、`external_connection_auth_service.py` |
| `platform/config` | 已硬搬/可继续沿用 | 已接入旧 `settings_service.py` |
| `platform/messaging` | 已硬搬/可继续沿用 | 已接入旧 `nats_event_bus.py`、`redis_client.py` |
| `platform/contracts` | 已硬搬/可继续沿用 | 已接入旧 `agent_protocol.py`、`event_protocol.py`、`event_subjects.py`、`event_types.py` |
| `platform/observability` | 已硬搬/可继续沿用 | 已接入旧 `dashboard_service.py`、`alert_center_service.py`、`operational_log_service.py`、`trace_exporter_service.py` |
| `platform/persistence` | 已硬搬/可继续沿用 | 已接入旧 `persistence_service.py` |
| `platform/audit` | 已硬搬/可继续沿用 | 已接入旧 `control_plane_audit_service.py`、`event_journal_service.py` |
| `platform/security` | 已硬搬/可继续沿用 | 已接入旧 `encryption_service.py` |
| `platform/approval` | 已硬搬/可继续沿用 | 已接入旧 `control_plane_approval_service.py` |


## 四、剩余旧 services 判断

### 0. 已完成目录收口

- `app/api/routes/` 兼容壳已删除，旧路由文件已分别搬入：
  - `platform/auth/api`
  - `platform/approval/api`
  - `platform/audit/api`
  - `platform/config/api`
  - `platform/observability/api`
  - `modules/agent_config/api`
  - `modules/reception/api`
- `app/core/__init__.py` 已取消对 `platform/*` 的兼容别名转发，只保留真实核心子模块包说明。
- `app/infrastructure/` 已确认无运行时引用，已物理删除。
- `app/tentacle_adapters/` 已确认无运行时引用，已物理删除。

### 1. 已删除兼容薄壳

这些旧文件原先只承担兼容转发，当前已经完成引用切换并删除：

- `app/services/control_plane_approval_service.py`
- `app/services/document_search_service.py`
- `app/services/encryption_service.py`
- `app/services/external_connection_auth_service.py`
- `app/services/language_service.py`
- `app/services/memory_service.py`
- `app/services/skill_runtime_service.py`

### 2. 暂冻结，不迁

这些文件虽然还有实现，但属于旧执行主链，不应继续迁入新结构：

- `app/services/execution_directory_service.py`
- `app/services/mandatory_workflow_module_registry_service.py`
- `app/services/mandatory_workflow_registry_service.py`

### 3. 必须保留的执行内核

- `app/services/store.py`

当前 `store.py` 仍被大量运行时、测试和脚本直接依赖，属于执行底座，不作为这一轮目录搬迁对象。


## 五、后续开发直接依据这份清单

后续如果继续整理目录，只按下面规则执行：

1. 目录在这份文档里标记为 `已硬搬/可继续沿用` 的，可以继续做纯搬迁和清兼容层。
2. 目录在这份文档里标记为 `暂无旧实现` 的，不要硬从旧主链里凑实现，直接按新结构新开发。
3. 目录或旧文件在这份文档里标记为 `旧主链冻结` 的，当前不继续迁。
