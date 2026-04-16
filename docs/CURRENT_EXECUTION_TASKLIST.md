# Current Execution Tasklist

更新时间：2026-04-15

## 目标

- 优先把 `XXL` 主脑推进到正式联调可上线状态
- 同时补齐 `XXL_ExternalConnection` 的独立部署骨架
- 不在当前阶段继续分散到低优先级的新能力扩展

## 优先级结论

- 第一优先：`XXL`
- 第二优先：`XXL_ExternalConnection` 的部署独立化
- 第三优先：外接 Agent 远程执行协议统一化

## P0：XXL 主脑严格 blocker 清零

- [ ] 接入正式 PostgreSQL 真源，消除 `persistent_truth_source_ready`
- [ ] 接入正式 NATS，消除 `nats_transport_ready`
- [ ] 在真实数据库下完成 dispatcher / workflow worker / agent worker 多实例联调
- [ ] 让 `check_scheduler_runtime_pg_acceptance.py` 在正式 DSN 下实跑通过
- [ ] 让 `check_nats_roundtrip.py` 在正式 NATS 下实跑通过
- [ ] 让 `check_brain_prelaunch.py --strict-production` 不再输出 `degraded_startable`

验收标准：

- `strict_failed_keys` 为空
- `production_ready=true`

## P1：XXL_ExternalConnection 独立部署骨架

- [x] 新建 `XXL_ExternalConnection/docker-compose.yml`
- [x] 新建 `XXL_ExternalConnection/.env.example`
- [x] 新建 `XXL_ExternalConnection/README.md`
- [x] 新建 `XXL_ExternalConnection/run-external.sh`
- [x] 明确每个 MCP / Agent / Skill 的端口、健康检查、重启策略
- [x] 明确主脑侧需要配置的 `base_url`、注册地址
- [x] 验证“外接仓单独启动”与“主脑仓远程接入”两种模式

验收标准：

- `XXL_ExternalConnection` 可单独拉起
- `XXL` 不依赖本地相对目录也能连接外接服务

已完成补充：

- 根仓已删除旧的一体化启动脚本 `run-compose.sh` / `run-dev.sh` / `run-full.sh`
- 根仓新增 `run-brain.sh`，只负责主脑 compose
- 外接仓新增 `run-external.sh`，只负责 MCP 触手 compose
- 主脑 compose 已改成 brain-only，不再直接 build 外接仓代码
- 触手签名密钥暂未新增部署参数，仍作为后续安全中心增强项

## P2：外接 Agent 远程执行主链统一

- [ ] 明确 external agent 标准执行端点协议：`/execute` 请求体、回包、错误结构
- [ ] 把 external agent 从“注册/心跳/治理优先”推进到“可统一远程执行”
- [ ] 为 external agent 增加与 MCP/Skill 同级的 runtime invoke bridge
- [ ] 明确 external agent 的超时、重试、熔断、回滚切换策略
- [ ] 补齐 external agent 执行链路回归测试

验收标准：

- 外接 Agent 与外接 Skill / MCP 一样，具备一致的远程执行入口与治理行为

## P3：文档整理

- [x] 新建 `docs/CURRENT_EXECUTION_TASKLIST.md`
- [x] 新建 `docs/README.md`
- [x] 将主脑文档整理到 `docs/brain/`
- [x] 将阶段清单整理到 `docs/stages/`
- [x] 将完成报告 `final_acceptance_report.md` 归拢到 `docs/reports/`
- [x] 同步修正 `dr_common.py`、`check_todo_sync.py` 与相关测试路径
- [ ] 继续识别“完成报告类文档”并归拢到 `docs/`
- [ ] 继续识别适合进入 `docs/brain/`、`docs/stages/`、`docs/reports/` 的整理文档

## 暂不优先

- [ ] 外接新能力扩展
- [ ] 新一轮 UI / 控制面扩展
- [ ] 非 blocker 级技术债清理

说明：

- 当前阶段不是“继续扩功能”，而是“主脑上线收口 + 外接仓部署独立化”。
