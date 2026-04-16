# Release Preflight

## Status

```json
{
  "ok": true,
  "status": null,
  "generated_at": "2026-04-15T19:44:18+00:00"
}
```

## Payload

```json
{
  "ok": true,
  "checks": {
    "alembic_chain": {
      "ok": true,
      "summary": {
        "total_revisions": 15,
        "heads": [
          "20260415_0015"
        ],
        "roots": [
          "20260403_0001"
        ],
        "missing_down_revisions": []
      }
    },
    "compose_guards": {
      "ok": true,
      "summary": {
        "missing_services": [],
        "healthcheck_gaps": [],
        "backend_has_depends_on": true,
        "leaked_external_services": [],
        "backend_has_external_registry_mount": true,
        "backend_has_external_registry_env": true,
        "backend_has_host_gateway": true,
        "backend_runs_migrations": true
      }
    },
    "production_env_template": {
      "ok": true,
      "summary": {
        "env_file": "/Users/xiaoyuge/Documents/XXL/backend/.env.production.example",
        "checks": [
          {
            "name": "env_file_exists",
            "ok": true,
            "message": "env 文件存在。",
            "value": "/Users/xiaoyuge/Documents/XXL/backend/.env.production.example"
          },
          {
            "name": "required:WORKBOT_ENVIRONMENT",
            "ok": true,
            "message": "存在且非空。",
            "value": "production"
          },
          {
            "name": "non_default:WORKBOT_ENVIRONMENT",
            "ok": true,
            "message": "不是默认值。",
            "value": "production"
          },
          {
            "name": "required:WORKBOT_DATABASE_URL",
            "ok": true,
            "message": "存在且非空。",
            "value": "postgresql+psycopg://workbot:ExampleProdPassword123!@db.example.internal:5432/workbot"
          },
          {
            "name": "non_default:WORKBOT_DATABASE_URL",
            "ok": true,
            "message": "不是默认值。",
            "value": "postgresql+psycopg://workbot:ExampleProdPassword123!@db.example.internal:5432/workbot"
          },
          {
            "name": "required:WORKBOT_REDIS_URL",
            "ok": true,
            "message": "存在且非空。",
            "value": "redis://redis.example.internal:6379/0"
          },
          {
            "name": "non_default:WORKBOT_REDIS_URL",
            "ok": true,
            "message": "不是默认值。",
            "value": "redis://redis.example.internal:6379/0"
          },
          {
            "name": "required:WORKBOT_NATS_URL",
            "ok": true,
            "message": "存在且非空。",
            "value": "nats://nats.example.internal:4222"
          },
          {
            "name": "non_default:WORKBOT_NATS_URL",
            "ok": true,
            "message": "不是默认值。",
            "value": "nats://nats.example.internal:4222"
          },
          {
            "name": "required:WORKBOT_DATA_ENCRYPTION_KEY",
            "ok": true,
            "message": "存在且非空。",
            "value": "example-prod-key-1234567890abcdef"
          },
          {
            "name": "non_default:WORKBOT_DATA_ENCRYPTION_KEY",
            "ok": true,
            "message": "不是默认值。",
            "value": "example-prod-key-1234567890abcdef"
          },
          {
            "name": "production_environment",
            "ok": true,
            "message": "环境为 production。",
            "value": "production"
          },
          {
            "name": "database_not_localhost",
            "ok": true,
            "message": "数据库 host 合法。",
            "value": "db.example.internal"
          },
          {
            "name": "database_password_strong",
            "ok": true,
            "message": "数据库口令强度通过。",
            "value": "***"
          },
          {
            "name": "nats_not_localhost",
            "ok": true,
            "message": "NATS host 合法。",
            "value": "nats.example.internal"
          },
          {
            "name": "redis_not_localhost",
            "ok": true,
            "message": "Redis host 合法。",
            "value": "redis.example.internal"
          },
          {
            "name": "data_encryption_key_strong",
            "ok": true,
            "message": "加密密钥强度通过。",
            "value": "<redacted>"
          }
        ],
        "ok": true
      }
    },
    "release_matrix": {
      "ok": true,
      "summary": {
        "frontend_version": "0.1.0",
        "backend_agent_protocol": "agentbus.v1",
        "external_agent_compatibility": "brain-core-v1",
        "external_skill_compatibility": "brain-core-v1"
      }
    }
  },
  "generated_at": "2026-04-15T19:44:18+00:00"
}
```
