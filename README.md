# WorkBot MVP

当前仓库已经从“开发指南 + 前端原型”整理为一个可继续开发的 MVP 骨架：

- `backend/`: FastAPI 后端，提供 Dashboard、Tasks、Agents、Users、Workflows、Security、Auth 等示例接口
- `样式文件/`: Next.js 前端，沿用现有原型页面并接入真实 API hooks

## 目录

```text
.
├── backend/
├── 样式文件/
├── WorkBot_开发全指南.md
├── 开发指南补充.md
├── security_gateway_pipeline.svg
└── memory_distillation_lifecycle.svg
```

## 后端启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

可用接口示例：

- `GET http://127.0.0.1:8080/health`
- `GET http://127.0.0.1:8080/api/dashboard/stats`
- `GET http://127.0.0.1:8080/api/tasks`
- `GET http://127.0.0.1:8080/api/agents`
- `GET http://127.0.0.1:8080/api/users`
- `GET http://127.0.0.1:8080/api/workflows`
- `GET http://127.0.0.1:8080/api/security/rules`

默认演示登录账号：

- `email`: `admin@workbot.ai`
- `password`: `workbot123`

数据库迁移：

```bash
cd backend
alembic upgrade head
alembic downgrade -1
```

- Alembic 配置在 `backend/alembic.ini`
- 默认会读取 `WORKBOT_DATABASE_URL`

## Docker Compose 开发环境

仓库根目录已经补齐 `docker-compose.yml`，可一次拉起：

- `frontend` (Next.js)
- `backend` (FastAPI + Uvicorn reload)
- `postgres`
- `redis`
- `nats`
- `chromadb`

启动方式：

```bash
cp .env.example .env
docker compose up --build
```

默认端口：

- 前端: `http://127.0.0.1:3000`
- 后端: `http://127.0.0.1:8080`
- PostgreSQL: `127.0.0.1:5432`
- Redis: `127.0.0.1:6379`
- NATS: `127.0.0.1:4222`
- NATS Monitor: `http://127.0.0.1:8222`
- ChromaDB: `http://127.0.0.1:8000`

说明：

- 根目录 `.env.example` 用于 Docker Compose 变量替换。
- `backend/.env.example` 对应 FastAPI 的 `WORKBOT_` 配置项。
- 当前项目已接入部分真实基础设施：核心运行状态可持久化到 PostgreSQL，任务 / 用户 / 安全规则等高频查询已切到数据库优先读取，安全网关限流与短期记忆优先走 Redis，mid-term session summary 已接入 SQLite，long-term memory 已接入 ChromaDB，workflow realtime 与 workflow tick dispatch 已接入 NATS 基础链路并保留本地回退，服务重启后也会重新调度非终态 workflow run。
- 当前仍未完成的基础设施主链路集中在更完整的 Dispatcher / Worker 异步调度，以及把现有 NATS 基础层扩展到正式任务分发、持久化队列和多实例独占协同。
- 可通过 `WORKBOT_MEMORY_SESSION_IDLE_SECONDS` 调整短期记忆会话空闲阈值；超过该阈值后，旧会话会自动蒸馏到 mid-term / long-term，并在后续新任务中参与记忆注入。
- 如果要启用 Telegram 出站回传，需要在后端环境中配置 `WORKBOT_TELEGRAM_BOT_TOKEN`；未配置时，Telegram 入站仍可正常创建任务，但结果回传会自动跳过并保留任务完成态。
- 如果要启用 Telegram webhook secret 校验，可额外配置 `WORKBOT_TELEGRAM_WEBHOOK_SECRET`，后端会校验 `X-Telegram-Bot-Api-Secret-Token` 请求头。

常用命令：

```bash
docker compose up -d postgres redis nats chromadb
docker compose up --build backend frontend
docker compose down
```

## 一键本地开发

仓库根目录提供了 `./run-dev.sh`，会优先尝试自动拉起 `postgres / redis / nats / chromadb`，然后启动后端和前端。

```bash
./run-dev.sh
```

行为说明：

- 脚本会优先使用仓库根目录 `.venv`，如果你已经按旧方式创建了 `backend/.venv` 也可以直接复用
- Docker 可用时：自动启动基础设施，再启动前后端
- Docker 不可用或未启动时：自动退回 SQLite 本地预览模式，并尽量降级 Redis / NATS / Chroma 依赖
- fallback 预览模式适合看页面和走单机主流程，不等价于完整的多实例 / 实时 / 长期记忆基础设施环境
- 前端访问入口：`http://127.0.0.1:3000`
- 登录页：`http://127.0.0.1:3000/login`
- 演示账号：`admin@workbot.ai / workbot123`

## 前端启动

```bash
cd 样式文件
cp .env.example .env.local
npm install
npm run dev
```

默认会连接：

- 前端: `http://127.0.0.1:3000`
- 后端: `http://127.0.0.1:8080`

## 当前已接通的页面

- Dashboard
- Agent 协作可视化
- 任务管理
- 任务详情页
- Agent 管理
- 用户管理
- 用户画像详情页
- 安全中心
- 工作流编辑器

## 当前仍是示例实现的部分

- Agent 启停和配置编辑
- 登录页 UI
- Dispatcher / Worker 多进程调度与多实例独占恢复
- 更多平台 Adapter 扩展
