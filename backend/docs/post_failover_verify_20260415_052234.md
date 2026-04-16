# Post Failover Verify

## Truth Comparison

```json
{
  "ok": true,
  "checks": [
    {
      "key": "task_truth_continuity",
      "ok": true,
      "details": {
        "baseline_total": 6,
        "current_total": 6,
        "missing_task_ids": []
      }
    },
    {
      "key": "run_truth_continuity",
      "ok": true,
      "details": {
        "baseline_total": 0,
        "current_total": 0,
        "missing_run_ids": []
      }
    },
    {
      "key": "audit_truth_continuity",
      "ok": true,
      "details": {
        "baseline_total": 7,
        "current_total": 7,
        "missing_audit_ids": []
      }
    },
    {
      "key": "security_truth_continuity",
      "ok": true,
      "details": {
        "baseline_rules": 7,
        "current_rules": 7,
        "missing_incident_ids": []
      }
    }
  ],
  "failed_steps": [],
  "estimated_rpo_seconds": 0.0,
  "estimated_lost_records": 0
}
```

## Current Truth Sources

```json
{
  "captured_at": "2026-04-15T05:22:34+00:00",
  "scope": {
    "tenant_id": "default",
    "project_id": "default",
    "environment": "docker-compose"
  },
  "tasks": {
    "total": 6,
    "by_status": {
      "completed": 2,
      "running": 1,
      "pending": 1,
      "failed": 1,
      "cancelled": 1
    },
    "sample_ids": [
      "1",
      "2",
      "3",
      "4",
      "5",
      "6"
    ],
    "latest_created_at": "2024-01-15T10:33:00+00:00"
  },
  "runs": {
    "total": 0,
    "by_status": {},
    "sample_ids": [],
    "latest_updated_at": null
  },
  "audit": {
    "total": 7,
    "by_status": {
      "warning": 2,
      "success": 3,
      "error": 2
    },
    "sample_ids": [
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7"
    ],
    "latest_timestamp": "2024-01-15T10:32:15+00:00"
  },
  "security": {
    "summary": {
      "total_events": 7,
      "blocked_threats": 2,
      "alert_notifications": 2,
      "active_rules": 7,
      "unique_users": 6,
      "rewrite_events": 0,
      "high_risk_events": 2
    },
    "active_penalties": 0,
    "rule_total": 7,
    "recent_incident_ids": [
      "1",
      "4",
      "6",
      "7"
    ],
    "latest_incident_at": "2024-01-15T10:32:15+00:00"
  }
}
```

## Readiness

```json
{
  "captured_at": "2026-04-15T05:22:34+00:00",
  "environment": "docker-compose",
  "persistence_enabled": false,
  "nats_connected": false,
  "fallback_event_bus_available": true,
  "runbook_exists": true,
  "result_template_exists": true,
  "warnings": [
    "当前未连接正式持久层，真源校验将基于内存/降级模式。",
    "NATS 当前未建立连接，将以 in-process fallback 视为可降级运行。"
  ]
}
```

## Result

```json
{
  "status": "passed",
  "failed_steps": [],
  "measurements": {
    "rto_seconds": 60.0,
    "external_recovery_rto_seconds": null,
    "estimated_rpo_seconds": 0.0,
    "estimated_lost_records": 0
  }
}
```
