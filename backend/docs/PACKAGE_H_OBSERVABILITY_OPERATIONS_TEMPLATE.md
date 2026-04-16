# Package H Observability / Alert Ops Template

更新时间：2026-04-16

## 1. Prometheus / Grafana 接入模板

### 1.1 Prometheus 抓取配置

仓库内模板文件：

- `deploy/monitoring/prometheus/prometheus.yml.tpl`

核心抓取口径：

```yaml
scrape_configs:
  - job_name: "brain-dashboard-metrics"
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /api/dashboard/metrics
    scheme: http
    authorization:
      type: Bearer
      credentials: "__WORKBOT_METRICS_SCRAPE_TOKEN__"
    static_configs:
      - targets:
          - "backend:8080"
        labels:
          env: prod
          service: workbot-brain
```

辅助启动脚本：

```bash
export WORKBOT_METRICS_SCRAPE_TOKEN=change-me
./run-monitoring-stack.sh
```

### 1.2 Grafana 看板接入清单

- [ ] 新增数据源：`Prometheus`（UID：`workbot-prom`）
- [ ] 导入看板：`Brain Runtime Overview`（UID：`brain-runtime-overview`）
- [ ] 最低面板：`queue_depth_total`、`dead_letter_total`、`sla_success_rate`、`prepared_alerts_total`
- [ ] 配置看板访问权限

### 1.3 抓取验收命令

```bash
curl -fsS -H "X-WorkBot-Metrics-Token: ${WORKBOT_METRICS_SCRAPE_TOKEN}" \
  "http://${BRAIN_API_HOST}:${BRAIN_API_PORT}/api/dashboard/metrics" | head -n 20
curl -fsS "http://${PROM_HOST}:${PROM_PORT}/api/v1/targets" | jq '.data.activeTargets[] | select(.labels.job==\"brain-dashboard-metrics\") | {health,lastError,lastScrape}'
```

监控证据采集：

```bash
python3 backend/scripts/collect_monitoring_alerting_evidence.py \
  --backend-base-url "http://${BRAIN_API_HOST}:${BRAIN_API_PORT}" \
  --metrics-token "${WORKBOT_METRICS_SCRAPE_TOKEN}" \
  --access-token "<operator_token>" \
  --strict
```

## 2. 企业通知渠道配置清单（模板）

| channel | enabled | webhook/api endpoint | secret/token source | target(chat_id/user) | network allowlist | test message evidence |
|---|---|---|---|---|---|---|
| dingtalk | false | `https://oapi.dingtalk.com/...` | `secret://ops/dingtalk-bot` | `chat:xxxx` | `egress-open` | `docs/evidence/h/dingtalk-test.md` |
| wecom | false | `https://qyapi.weixin.qq.com/...` | `secret://ops/wecom-bot` | `group:xxxx` | `egress-open` | `docs/evidence/h/wecom-test.md` |
| feishu | false | `https://open.feishu.cn/...` | `secret://ops/feishu-bot` | `chat:xxxx` | `egress-open` | `docs/evidence/h/feishu-test.md` |
| telegram | false | `https://api.telegram.org/...` | `secret://ops/telegram-bot` | `chat_id:xxxx` | `egress-open` | `docs/evidence/h/telegram-test.md` |

执行要求：

- [ ] 至少 1 条 P1 通道 + 1 条 P2 通道可用
- [ ] 凭证只从密钥管理读取，不落盘到仓库
- [ ] 每条通道有一条“发送成功 + 接收截图”证据

## 3. 值班升级链 / 抑制窗口 / 演练证据模板

### 3.1 值班升级链模板

| severity | T+0 | T+5min | T+15min | T+30min |
|---|---|---|---|---|
| P1 | 当班 SRE | 值班 TL | 平台负责人 | 技术负责人 |
| P2 | 当班 SRE | 值班 TL | 平台负责人 | - |
| P3 | 当班工程师 | 值班 SRE | - | - |

要求：

- [ ] 每个级别有明确责任人
- [ ] 升级超时自动转下一级

### 3.2 告警抑制窗口模板

| window_name | scope | rule | start/end | approver | rollback_rule |
|---|---|---|---|---|---|
| release-freeze-1 | `env=prod` | suppress `P3` only | `2026-04-20 20:00~22:00` | `ops_manager` | 发布结束立即恢复 |
| db-maintenance | `service=db` | suppress `known_maintenance` | `YYYY-MM-DD HH:mm~HH:mm` | `dba_owner` | 维护失败立即取消抑制 |

红线：

- [ ] 不允许抑制 `P1`
- [ ] 抑制规则必须有开始、结束、审批人、回滚条件

### 3.3 演练证据模板

| drill_id | inject_time | expected_alert | actual_alert_time | notify_channel | ack_time | resolve_time | closed_loop | evidence_link |
|---|---|---|---|---|---|---|---|---|
| `H-DRILL-001` | `YYYY-MM-DD HH:mm:ss` | `queue_depth_high(P1)` | `YYYY-MM-DD HH:mm:ss` | `dingtalk+pager` | `+3m` | `+14m` | true | `backend/docs/evidence/h/H-DRILL-001.md` |

验收阈值：

- [ ] 告警触发延迟 <= 60s
- [ ] P1 首次触达 <= 180s
- [ ] 每条演练记录含“注入命令、告警截图、通知截图、关闭记录”

## 4. Package H 落地判定

- `模板化完成`：本文档已填入真实环境值并完成评审
- `仓库内交付完成`：compose、Grafana provisioning、metrics token 抓取口径、证据采集脚本已落仓
- `生产执行完成`：Prometheus/Grafana 已接通 + 至少一条企业通知通道真实可达 + 已留存至少一轮演练证据
