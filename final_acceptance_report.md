# WorkBot 八爪鱼改造最终验收报告

更新时间：2026-04-11

## 1. 最终结论

- 已完成“大脑封闭、触手外置、协议统一”的主线改造。
- 主仓默认运行形态已收敛到 `external_only`。
- 主仓内不再保留任何重执行 builtin fallback。
- 主仓当前仅保留两个只读轻能力：
  - `task_status_skill`
  - `task_list_skill`

## 2. 当前架构状态

大脑保留：

- 唯一消息入口 Agent（接待 + 项目经理）
- 路由、编排、审计、回传
- 任务状态与任务列表查询视图

外接能力：

- `weather_skill` -> `weather-mcp`
- `web_search_skill` -> `search-mcp`
- `pdf_read_skill` -> `pdf-mcp`
- `pdf_summary_skill` -> `pdf-mcp`
- `speech_writer_skill` -> `writer-mcp`
- `general_writer_skill` -> `writer-mcp`
- `order-query-mcp`
- `crm-query-mcp`
- 外接 `agent`
- 外接 `skill`
- 外接 `mcp`

统一协议：

- 主链统一走 tool source registry + MCP/runtime bridge
- `external_only / hybrid / local_only` 模式已打通
- `local-agents` / `local-mcp-services` 已降级为 `legacy/manual fallback`

## 3. 已完成的关键治理

- `external_only` 下，重执行能力必须走 external runtime。
- 新增 builtin `*_skill` 会触发架构检查失败。
- 自由工作流默认不会把 legacy fallback source 当作 runtime 主路径。
- 工具页已显式展示治理状态、运行模式和 legacy fallback 标识。
- 示例 registry、部署文档、桥接文档已同步到 `agent + skill + mcp` 全外接模型。

## 4. 代码层最终判断

主仓内仍允许存在：

- 路由与编排逻辑
- 只读查询型轻能力
- runtime 适配、治理、回滚与观测

主仓内已移除或不再允许：

- 搜索 builtin fallback
- 天气 builtin fallback
- PDF builtin fallback
- 写作 builtin fallback
- 新增重执行 builtin skill

## 5. 验收结果

已通过的关键验收：

- `pytest -q backend/tests/test_free_workflow.py backend/tests/test_architecture_boundaries.py`
- `pytest -q backend/tests/test_tool_source_service.py backend/tests/test_tool_catalog.py backend/tests/test_tools_catalog.py`
- `pytest -q backend/tests/test_mcp_runtime.py backend/tests/test_agents_runtime.py`
- `python3 backend/scripts/check_architecture_boundaries.py --root backend`
- `python3 -m py_compile` 关键服务文件
- `docker compose -f docker-compose.yml config --services`
- `bash -n run-dev.sh`
- `cd 样式文件 && npx tsc --noEmit`

## 6. 剩余风险

- `local-agents` / `local-mcp-services` 仍保留为兼容与应急兜底入口，虽然不再是默认主链。
- 若外部 runtime 不可用，重执行能力会明确失败，不再回落到主仓执行；这符合目标，但要求外部触手部署必须稳定。
- 前后端文档已基本同步，但未来如果新增外接能力，需要同步更新 external registry 与验收清单。

## 7. 后续建议

- 若进入下一阶段，可把 `local-agents` / `local-mcp-services` 进一步收敛成纯运维级开关，不再作为常规产品能力展示。
- 可增加一份运维演练手册，专门覆盖 external runtime 故障、切换 `hybrid`、恢复 `external_only` 的流程。
