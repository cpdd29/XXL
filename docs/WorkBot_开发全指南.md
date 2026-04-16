# WorkBot 企业级多Agent工作机器人 · 完整开发指南

> 版本: v1.0 | 状态: 开发蓝图 | 目标: 多平台接入 + 多Agent协作 + 可视化工作流 + 本地安全存储

---

## 目录

1. [项目背景与目标](#1-项目背景与目标)
2. [架构总览与优先级](#2-架构总览与优先级)
3. [技术栈选型](#3-技术栈选型)
4. [数据库设计](#4-数据库设计)
5. [后端开发任务](#5-后端开发任务)
6. [前端开发任务](#6-前端开发任务)
7. [Agent设计与通信 (NATS)](#7-agent设计与通信-nats)
8. [工作流引擎方案](#8-工作流引擎方案)
9. [用户数据加密与权限体系](#9-用户数据加密与权限体系)
10. [Agent配置文件规范 (agents.md + soul.md)](#10-agent配置文件规范-agentsmd--soulmd)
11. [快速落地方案 (Codex + GPT多Agent并行开发)](#11-快速落地方案-codex--gpt多agent并行开发)
12. [MVP开发检查清单](#12-mvp开发检查清单)

---

## 1. 项目背景与目标

### 背景
市面上现有的工作机器人（如企业版ChatBot、Dify私有部署）功能单一，缺乏：
- 跨平台统一管理（钉钉/企微/TG/及时沟通）
- 多Agent真正协同可视化
- 用户级别隔离的记忆与画像
- 可定制化工作流（非代码配置）
- 完整的安全审计体系

### 产品目标
```
用户在任意平台发消息
    → WorkBot 接收并理解意图
    → 自动分配给合适的Agent(s)
    → 多Agent协作完成任务
    → 结果汇总返回用户
    → 全程可视化 + 安全审计
```

### 核心特性
| 特性 | 描述 |
|------|------|
| 多平台接入 | 钉钉、企业微信、Telegram、及时沟通统一消息网关 |
| Master Bot | 意图识别 + 任务路由 + 结果聚合的中枢大脑 |
| 模块化Agent | 每个Agent独立配置、独立工具集、可热插拔 |
| 可视化工作流 | 拖拽式流程设计，实时展示Agent协作状态 |
| 本地记忆隔离 | 每用户独立加密存储，画像+对话历史 |
| 安全监控Agent | Prompt注入检测、权限控制、审计日志 |

---

## 2. 架构总览与优先级

### 系统分层架构

```
┌─────────────────────────────────────────────────────┐
│            第一层：接入层 (Channel Adapters)          │
│  钉钉  │  企业微信  │  Telegram  │  及时沟通          │
└─────────────────────┬───────────────────────────────┘
                      │ 统一消息对象 (UnifiedMessage)
┌─────────────────────▼───────────────────────────────┐
│        第二层：安全网关 (Security Gateway)            │
│  Prompt注入检测 │ 敏感词过滤 │ 频率限制 │ 权限校验    │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│         第三层：Master Bot (核心调度引擎)              │
│  意图识别 │ 任务分解 │ Agent路由 │ 结果聚合 │ 上下文   │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──┐    ┌──────▼──┐   ┌──────▼──────────────┐
│ Agent A │    │ Agent B │   │     工作流引擎        │
│搜索Agent│    │写作Agent│   │  (可视化编排节点)     │
└──────┬──┘    └──────┬──┘   └──────┬───────────────┘
       └──────┬────────┘             │
              │ NATS 消息总线         │
┌─────────────▼────────────────────────────────────── ┐
│         第四层：存储层 (本地加密)                      │
│  PostgreSQL  │  ChromaDB  │  Redis  │  本地文件系统   │
└─────────────────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────┐
│     第五层：可视化面板 (Web Dashboard)                │
│  工作流编辑器 │ Agent协作图 │ 任务看板 │ 安全日志      │
└─────────────────────────────────────────────────────┘
```

### ⭐ 开发优先级（什么最重要）

```
P0 最高优先级（必须先做）
├── 统一消息适配器（接入层）
├── Master Bot 意图识别 + 路由
├── 安全网关（输入过滤）
└── 本地存储基础架构 + 加密

P1 核心功能（MVP必须有）
├── 至少2个工作Agent（搜索 + 写作）
├── NATS 消息通信
├── 用户记忆存储（SQLite起步）
└── 基础权限（用户/管理员）

P2 增强功能（第二阶段）
├── 可视化工作流编辑器
├── 用户画像系统
├── 多平台全接入
└── 审计日志面板

P3 完整版（第三阶段）
├── Agent市场（插件化管理）
├── 完整RBAC权限
├── 性能监控 + 告警
└── 多租户支持
```

---

## 3. 技术栈选型

### 后端

```yaml
语言: Python 3.11+

核心框架:
  - FastAPI          # 主Web框架，异步，自动生成API文档
  - LangGraph        # 多Agent编排（有状态、支持循环、支持并发）
  - LangChain        # Agent工具链基础库

消息通信:
  - NATS             # Agent间高性能消息总线（替代方案：Redis Pub/Sub）
  - nats-py          # Python NATS客户端

任务队列:
  - Celery + Redis   # 异步任务处理
  - Redis            # 缓存 + 会话存储 + 消息队列

数据库:
  - PostgreSQL 15+   # 主数据库（用户、任务、工作流）
  - ChromaDB         # 本地向量数据库（语义记忆检索）
  - SQLite           # 轻量本地存储（MVP阶段可用）

工作流引擎:
  - Prefect          # 可视化工作流编排（支持私有部署）
  - 或 自研 + ReactFlow前端

安全:
  - cryptography     # AES-256-GCM 加密
  - PyJWT            # JWT Token
  - python-jose      # JOSE标准
  - slowapi          # API限流

监控:
  - Prometheus       # 指标采集
  - structlog        # 结构化日志
```

### 前端

```yaml
框架: React 18 + TypeScript + Vite

核心库:
  - ReactFlow        # 工作流可视化编辑器（Agent协作图）
  - Zustand          # 状态管理（轻量）
  - TanStack Query   # 数据请求 + 缓存
  - Socket.IO Client # WebSocket实时通信

UI组件:
  - Tailwind CSS     # 样式
  - shadcn/ui        # 组件库
  - Recharts         # 数据图表

工具:
  - Axios            # HTTP请求
  - React Router v6  # 路由
  - React Hook Form  # 表单
  - date-fns         # 日期处理
```

### 部署

```yaml
容器: Docker + Docker Compose
反向代理: Nginx
本地部署: 单机 Docker Compose（MVP）
生产扩展: K8s（后期）
```

---

## 4. 数据库设计

### PostgreSQL 表结构

#### 用户相关

```sql
-- 用户表
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_id     VARCHAR(128) NOT NULL,        -- 平台原始用户ID
    platform        VARCHAR(32) NOT NULL,         -- dingtalk/wecom/telegram/jishi
    display_name    VARCHAR(128),
    role            VARCHAR(32) DEFAULT 'user',   -- user/admin/super_admin
    status          VARCHAR(16) DEFAULT 'active', -- active/blocked/pending
    encrypted_meta  TEXT,                         -- AES加密的用户元数据JSON
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform_id, platform)
);

-- 用户画像（加密存储）
CREATE TABLE user_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    profile_key     VARCHAR(64) NOT NULL,          -- 画像字段key
    encrypted_value TEXT NOT NULL,                 -- AES加密的value
    vector_id       VARCHAR(128),                  -- Chroma向量ID（语义检索用）
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, profile_key)
);

-- 会话表
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    platform        VARCHAR(32) NOT NULL,
    context_window  JSONB DEFAULT '[]',            -- 最近N条消息上下文
    summary         TEXT,                          -- 历史摘要（压缩后）
    last_active_at  TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### 任务相关

```sql
-- 任务表
CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    session_id      UUID REFERENCES sessions(id),
    title           VARCHAR(256),
    intent          VARCHAR(64),                   -- 意图类型
    status          VARCHAR(32) DEFAULT 'pending', -- pending/running/done/failed/cancelled
    priority        SMALLINT DEFAULT 5,            -- 1-10
    input_payload   JSONB,                         -- 用户原始输入
    output_payload  JSONB,                         -- 最终输出
    workflow_id     UUID,                          -- 关联工作流（可空）
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error_msg       TEXT
);

-- 子任务/Agent执行记录
CREATE TABLE task_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id        VARCHAR(64) NOT NULL,          -- 执行该步骤的Agent ID
    step_order      SMALLINT NOT NULL,
    action          VARCHAR(128),                  -- Agent执行的动作
    input           JSONB,
    output          JSONB,
    status          VARCHAR(32) DEFAULT 'pending',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    tokens_used     INTEGER DEFAULT 0,
    error_msg       TEXT
);
```

#### 工作流相关

```sql
-- 工作流定义
CREATE TABLE workflows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL,
    description     TEXT,
    version         INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT true,
    owner_id        UUID REFERENCES users(id),
    flow_json       JSONB NOT NULL,                -- ReactFlow节点+边 的JSON
    trigger_intent  VARCHAR(64)[],                 -- 触发该工作流的意图列表
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 工作流执行历史
CREATE TABLE workflow_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID REFERENCES workflows(id),
    task_id         UUID REFERENCES tasks(id),
    status          VARCHAR(32) DEFAULT 'running',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    step_states     JSONB DEFAULT '{}'             -- 各节点执行状态
);
```

#### Agent相关

```sql
-- Agent注册表
CREATE TABLE agents (
    id              VARCHAR(64) PRIMARY KEY,       -- 如 "search_agent_v1"
    name            VARCHAR(128) NOT NULL,
    description     TEXT,
    version         VARCHAR(16) NOT NULL,
    config_path     VARCHAR(256),                  -- agents.md文件路径
    soul_path       VARCHAR(256),                  -- soul.md文件路径
    capabilities    TEXT[],                        -- 能力标签
    model           VARCHAR(64),                   -- 使用的LLM
    status          VARCHAR(16) DEFAULT 'active',  -- active/inactive/maintenance
    is_builtin      BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### 安全相关

```sql
-- 审计日志
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    event_type      VARCHAR(64) NOT NULL,          -- message_in/task_start/permission_denied等
    severity        VARCHAR(16) DEFAULT 'info',    -- info/warn/error/critical
    platform        VARCHAR(32),
    ip_address      INET,
    payload         JSONB,                         -- 脱敏后的事件数据
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 封禁规则
CREATE TABLE security_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_type       VARCHAR(32) NOT NULL,           -- keyword/pattern/rate_limit
    rule_value      TEXT NOT NULL,
    action          VARCHAR(32) DEFAULT 'block',    -- block/warn/flag
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- API密钥表（平台Webhook密钥等）
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128),
    key_hash        VARCHAR(256) NOT NULL,          -- 只存hash，不存原文
    platform        VARCHAR(32),
    permissions     TEXT[] DEFAULT '{}',
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### ChromaDB 集合设计

```python
# 向量数据库集合规划
collections = {
    "user_memories": {
        "description": "用户长期记忆，语义检索",
        "metadata_fields": ["user_id", "memory_type", "created_at", "importance"]
    },
    "knowledge_base": {
        "description": "企业知识库，Agent RAG检索",
        "metadata_fields": ["doc_id", "doc_type", "source", "created_at"]
    },
    "agent_experiences": {
        "description": "Agent成功/失败经验积累",
        "metadata_fields": ["agent_id", "task_type", "outcome"]
    }
}
```

### Redis Key设计

```
session:{user_id}:{platform}       → Hash: 会话上下文 (TTL: 2h)
rate_limit:{user_id}               → String: 请求计数 (TTL: 60s)
task:queue:high                    → List: 高优先级任务队列
task:queue:normal                  → List: 普通任务队列
agent:status:{agent_id}            → Hash: Agent状态
workflow:state:{run_id}            → Hash: 工作流执行状态
```

---

## 5. 后端开发任务

### 项目目录结构

```
workbot-backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置管理
│   ├── adapters/                  # 平台适配器
│   │   ├── base.py                # 统一消息基类
│   │   ├── dingtalk.py
│   │   ├── wecom.py
│   │   ├── telegram.py
│   │   └── jishi.py
│   ├── core/
│   │   ├── master_bot.py          # Master Bot 主调度逻辑
│   │   ├── intent.py              # 意图识别
│   │   ├── router.py              # 任务路由
│   │   └── aggregator.py         # 结果聚合
│   ├── agents/
│   │   ├── base_agent.py          # Agent基类
│   │   ├── search_agent.py
│   │   ├── writer_agent.py
│   │   ├── code_agent.py
│   │   ├── data_agent.py
│   │   └── security_agent.py      # 安全监控Agent
│   ├── workflow/
│   │   ├── engine.py              # 工作流执行引擎
│   │   ├── nodes.py               # 节点类型定义
│   │   └── executor.py            # 节点执行器
│   ├── messaging/
│   │   ├── nats_client.py         # NATS连接管理
│   │   ├── topics.py              # 主题/Subject定义
│   │   └── handlers.py            # 消息处理器
│   ├── memory/
│   │   ├── short_term.py          # Redis短期记忆
│   │   ├── long_term.py           # PostgreSQL + Chroma长期记忆
│   │   └── profile.py             # 用户画像管理
│   ├── security/
│   │   ├── encryption.py          # AES-256-GCM加密工具
│   │   ├── auth.py                # JWT认证
│   │   ├── rbac.py                # 角色权限控制
│   │   ├── filter.py              # 输入过滤/Prompt注入检测
│   │   └── audit.py               # 审计日志
│   ├── api/
│   │   ├── routes/
│   │   │   ├── webhooks.py        # 平台Webhook接收
│   │   │   ├── tasks.py           # 任务管理API
│   │   │   ├── workflows.py       # 工作流CRUD
│   │   │   ├── agents.py          # Agent管理
│   │   │   ├── users.py           # 用户管理
│   │   │   └── dashboard.py       # Dashboard数据
│   │   └── middleware.py          # 中间件
│   ├── models/                    # SQLAlchemy ORM模型
│   ├── schemas/                   # Pydantic数据校验
│   └── utils/
├── agents_config/                 # Agent配置文件目录
│   ├── search_agent/
│   │   ├── agents.md
│   │   └── soul.md
│   ├── writer_agent/
│   │   ├── agents.md
│   │   └── soul.md
│   └── security_agent/
│       ├── agents.md
│       └── soul.md
├── alembic/                       # 数据库迁移
├── tests/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### 后端API接口清单

```
POST /webhooks/{platform}          接收平台消息（钉钉/企微/TG等）
GET  /webhooks/{platform}/verify   平台验证（钉钉Token验证等）

POST /api/tasks                    创建任务
GET  /api/tasks/{task_id}          查询任务状态
GET  /api/tasks/{task_id}/steps    查询子步骤
DELETE /api/tasks/{task_id}        取消任务

GET  /api/workflows                列出工作流
POST /api/workflows                创建工作流
PUT  /api/workflows/{id}           更新工作流
DELETE /api/workflows/{id}         删除工作流
POST /api/workflows/{id}/run       手动触发工作流

GET  /api/agents                   列出所有Agent
GET  /api/agents/{id}/status       Agent状态
POST /api/agents/{id}/reload       热重载Agent配置

GET  /api/users                    用户列表
GET  /api/users/{id}/profile       用户画像
PUT  /api/users/{id}/role          修改用户角色
POST /api/users/{id}/block         封禁用户

GET  /api/dashboard/stats          仪表盘统计数据
GET  /api/dashboard/logs           审计日志（分页）
GET  /api/dashboard/realtime       WebSocket实时数据流

POST /api/auth/login               管理员登录
POST /api/auth/refresh             Token刷新
```

---

## 6. 前端开发任务

### 页面结构

```
workbot-frontend/
├── src/
│   ├── pages/
│   │   ├── Dashboard/             # 主控制台
│   │   │   ├── index.tsx          # 概览：任务统计/Agent状态/实时消息流
│   │   │   └── StatsCards.tsx
│   │   ├── WorkflowEditor/        # 工作流编辑器（核心页面）
│   │   │   ├── index.tsx          # ReactFlow画布
│   │   │   ├── NodePanel.tsx      # 左侧节点面板（拖拽源）
│   │   │   ├── nodes/             # 自定义节点
│   │   │   │   ├── AgentNode.tsx  # Agent节点（显示状态）
│   │   │   │   ├── ConditionNode.tsx
│   │   │   │   ├── TriggerNode.tsx
│   │   │   │   └── OutputNode.tsx
│   │   │   └── EdgeTypes.tsx      # 自定义边（带动画）
│   │   ├── AgentColab/            # Agent协作实时可视化
│   │   │   ├── index.tsx          # 实时任务执行流转图
│   │   │   └── AgentStatusBar.tsx
│   │   ├── Tasks/                 # 任务管理
│   │   │   ├── index.tsx          # 任务列表（看板视图）
│   │   │   └── TaskDetail.tsx     # 任务详情 + 步骤时间线
│   │   ├── Agents/                # Agent管理
│   │   │   ├── index.tsx          # Agent列表 + 状态
│   │   │   └── AgentConfig.tsx    # 查看/编辑agents.md
│   │   ├── Users/                 # 用户管理
│   │   │   ├── index.tsx          # 用户列表
│   │   │   └── UserProfile.tsx    # 用户画像（脱敏展示）
│   │   └── Security/              # 安全日志
│   │       ├── AuditLog.tsx       # 审计日志
│   │       └── SecurityRules.tsx  # 过滤规则管理
│   ├── components/
│   │   ├── Layout/                # 整体布局
│   │   ├── RealtimeLog/           # 实时消息滚动展示
│   │   └── AgentAvatar/           # Agent头像+状态指示器
│   ├── hooks/
│   │   ├── useWebSocket.ts        # WebSocket实时数据
│   │   ├── useTaskStream.ts       # 任务执行流监听
│   │   └── useAgentStatus.ts      # Agent状态轮询
│   └── store/
│       ├── workflowStore.ts       # 工作流状态
│       ├── taskStore.ts           # 任务状态
│       └── agentStore.ts          # Agent状态
```

### 核心页面设计说明

**工作流编辑器页面**
```
┌──────────────────────────────────────────────────────┐
│  工具栏: [保存] [运行] [版本历史] [导入/导出]          │
├────────────┬─────────────────────────────────────────┤
│  节点面板  │                                          │
│  ─────── │         ReactFlow 画布                    │
│  触发节点  │                                          │
│  Agent节点│   [触发] → [安全检测] → [意图识别]        │
│  条件节点  │                  ↓              ↓        │
│  工具节点  │           [搜索Agent]     [写作Agent]     │
│  输出节点  │                  ↓              ↓        │
│           │              [聚合节点] → [发送结果]       │
│           │                                          │
├────────────┴─────────────────────────────────────────┤
│  底部: 节点属性配置面板（点击节点展开）                 │
└──────────────────────────────────────────────────────┘
```

**Agent协作实时图页面**
```
执行任务时，节点高亮 + 边上有流动动画，显示：
- 每个Agent当前状态（空闲/运行中/等待/错误）
- 消息在Agent间流转的动画
- 每个Agent已处理的Token数
- 实时日志侧边栏
```

---

## 7. Agent设计与通信 (NATS)

### 为什么选 NATS

| 对比项 | NATS | Redis Pub/Sub | Kafka |
|--------|------|--------------|-------|
| 延迟 | 极低 (<1ms) | 低 | 中 |
| 部署复杂度 | 极简（单二进制） | 简单 | 复杂 |
| 持久化 | JetStream支持 | 不支持 | 支持 |
| 适合场景 | Agent间实时通信 | 简单广播 | 大规模日志 |
| 推荐度 | ✅ 首选 | 备选 | 不适合 |

### NATS Subject（主题）设计

```
# 任务分发
workbot.task.new                    # 新任务广播
workbot.task.{task_id}.update       # 特定任务状态更新
workbot.task.{task_id}.result       # 任务结果

# Agent通信
workbot.agent.{agent_id}.inbox      # 特定Agent的收件箱
workbot.agent.{agent_id}.status     # Agent状态上报
workbot.agent.broadcast             # 向所有Agent广播

# 工作流
workbot.workflow.{run_id}.step      # 工作流步骤执行
workbot.workflow.{run_id}.done      # 工作流完成

# 安全
workbot.security.alert              # 安全告警
workbot.security.block              # 拦截事件

# 监控
workbot.monitor.metrics             # 指标上报
workbot.monitor.heartbeat           # Agent心跳
```

### NATS 代码实现示例

```python
# messaging/nats_client.py
import nats
from nats.aio.client import Client as NATS

class NATSManager:
    def __init__(self):
        self.nc: NATS = None
        self.js = None  # JetStream（持久化消息）

    async def connect(self, servers: list[str]):
        self.nc = await nats.connect(servers)
        self.js = self.nc.jetstream()

    async def publish(self, subject: str, data: dict):
        import json
        payload = json.dumps(data).encode()
        await self.nc.publish(subject, payload)

    async def subscribe(self, subject: str, callback):
        await self.nc.subscribe(subject, cb=callback)

    async def request(self, subject: str, data: dict, timeout: float = 5.0):
        """Request-Reply 模式：Agent请求 + 等待响应"""
        import json
        payload = json.dumps(data).encode()
        response = await self.nc.request(subject, payload, timeout=timeout)
        return json.loads(response.data)

# Agent基类中的NATS使用
class BaseAgent:
    def __init__(self, agent_id: str, nats_manager: NATSManager):
        self.agent_id = agent_id
        self.nats = nats_manager

    async def start(self):
        # 订阅自己的收件箱
        await self.nats.subscribe(
            f"workbot.agent.{self.agent_id}.inbox",
            self._handle_message
        )
        # 定期发送心跳
        asyncio.create_task(self._heartbeat())

    async def _handle_message(self, msg):
        data = json.loads(msg.data)
        result = await self.process(data)
        # 发布结果
        await self.nats.publish(
            f"workbot.task.{data['task_id']}.result",
            {"agent_id": self.agent_id, "result": result}
        )

    async def _heartbeat(self):
        while True:
            await self.nats.publish(
                f"workbot.monitor.heartbeat",
                {"agent_id": self.agent_id, "status": "alive", "ts": time.time()}
            )
            await asyncio.sleep(10)

    async def process(self, task_data: dict) -> dict:
        raise NotImplementedError
```

### Master Bot 路由逻辑

```python
# core/master_bot.py
class MasterBot:
    async def handle_message(self, message: UnifiedMessage):
        # 1. 安全过滤
        safe = await self.security_agent.check(message)
        if not safe:
            return

        # 2. 意图识别
        intent = await self.intent_recognizer.recognize(message.text)

        # 3. 加载用户上下文
        context = await self.memory.get_context(message.user_id)

        # 4. 路由决策：找工作流 or 直接分配Agent
        workflow = await self.find_workflow(intent)
        if workflow:
            run_id = await self.workflow_engine.run(workflow, message, context)
        else:
            agents = await self.router.select_agents(intent)
            await self.dispatch_to_agents(agents, message, context)

    async def find_workflow(self, intent: str):
        # 查数据库，看有没有匹配该意图的工作流
        return await WorkflowService.find_by_intent(intent)
```

---

## 8. 工作流引擎方案

### 推荐方案：自研引擎 + Prefect 调度 + ReactFlow 可视化

不推荐完全使用 Dify（锁定性太强），推荐**自研工作流执行引擎 + ReactFlow可视化编辑器**。

### 工作流节点类型

```python
# workflow/nodes.py
from enum import Enum

class NodeType(str, Enum):
    TRIGGER     = "trigger"      # 触发器（消息触发/定时触发）
    AGENT       = "agent"        # 执行某个Agent
    CONDITION   = "condition"    # 条件分支 (if/else)
    PARALLEL    = "parallel"     # 并行执行多个Agent
    MERGE       = "merge"        # 合并并行结果
    TOOL        = "tool"         # 直接调用工具（搜索/API等）
    TRANSFORM   = "transform"    # 数据转换
    OUTPUT      = "output"       # 输出到用户

# 节点配置schema
NODE_SCHEMAS = {
    NodeType.AGENT: {
        "agent_id": "string",       # 使用哪个Agent
        "input_mapping": "dict",    # 输入字段映射
        "output_key": "string",     # 输出存到哪个变量
        "timeout": "int"            # 超时时间（秒）
    },
    NodeType.CONDITION: {
        "condition": "string",      # Python表达式，如 "output.score > 0.8"
        "true_next": "node_id",
        "false_next": "node_id"
    }
}
```

### 工作流 JSON 格式（存入数据库的 flow_json）

```json
{
  "version": "1.0",
  "nodes": [
    {
      "id": "trigger_1",
      "type": "trigger",
      "data": { "trigger_type": "message", "intent": ["search", "research"] },
      "position": { "x": 100, "y": 100 }
    },
    {
      "id": "security_1",
      "type": "agent",
      "data": { "agent_id": "security_agent", "timeout": 5 },
      "position": { "x": 300, "y": 100 }
    },
    {
      "id": "search_1",
      "type": "agent",
      "data": { "agent_id": "search_agent", "output_key": "search_result" },
      "position": { "x": 500, "y": 100 }
    },
    {
      "id": "output_1",
      "type": "output",
      "data": { "template": "根据搜索结果：{{search_result}}" },
      "position": { "x": 700, "y": 100 }
    }
  ],
  "edges": [
    { "id": "e1", "source": "trigger_1", "target": "security_1" },
    { "id": "e2", "source": "security_1", "target": "search_1" },
    { "id": "e3", "source": "search_1", "target": "output_1" }
  ]
}
```

### Prefect 集成（任务调度 + 监控）

```python
# workflow/executor.py
from prefect import flow, task
import prefect

@task(retries=2, retry_delay_seconds=5)
async def run_agent_node(agent_id: str, input_data: dict) -> dict:
    agent = AgentRegistry.get(agent_id)
    return await agent.process(input_data)

@flow(name="workbot-workflow")
async def execute_workflow(flow_json: dict, context: dict):
    # 解析节点和边
    nodes = {n['id']: n for n in flow_json['nodes']}
    edges = flow_json['edges']
    
    # 拓扑排序后按序执行
    results = {}
    for node_id in topological_sort(nodes, edges):
        node = nodes[node_id]
        if node['type'] == 'agent':
            result = await run_agent_node(
                node['data']['agent_id'],
                build_input(node, results)
            )
            results[node_id] = result
    return results
```

---

## 9. 用户数据加密与权限体系

### 加密方案：AES-256-GCM（本地密钥）

```python
# security/encryption.py
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os, base64, json

class EncryptionService:
    def __init__(self, master_key: bytes):
        """master_key: 从环境变量或本地密钥文件读取，绝不存数据库"""
        self.master_key = master_key

    def _derive_user_key(self, user_id: str) -> bytes:
        """为每个用户派生独立的加密密钥（用户级隔离）"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=user_id.encode(),
            iterations=100_000,
        )
        return kdf.derive(self.master_key)

    def encrypt(self, user_id: str, data: dict) -> str:
        key = self._derive_user_key(user_id)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit nonce
        plaintext = json.dumps(data).encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        # 存储格式: base64(nonce + ciphertext)
        return base64.b64encode(nonce + ciphertext).decode()

    def decrypt(self, user_id: str, encrypted: str) -> dict:
        key = self._derive_user_key(user_id)
        aesgcm = AESGCM(key)
        raw = base64.b64decode(encrypted)
        nonce, ciphertext = raw[:12], raw[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext)

# 密钥管理原则：
# 1. MASTER_KEY 从环境变量读取: os.environ['WORKBOT_MASTER_KEY']
# 2. 生成方式: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
# 3. 本地存储在 .env 文件（绝不提交Git）
# 4. 生产环境使用 HashiCorp Vault 或系统Keyring
```

### RBAC 权限体系

```python
# security/rbac.py
from enum import Enum

class Role(str, Enum):
    SUPER_ADMIN = "super_admin"   # 所有权限
    ADMIN       = "admin"         # 管理用户、查看日志、编辑工作流
    POWER_USER  = "power_user"    # 创建工作流、管理自己的Agent
    USER        = "user"          # 基础对话功能
    BLOCKED     = "blocked"       # 被封禁

PERMISSIONS = {
    Role.SUPER_ADMIN: ["*"],  # 通配符，所有权限
    Role.ADMIN: [
        "users:read", "users:write", "users:block",
        "workflows:read", "workflows:write", "workflows:delete",
        "agents:read", "agents:reload",
        "logs:read", "security:manage"
    ],
    Role.POWER_USER: [
        "workflows:read", "workflows:write",
        "agents:read",
        "tasks:read", "tasks:write"
    ],
    Role.USER: [
        "tasks:read", "tasks:write",
        "profile:read", "profile:write"
    ],
    Role.BLOCKED: []
}

def require_permission(permission: str):
    """FastAPI依赖注入装饰器"""
    def decorator(current_user = Depends(get_current_user)):
        user_perms = PERMISSIONS.get(current_user.role, [])
        if "*" not in user_perms and permission not in user_perms:
            raise HTTPException(403, "Permission denied")
        return current_user
    return decorator

# 使用示例
@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: str,
    user = Depends(require_permission("users:write"))
):
    ...
```

---

## 10. Agent配置文件规范 (agents.md + soul.md)

### 文件结构说明

每个Agent目录包含两个配置文件：
- `agents.md`：技术配置（工具、能力、路由规则）
- `soul.md`：人格配置（性格、沟通风格、核心原则）

### agents.md 规范（技术配置）

```markdown
---
# ========================================
# agents.md - Agent技术配置文件
# 版本: v{major}.{minor}  日期: YYYY-MM-DD
# ========================================

agent_id: search_agent
version: "1.2.0"
name: "搜索助理"
model: "claude-3-5-sonnet-20241022"   # 支持热切换
status: active

## 能力标签
capabilities:
  - web_search
  - document_retrieval
  - fact_checking
  - news_monitoring

## 触发意图（Master Bot路由依据）
trigger_intents:
  - search
  - find
  - lookup
  - research
  - news

## 工具配置
tools:
  - name: web_search
    provider: tavily           # tavily / serper / bing
    max_results: 10
    timeout: 10

  - name: vector_search
    collection: knowledge_base
    top_k: 5
    threshold: 0.75

  - name: url_fetcher
    max_content_length: 50000

## 执行配置
execution:
  max_iterations: 5            # 最多思考5次
  timeout_seconds: 60
  parallel: false              # 是否允许并发执行（同一任务多实例）
  retry_on_failure: 2

## 输入/输出Schema
input_schema:
  query: string                # 必填，搜索查询
  context: object              # 可选，对话上下文
  user_id: string              # 必填，用于记忆检索

output_schema:
  results: array               # 搜索结果列表
  summary: string              # 摘要
  sources: array               # 来源引用
  confidence: float            # 置信度 0-1

## 版本历史
changelog:
  - version: "1.2.0"
    date: "2025-01-01"
    changes: "新增向量搜索工具，提升本地知识库检索"
  - version: "1.1.0"
    date: "2024-12-01"
    changes: "切换Tavily搜索，提升结果质量"
  - version: "1.0.0"
    date: "2024-11-01"
    changes: "初始版本"
---
```

### soul.md 规范（人格配置）

```markdown
---
# ========================================
# soul.md - Agent人格与行为准则
# 每个Agent必须有独立soul.md
# ========================================

agent_id: search_agent
persona_name: "探索者·小搜"

## 核心人格
personality:
  tone: professional_friendly    # professional/casual/friendly/formal
  language_style: concise        # concise/detailed/conversational
  emoji_usage: moderate          # none/minimal/moderate/rich
  response_format: structured    # structured/prose/mixed

## 系统提示词（基础人格）
system_prompt: |
  你是WorkBot的搜索助理，代号"小搜"。
  
  你的核心职责：
  - 高效准确地搜索并整理信息
  - 区分事实与观点，标注信息来源
  - 当信息不足时，主动说明局限性
  
  你的行为准则：
  1. 永远先验证信息的可靠性再输出
  2. 对于时效性强的信息，注明检索时间
  3. 不捏造信息，不确定时直接说"我不确定"
  4. 结果尽量结构化，方便阅读

## 边界规则（不可违背）
boundaries:
  - 不搜索涉及个人隐私的信息
  - 不搜索违法违规内容
  - 不输出未经验证的医疗建议
  - 遇到敏感话题立即转交安全Agent

## 与其他Agent协作时的行为
collaboration:
  when_receiving_task: "收到任务后先确认查询意图是否清晰，不清晰则返回澄清请求"
  when_done: "输出标准化结果JSON，附带置信度分数"
  when_failed: "向Master Bot上报失败原因，建议备选方案"

## 多语言支持
language:
  default: zh-CN
  fallback: en
  auto_detect: true
---
```

### 版本化热重载实现

```python
# agents/config_loader.py
import yaml, hashlib
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AgentConfigLoader:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.configs = {}    # {agent_id: {version, agents_config, soul_config, hash}}
        self._load_all()
        self._watch()        # 监听文件变化，自动热重载

    def _load_all(self):
        for agent_dir in self.config_dir.iterdir():
            if agent_dir.is_dir():
                self._load_agent(agent_dir.name)

    def _load_agent(self, agent_id: str):
        agents_file = self.config_dir / agent_id / "agents.md"
        soul_file = self.config_dir / agent_id / "soul.md"
        
        if not agents_file.exists():
            return

        content = agents_file.read_text()
        current_hash = hashlib.md5(content.encode()).hexdigest()
        
        # 只有内容变化才重载
        if self.configs.get(agent_id, {}).get('hash') == current_hash:
            return

        # 解析YAML front matter
        agents_config = self._parse_md(agents_file)
        soul_config = self._parse_md(soul_file) if soul_file.exists() else {}
        
        self.configs[agent_id] = {
            "hash": current_hash,
            "version": agents_config.get("version", "0.0.1"),
            "agents": agents_config,
            "soul": soul_config,
            "loaded_at": datetime.now()
        }
        print(f"✅ Agent [{agent_id}] 配置已加载 v{agents_config.get('version')}")

    def _watch(self):
        """监听配置目录文件变化，自动热重载"""
        class Handler(FileSystemEventHandler):
            def on_modified(self_h, event):
                if event.src_path.endswith('.md'):
                    agent_id = Path(event.src_path).parent.name
                    self._load_agent(agent_id)
                    
        observer = Observer()
        observer.schedule(Handler(), str(self.config_dir), recursive=True)
        observer.start()
```

---

## 11. 快速落地方案 (Codex + GPT多Agent并行开发)

### 用AI加速开发的核心策略

**原则：每个 Codex/GPT Agent 只负责一个模块，任务边界清晰，互不干扰。**

### AI Agent 分工表

| Agent编号 | 负责模块 | 具体任务 | 工作目录 |
|---------|---------|---------|---------|
| Agent-1 | 平台接入层 | 实现4个平台的Adapter + 统一消息对象 | `app/adapters/` |
| Agent-2 | 数据库层 | SQLAlchemy模型 + Alembic迁移 + CRUD工具函数 | `app/models/` |
| Agent-3 | 安全模块 | 加密工具 + JWT认证 + RBAC + 过滤器 | `app/security/` |
| Agent-4 | Master Bot | 意图识别 + 路由 + NATS集成 + 结果聚合 | `app/core/` |
| Agent-5 | 工作Agent实现 | 搜索/写作/代码3个Agent的完整实现 | `app/agents/` |
| Agent-6 | 工作流引擎 | 节点执行 + 拓扑排序 + Prefect集成 | `app/workflow/` |
| Agent-7 | API层 | FastAPI路由 + 中间件 + WebSocket | `app/api/` |
| Agent-8 | 前端-工作流编辑器 | ReactFlow画布 + 自定义节点 | `frontend/workflow/` |
| Agent-9 | 前端-Dashboard | 任务看板 + Agent状态 + 实时日志 | `frontend/dashboard/` |
| Agent-10 | DevOps | Docker Compose + Nginx + 环境配置 | 根目录 |

### 给每个AI Agent的Prompt模板

```
你是 [模块名] 的专业开发工程师。
项目名称：WorkBot - 企业级多Agent工作机器人

你的任务范围仅限于：[具体模块]
你需要实现的功能：
1. [具体功能1]
2. [具体功能2]

技术约束：
- 语言：Python 3.11 / TypeScript
- 框架：FastAPI / React 18
- 编码规范：PEP8 / ESLint + Prettier
- 所有函数必须有类型注解
- 所有公开函数必须有docstring

接口契约（你需要遵守的输入/输出格式）：
[粘贴相关的Schema或接口定义]

请直接输出可运行的代码，包含完整的文件路径注释。
```

### MVP 最小可用版本 (2周冲刺计划)

```
第1周 (后端骨架)
├── Day 1-2: 环境搭建 + Docker Compose（NATS + Redis + PostgreSQL）
├── Day 3:   数据库模型 + 迁移（Agent-2 负责）
├── Day 4:   安全模块基础（Agent-3 负责）
└── Day 5-7: Master Bot + Telegram接入 + 2个Agent（Agent-1,4,5 负责）

第2周 (前端 + 联调)
├── Day 8-9:  FastAPI路由层 + WebSocket（Agent-7 负责）
├── Day 10-11: 前端Dashboard基础版（Agent-9 负责）
├── Day 12-13: 工作流编辑器基础版（Agent-8 负责）
└── Day 14:   端到端联调 + Bug修复
```

### 开发环境一键启动

```yaml
# docker-compose.yml
version: "3.9"

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: workbot
      POSTGRES_USER: workbot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "6379:6379"

  nats:
    image: nats:2.10-alpine
    command: --jetstream --store_dir /data
    volumes:
      - nats_data:/data
    ports:
      - "4222:4222"
      - "8222:8222"    # 监控面板

  chromadb:
    image: chromadb/chroma:latest
    volumes:
      - chroma_data:/chroma/chroma
    ports:
      - "8000:8000"

  backend:
    build: .
    environment:
      DATABASE_URL: postgresql://workbot:${DB_PASSWORD}@postgres/workbot
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379
      NATS_URL: nats://nats:4222
      CHROMA_URL: http://chromadb:8000
      WORKBOT_MASTER_KEY: ${WORKBOT_MASTER_KEY}
    depends_on: [postgres, redis, nats, chromadb]
    ports:
      - "8080:8080"
    volumes:
      - ./agents_config:/app/agents_config  # Agent配置热重载

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on: [backend]

volumes:
  postgres_data:
  nats_data:
  chroma_data:
```

### 生成 MASTER_KEY 命令

```bash
# 生成主加密密钥
python -c "import os,base64; print('WORKBOT_MASTER_KEY=' + base64.b64encode(os.urandom(32)).decode())" >> .env

# 启动全部服务
docker-compose up -d

# 查看NATS监控
open http://localhost:8222
```

---

## 12. MVP开发检查清单

### 后端检查清单

- [ ] FastAPI 项目初始化，健康检查接口 `/health`
- [ ] PostgreSQL 连接 + 所有表迁移成功
- [ ] Redis 连接 + Session存储测试通过
- [ ] NATS 连接 + 基本Pub/Sub测试
- [ ] ChromaDB 连接 + 向量插入/检索测试
- [ ] Telegram Webhook 接入，能收发消息
- [ ] 统一消息对象 `UnifiedMessage` 定义完成
- [ ] 安全过滤器：屏蔽关键词 + Prompt注入检测
- [ ] 用户自动创建（首次消息时）+ 加密存储
- [ ] Master Bot 能识别至少3种意图（search/write/help）
- [ ] 搜索Agent完整运行
- [ ] 写作Agent完整运行
- [ ] 任务状态能正确更新（pending→running→done）
- [ ] JWT认证 + 管理员登录接口
- [ ] 审计日志写入

### 前端检查清单

- [ ] React 项目初始化，路由配置
- [ ] 管理员登录页面
- [ ] Dashboard 概览页（任务计数 + Agent状态）
- [ ] 任务列表页（支持状态过滤）
- [ ] 任务详情页（显示子步骤时间线）
- [ ] WebSocket 实时消息接收
- [ ] 工作流编辑器：能添加节点和连线
- [ ] 工作流编辑器：保存/加载工作流
- [ ] Agent 列表页（显示状态 + 配置预览）
- [ ] 审计日志页（支持搜索和分页）

### 安全检查清单

- [ ] `.env` 文件加入 `.gitignore`，绝不提交密钥
- [ ] 所有用户数据入库前都经过 `EncryptionService.encrypt()`
- [ ] API 接口全部有认证中间件保护（除Webhook验证）
- [ ] Webhook接口有签名验证（平台签名校验）
- [ ] 有全局限流（每用户每分钟最多N条消息）
- [ ] 敏感信息（密钥、密码）不出现在日志中

---

## 附录：推荐学习资源

| 模块 | 资源 |
|------|------|
| LangGraph | https://langchain-ai.github.io/langgraph/ |
| NATS官方文档 | https://docs.nats.io/ |
| ReactFlow | https://reactflow.dev/docs |
| FastAPI | https://fastapi.tiangolo.com/ |
| ChromaDB | https://docs.trychroma.com/ |
| Prefect | https://docs.prefect.io/ |
| cryptography库 | https://cryptography.io/en/latest/ |

---

*文档版本: v1.0 | 最后更新: 2025年 | 作者: WorkBot开发团队*
