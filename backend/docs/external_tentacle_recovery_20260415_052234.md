# External Tentacle Recovery

## External Recovery Comparison

```json
{
  "ok": true,
  "checks": [
    {
      "key": "registry_inventory_loaded",
      "ok": true,
      "details": {
        "baseline_instance_total": 0,
        "current_instance_total": 0,
        "agent_families": 0,
        "skill_families": 0,
        "agent_instances": 0,
        "skill_instances": 0,
        "routable_instances": 0,
        "offline_instances": 0,
        "open_circuits": 0,
        "stale_heartbeats": 0
      }
    },
    {
      "key": "family_recovered",
      "ok": true,
      "details": {
        "missing_agent_families": [],
        "missing_skill_families": []
      }
    },
    {
      "key": "stale_heartbeats_cleared",
      "ok": true,
      "details": {
        "stale_items": []
      }
    },
    {
      "key": "open_circuits_cleared",
      "ok": true,
      "details": {
        "open_circuits": 0
      }
    }
  ],
  "failed_steps": [],
  "missing_agent_families": [],
  "missing_skill_families": []
}
```

## Current External Manifest

```json
{
  "captured_at": "2026-04-15T05:22:34+00:00",
  "summary": {
    "agent_families": 0,
    "skill_families": 0,
    "agent_instances": 0,
    "skill_instances": 0,
    "routable_instances": 0,
    "offline_instances": 0,
    "open_circuits": 0,
    "stale_heartbeats": 0
  },
  "stale_items": [],
  "agents": [],
  "skills": []
}
```

## Result

```json
{
  "status": "passed",
  "failed_steps": [],
  "measurements": {
    "rto_seconds": null,
    "external_recovery_rto_seconds": 60.0,
    "estimated_rpo_seconds": null,
    "estimated_lost_records": 0
  }
}
```
