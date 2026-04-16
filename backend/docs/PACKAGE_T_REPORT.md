# Package T Report

- generated_at: 2026-04-13T19:06:06.268056+00:00
- load_report: docs/package_t_load_smoke2_20260413_190524.json
- fault_report: docs/package_t_faults_smoke_20260413_185941.json

## Load Benchmark 1

```json
{
  "scenario": "concurrent_messages",
  "total_requests": 6,
  "concurrency": 2,
  "summary": {
    "requests": 6,
    "success_count": 6,
    "failure_count": 0,
    "success_rate": 100.0,
    "latency": {
      "avg_ms": 58.43,
      "min_ms": 16.66,
      "max_ms": 106.4,
      "p95_ms": 70.61,
      "p99_ms": 70.61
    },
    "errors": {}
  }
}
```

## Load Benchmark 2

```json
{
  "scenario": "timeout_retry",
  "total_requests": 6,
  "concurrency": 2,
  "forced_timeout_ms": 80.0,
  "retries": 1,
  "summary": {
    "requests": 6,
    "success_count": 6,
    "failure_count": 0,
    "success_rate": 100.0,
    "latency": {
      "avg_ms": 38.03,
      "min_ms": 36.19,
      "max_ms": 39.85,
      "p95_ms": 39.15,
      "p99_ms": 39.15
    },
    "errors": {}
  }
}
```

## Fault Drill 1

```json
{
  "scenario": "external_offline",
  "status_code": 200,
  "summary": {
    "agents": 1,
    "skills": 1,
    "routable": 0,
    "open_circuits": 0,
    "offline": 2
  },
  "counts": {}
}
```

## Fault Drill 2

```json
{
  "scenario": "nats_block",
  "publish_ok": false,
  "failure": "simulated_nats_block",
  "expected_degradation": "fallback_to_in_process_bus",
  "captured_local_events": 0
}
```

## Fault Drill 3

```json
{
  "scenario": "database_slow_query",
  "delay_seconds": 0.02,
  "status_code": 200,
  "latency_ms": 34.99,
  "health_status": "critical"
}
```

## Fault Drill 4

```json
{
  "scenario": "security_high_pressure",
  "total_requests": 8,
  "allowed": 5,
  "blocked_429": 3,
  "degradation_expected": true
}
```
