global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "workbot-brain-dashboard"
    scheme: http
    metrics_path: /api/dashboard/metrics
    authorization:
      type: Bearer
      credentials: "__WORKBOT_METRICS_SCRAPE_TOKEN__"
    static_configs:
      - targets:
          - backend:8080
        labels:
          service: workbot-brain
          layer: brain
