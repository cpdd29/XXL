# 监控接入模板

更新时间：2026-04-16

## 1. 本地模板资产

仓库内已提供：

- `deploy/monitoring/docker-compose.monitoring.yml`
- `deploy/monitoring/prometheus/prometheus.yml.tpl`
- `deploy/monitoring/grafana/provisioning/`
- `deploy/monitoring/grafana/dashboards/brain-runtime-overview.json`
- `run-monitoring-stack.sh`
- `backend/scripts/collect_monitoring_alerting_evidence.py`

## 2. Prometheus 抓取

主脑 `/api/dashboard/metrics` 现在支持：

- 正常控制面 Bearer Token
- `WORKBOT_METRICS_SCRAPE_TOKEN`

模板中的 Prometheus 默认使用 `WORKBOT_METRICS_SCRAPE_TOKEN`：

```yaml
scrape_configs:
  - job_name: "workbot-brain-dashboard"
    metrics_path: /api/dashboard/metrics
    authorization:
      type: Bearer
      credentials: "__WORKBOT_METRICS_SCRAPE_TOKEN__"
    static_configs:
      - targets:
          - backend:8080
```

启动方式：

```bash
export WORKBOT_METRICS_SCRAPE_TOKEN=change-me
./run-monitoring-stack.sh
```

## 3. Grafana 看板接入清单

- [ ] Prometheus 数据源已配置并可查询
- [ ] 已导入 `Brain Runtime Overview` 看板
- [ ] `queue depth / dead letters / sla health / alerts` 面板可见
- [ ] 看板访问权限已分配给值班与研发团队

## 4. 企业通知渠道变量清单

- `ALERT_CHANNEL_TYPE`
- `ALERT_WEBHOOK_URL`
- `ALERT_WEBHOOK_SECRET`
- `ALERT_AT_USERS`
- `ALERT_AT_ALL`
- `ALERT_TITLE_PREFIX`

这些变量不应落仓，真实值应来自密钥管理或部署平台。

## 5. 证据采集

```bash
python3 backend/scripts/collect_monitoring_alerting_evidence.py \
  --backend-base-url http://127.0.0.1:8080 \
  --metrics-token "$WORKBOT_METRICS_SCRAPE_TOKEN" \
  --email admin@workbot.ai \
  --password workbot123 \
  --strict
```

脚本会输出：

- `backend/docs/monitoring_alerting_evidence_*.json`
- `backend/docs/monitoring_alerting_evidence_*.md`

## 6. 当前边界

- 仓库内监控接入模板、Prometheus/Grafana compose 和证据采集脚本已补齐
- 真实 Prometheus / Grafana / 企业通知通道接入、值班升级链和上线演练留痕，仍需在真实环境执行
