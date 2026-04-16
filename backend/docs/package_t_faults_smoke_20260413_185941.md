# Package T Fault Drill

## external_offline

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

## nats_block

```json
{
  "scenario": "nats_block",
  "publish_ok": false,
  "failure": "simulated_nats_block",
  "expected_degradation": "fallback_to_in_process_bus",
  "captured_local_events": 0
}
```

## database_slow_query

```json
{
  "scenario": "database_slow_query",
  "delay_seconds": 0.02,
  "status_code": 200,
  "latency_ms": 34.99,
  "health_status": "critical"
}
```

## security_high_pressure

```json
{
  "scenario": "security_high_pressure",
  "total_requests": 8,
  "allowed": 5,
  "blocked_429": 3,
  "degradation_expected": true
}
```
