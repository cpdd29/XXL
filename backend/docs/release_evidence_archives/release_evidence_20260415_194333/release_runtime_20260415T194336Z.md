# Release Runtime Verification

## Status

```json
{
  "ok": true,
  "status": "passed",
  "generated_at": "2026-04-15T19:43:36+00:00"
}
```

## Payload

```json
{
  "ok": true,
  "status": "passed",
  "checked_at": "2026-04-15T19:43:36+00:00",
  "scenario": "all",
  "failed_steps": [],
  "summary": {
    "requested_scenarios": [
      "postdeploy",
      "rollback",
      "recovery"
    ],
    "passed_scenarios": [
      "postdeploy",
      "rollback",
      "recovery"
    ],
    "failed_scenarios": [],
    "snapshot_root": "/Users/xiaoyuge/Documents/XXL/backend/data/release_snapshots",
    "backend_base_url": "http://127.0.0.1:8080"
  },
  "scenarios": {
    "postdeploy": {
      "ok": true,
      "status": "passed",
      "scenario": "postdeploy",
      "checked_at": "2026-04-15T19:43:35+00:00",
      "checks": [
        {
          "key": "release_preflight_ready",
          "ok": true,
          "details": {
            "include_live_database": true
          }
        },
        {
          "key": "brain_runtime_ready",
          "ok": true,
          "details": {
            "require_production_ready": false,
            "startup_ready": true,
            "production_ready": false,
            "status": "degraded_startable"
          }
        },
        {
          "key": "runtime_endpoints_ready",
          "ok": true,
          "details": {
            "backend_base_url": "http://127.0.0.1:8080",
            "required_endpoints": [
              "health"
            ],
            "reachable_required_endpoints": 1
          }
        }
      ],
      "failed_steps": [],
      "components": {
        "persistence_contract": {
          "ok": false,
          "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
          "scheme": "postgresql+psycopg",
          "driver": "postgresql",
          "host": "localhost",
          "port": 5432,
          "is_sqlite": false,
          "is_localhost": true,
          "uses_default_url": true,
          "persistence_enabled": true,
          "probe_error": null,
          "warnings": [
            "database_url 仍为默认值。",
            "database_url 指向 localhost，本机真源不符合生产部署约束。"
          ]
        },
        "release_preflight": {
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
          }
        },
        "brain_prelaunch": {
          "ok": true,
          "startup_ready": true,
          "production_ready": false,
          "status": "degraded_startable",
          "checks": {
            "platform_readiness": {
              "captured_at": "2026-04-15T19:43:35+00:00",
              "environment": "docker-compose",
              "persistence_enabled": false,
              "nats_connected": true,
              "fallback_event_bus_available": true,
              "runbook_exists": true,
              "result_template_exists": true,
              "warnings": [
                "当前未连接正式持久层，真源校验将基于内存/降级模式。"
              ]
            },
            "persistence_contract": {
              "ok": false,
              "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
              "scheme": "postgresql+psycopg",
              "driver": "postgresql",
              "host": "localhost",
              "port": 5432,
              "is_sqlite": false,
              "is_localhost": true,
              "uses_default_url": true,
              "persistence_enabled": true,
              "probe_error": null,
              "warnings": [
                "database_url 仍为默认值。",
                "database_url 指向 localhost，本机真源不符合生产部署约束。"
              ]
            },
            "nats_contract": {
              "ok": false,
              "nats_url": "nats://localhost:4222",
              "scheme": "nats",
              "host": "localhost",
              "port": 4222,
              "uses_default_url": true,
              "is_localhost": true,
              "connected": true,
              "fallback_mode": false,
              "handler_registrations": 5,
              "subscription_registrations": 5,
              "last_error": null,
              "probe_error": null,
              "warnings": [
                "nats_url 仍为默认值。",
                "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
              ]
            },
            "scheduler_startup": {
              "ok": true,
              "checks": {
                "platform_readiness": {
                  "ok": true,
                  "summary": {
                    "captured_at": "2026-04-15T19:43:35+00:00",
                    "environment": "docker-compose",
                    "persistence_enabled": false,
                    "nats_connected": true,
                    "fallback_event_bus_available": true,
                    "runbook_exists": true,
                    "result_template_exists": true,
                    "warnings": [
                      "当前未连接正式持久层，真源校验将基于内存/降级模式。"
                    ],
                    "persistence_contract": {
                      "ok": false,
                      "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                      "scheme": "postgresql+psycopg",
                      "driver": "postgresql",
                      "host": "localhost",
                      "port": 5432,
                      "is_sqlite": false,
                      "is_localhost": true,
                      "uses_default_url": true,
                      "persistence_enabled": true,
                      "probe_error": null,
                      "warnings": [
                        "database_url 仍为默认值。",
                        "database_url 指向 localhost，本机真源不符合生产部署约束。"
                      ]
                    },
                    "nats_contract": {
                      "ok": false,
                      "nats_url": "nats://localhost:4222",
                      "scheme": "nats",
                      "host": "localhost",
                      "port": 4222,
                      "uses_default_url": true,
                      "is_localhost": true,
                      "connected": true,
                      "fallback_mode": false,
                      "handler_registrations": 5,
                      "subscription_registrations": 5,
                      "last_error": null,
                      "probe_error": null,
                      "warnings": [
                        "nats_url 仍为默认值。",
                        "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
                      ]
                    }
                  }
                },
                "dispatch_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_workflow_dispatch_jobs",
                      "release_workflow_dispatch_job_claim",
                      "list_workflow_dispatch_jobs",
                      "claim_due_workflow_runs",
                      "release_workflow_run_claim",
                      "list_workflow_runs"
                    ],
                    "missing": [],
                    "count": 6
                  }
                },
                "workflow_execution_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_workflow_execution_jobs",
                      "claim_workflow_execution_job",
                      "release_workflow_execution_job_claim",
                      "delete_workflow_execution_job",
                      "upsert_workflow_execution_job",
                      "list_workflow_execution_jobs",
                      "list_workflow_runs"
                    ],
                    "missing": [],
                    "count": 7
                  }
                },
                "agent_execution_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_agent_execution_jobs",
                      "claim_agent_execution_job",
                      "release_agent_execution_job_claim",
                      "delete_agent_execution_job",
                      "upsert_agent_execution_job",
                      "list_agent_execution_jobs",
                      "list_workflow_runs",
                      "list_tasks"
                    ],
                    "missing": [],
                    "count": 8
                  }
                },
                "guard_runtime": {
                  "ok": true,
                  "methods": {
                    "available": [
                      "guard_dispatch_runtime",
                      "guard_workflow_execution_runtime",
                      "guard_agent_execution_runtime"
                    ],
                    "missing": [],
                    "count": 3
                  }
                },
                "lease_window": {
                  "ok": true,
                  "summary": {
                    "dispatch_lease_seconds": 30.0,
                    "dispatch_poll_interval_seconds": 1.0,
                    "workflow_execution_lease_seconds": 45.0,
                    "workflow_execution_poll_interval_seconds": 1.0,
                    "workflow_execution_scan_limit": 50
                  }
                },
                "multi_instance_guard": {
                  "ok": true,
                  "mode": "enabled",
                  "summary": {
                    "persistence_enabled": true,
                    "strict_multi_instance_ready": true
                  },
                  "warnings": []
                }
              }
            },
            "scheduler_runtime_pg_acceptance": {
              "ok": false,
              "ran": false,
              "skipped": true,
              "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
              "skip_reason": "persistence_contract_not_ready"
            },
            "release_preflight": {
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
              }
            },
            "security_controls": {
              "ok": true,
              "checks": [
                {
                  "key": "allow_and_audit",
                  "ok": true,
                  "summary": {
                    "trace_id": "trace-f49d316aa913",
                    "audit_action": "安全网关放行"
                  }
                },
                {
                  "key": "redaction_and_audit",
                  "ok": true,
                  "summary": {
                    "audit_action": "安全网关改写放行",
                    "rewrite_rules": [
                      "pii_email",
                      "pii_phone",
                      "otp_code"
                    ]
                  }
                },
                {
                  "key": "prompt_injection_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "detail": "Prompt injection risk detected",
                    "audit_action": "安全网关拦截:prompt_injection"
                  }
                },
                {
                  "key": "auth_scope_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "detail": "Message ingest scope is not allowed",
                    "audit_action": "安全网关拦截:auth_rbac"
                  }
                },
                {
                  "key": "rate_limit_block",
                  "ok": true,
                  "summary": {
                    "status_code": 429,
                    "detail": "Rate limit exceeded for this user",
                    "audit_action": "安全网关拦截:rate_limit"
                  }
                },
                {
                  "key": "message_ingest_redaction_side_effects",
                  "ok": true,
                  "summary": {
                    "task_id": "7",
                    "audit_action": "安全网关改写放行",
                    "memory_total": 1
                  }
                },
                {
                  "key": "blocked_message_no_orchestration_side_effects",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "audit_action": "安全网关拦截:prompt_injection",
                    "task_total": 6,
                    "run_total": 0
                  }
                },
                {
                  "key": "message_ingest_auth_scope_route_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "audit_action": "安全网关拦截:auth_rbac"
                  }
                },
                {
                  "key": "message_ingest_rate_limit_route_block",
                  "ok": true,
                  "summary": {
                    "first_status": 200,
                    "second_status": 429,
                    "audit_action": "安全网关拦截:rate_limit"
                  }
                },
                {
                  "key": "workflow_webhook_block_no_orchestration_side_effects",
                  "ok": true,
                  "summary": {
                    "workflow_id": "workflow-2",
                    "status_code": 403,
                    "audit_action": "安全网关拦截:prompt_injection"
                  }
                }
              ],
              "summary": {
                "total_checks": 10,
                "failed_checks": 0
              }
            },
            "security_entrypoints": {
              "ok": true,
              "checks": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "ok": true,
                  "required_calls": [
                    "ingest_unified_message"
                  ],
                  "observed_calls": [
                    "Body",
                    "IngestMessageResponse",
                    "IngestUnifiedMessageRequest.model_validate",
                    "RequestValidationError",
                    "UnifiedMessage",
                    "exc.errors",
                    "ingest_unified_message",
                    "request_payload.model_dump",
                    "router.post",
                    "store.now_string"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "_ingest_channel_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "_validate_channel_secret",
                    "ingest_channel_webhook"
                  ],
                  "observed_calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_validate_channel_secret",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "ingest_channel_webhook",
                    "str"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "ingest_telegram_webhook"
                  ],
                  "observed_calls": [
                    "HTTPException",
                    "Header",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_telegram_webhook",
                    "payload.model_dump",
                    "router.post",
                    "str"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "security_gateway_service.inspect_text_entrypoint",
                    "trigger_workflow_webhook"
                  ],
                  "observed_calls": [
                    "WorkflowActionResponse",
                    "_workflow_webhook_security_text",
                    "_workflow_webhook_user_key",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "router.post",
                    "security_gateway_service.inspect_text_entrypoint",
                    "trigger_workflow_webhook"
                  ],
                  "missing_calls": []
                }
              ],
              "summary": {
                "total_checks": 4,
                "failed_checks": 0
              }
            },
            "security_audit_persistence": {
              "ok": true,
              "checks": [
                {
                  "key": "security_gateway_emit_all_audit_actions",
                  "ok": true,
                  "summary": {
                    "allow_trace_id": "trace-77d593404e94",
                    "rewrite_diff_count": 3,
                    "block_status_code": 403,
                    "block_detail": "Prompt injection risk detected"
                  }
                },
                {
                  "key": "runtime_store_has_audits",
                  "ok": true,
                  "summary": {
                    "runtime_log_count": 7
                  }
                },
                {
                  "key": "audit_logs_persisted_to_truth_source",
                  "ok": true,
                  "summary": {
                    "database_log_count": 10,
                    "expected_actions": [
                      "安全网关拦截:prompt_injection",
                      "安全网关改写放行",
                      "安全网关放行"
                    ],
                    "observed_actions": [
                      "Token 超限",
                      "安全网关拦截:prompt_injection",
                      "安全网关改写放行",
                      "安全网关放行",
                      "工作流修改",
                      "异常请求",
                      "敏感词检测",
                      "权限变更",
                      "用户登录",
                      "登录失败"
                    ]
                  }
                },
                {
                  "key": "truth_source_survives_runtime_reset",
                  "ok": true,
                  "summary": {
                    "runtime_log_ids_count": 7,
                    "persisted_ids_count": 10,
                    "runtime_cleared": true
                  }
                },
                {
                  "key": "persisted_audit_metadata_integrity",
                  "ok": true,
                  "summary": {
                    "actions": [
                      {
                        "action": "安全网关拦截:prompt_injection",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": false
                        }
                      },
                      {
                        "action": "安全网关改写放行",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": true
                        }
                      },
                      {
                        "action": "安全网关放行",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": false
                        }
                      }
                    ]
                  }
                }
              ],
              "summary": {
                "database_path": "/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/security-audit-persistence-fjnkeauo/audit-persistence.db",
                "total_checks": 5,
                "failed_checks": 0
              }
            },
            "external_ingress_bypass": {
              "ok": true,
              "summary": {
                "total_routes": 29,
                "public_external_ingress_routes": 10,
                "authenticated_control_plane_routes": 19,
                "failed_public_routes": 0,
                "manual_review_required": 10
              },
              "routes": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "method": "post",
                  "path": "/ingest",
                  "calls": [
                    "Body",
                    "IngestMessageResponse",
                    "IngestUnifiedMessageRequest.model_validate",
                    "RequestValidationError",
                    "UnifiedMessage",
                    "exc.errors",
                    "ingest_unified_message",
                    "request_payload.model_dump",
                    "router.post",
                    "store.now_string"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "security_gateway"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [
                        "ingest_unified_message"
                      ],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "method": "post",
                  "path": "/telegram",
                  "calls": [
                    "HTTPException",
                    "Header",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_telegram_webhook",
                    "payload.model_dump",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "wecom_webhook_route",
                  "method": "post",
                  "path": "/wecom",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "feishu_webhook_route",
                  "method": "post",
                  "path": "/feishu",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "dingtalk_webhook_route",
                  "method": "post",
                  "path": "/dingtalk",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "method": "post",
                  "path": "/workflows/{trigger_path:path}",
                  "calls": [
                    "WorkflowActionResponse",
                    "_workflow_webhook_security_text",
                    "_workflow_webhook_user_key",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "forwarded_for.split",
                    "json.dumps",
                    "request.headers.get",
                    "router.post",
                    "sanitize_webhook_payload",
                    "security_gateway_service.inspect_text_entrypoint",
                    "str",
                    "str.strip",
                    "trigger_workflow_webhook"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [
                        "security_gateway_service.inspect_text_entrypoint"
                      ],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_agents_route",
                  "method": "get",
                  "path": "/agents",
                  "calls": [
                    "Agent",
                    "Depends",
                    "ExternalAgentListResponse",
                    "external_agent_registry_service.list_agents",
                    "len",
                    "require_permission",
                    "router.get"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_agent_versions_route",
                  "method": "get",
                  "path": "/agents/families/{family}/versions",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityVersionItem",
                    "ExternalCapabilityVersionListResponse",
                    "_agent_version_items",
                    "_rollback_policy",
                    "_rollout_policy",
                    "bool",
                    "external_agent_registry_service.list_versions",
                    "int",
                    "isinstance",
                    "item.get",
                    "len",
                    "list",
                    "raw.get",
                    "require_permission",
                    "router.get",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_skill_versions_route",
                  "method": "get",
                  "path": "/skills/families/{family}/versions",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityVersionItem",
                    "ExternalCapabilityVersionListResponse",
                    "_rollback_policy",
                    "_rollout_policy",
                    "_skill_version_items",
                    "bool",
                    "external_skill_registry_service.list_versions",
                    "int",
                    "isinstance",
                    "item.get",
                    "len",
                    "list",
                    "raw.get",
                    "require_permission",
                    "router.get",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "get_external_capability_health_route",
                  "method": "get",
                  "path": "/health",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityHealthItem",
                    "ExternalCapabilityHealthResponse",
                    "_health_items",
                    "bool",
                    "dict",
                    "external_agent_registry_service.list_agents",
                    "external_agent_registry_service.prune_expired",
                    "external_skill_registry_service.list_skills",
                    "external_skill_registry_service.prune_expired",
                    "int",
                    "item.get",
                    "items.append",
                    "items.sort",
                    "len",
                    "list",
                    "require_permission",
                    "router.get",
                    "str"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "get_external_capability_governance_route",
                  "method": "get",
                  "path": "/governance",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityGovernanceFamilySummary",
                    "ExternalCapabilityGovernanceOverviewResponse",
                    "ExternalCapabilityGovernanceSummary",
                    "Header",
                    "Query",
                    "ValueError",
                    "_agent_governance_summary",
                    "_governance_items",
                    "_pick_family_primary_item",
                    "_rollback_policy",
                    "_rollout_policy",
                    "_skill_governance_summary",
                    "bool",
                    "config_summary.get",
                    "default_item.get",
                    "dict",
                    "external_agent_registry_service.list_agents",
                    "external_agent_registry_service.list_versions",
                    "external_agent_registry_service.prune_expired",
                    "external_skill_registry_service.list_skills",
                    "external_skill_registry_service.list_versions",
                    "external_skill_registry_service.prune_expired",
                    "get_audit_logs",
                    "int",
                    "isinstance",
                    "item.get",
                    "items.append",
                    "items.sort",
                    "len",
                    "list",
                    "next",
                    "primary.get",
                    "raw.get",
                    "require_permission",
                    "resolve_scope",
                    "router.get",
                    "sorted",
                    "str",
                    "str.strip",
                    "sum"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_agent_route",
                  "method": "post",
                  "path": "/agents/register",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_agent_registry_service.register_agent",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_skill_route",
                  "method": "post",
                  "path": "/skills/register",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_skill_registry_service.register_skill",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_agent_heartbeat_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/heartbeat",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_agent_registry_service.report_heartbeat",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_skill_heartbeat_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/heartbeat",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_skill_registry_service.report_heartbeat",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "report_external_agent_failure_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/failures",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.report_failure",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "report_external_skill_failure_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/failures",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.report_failure",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "recover_external_agent_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/recover",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.recover_agent",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "recover_external_skill_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/recover",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.recover_skill",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "promote_external_agent_version_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/promote",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.promote_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "promote_external_skill_version_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/promote",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.promote_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_fallback_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/set-fallback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.set_fallback_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_fallback_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/set-fallback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.set_fallback_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_rollout_policy_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/rollout-policy",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollout_policy",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.set_rollout_policy",
                    "int",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_rollout_policy_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/rollout-policy",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollout_policy",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.set_rollout_policy",
                    "int",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_rollback_policy_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/rollback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollback_policy",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.set_rollback_policy",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_rollback_policy_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/rollback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollback_policy",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.set_rollback_policy",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_deprecated_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/deprecate",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.set_deprecated",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_deprecated_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/deprecate",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.set_deprecated",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                }
              ],
              "failed_public_routes": [],
              "manual_review_required": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "method": "post",
                  "path": "/ingest",
                  "matched_protections": [
                    "security_gateway"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "method": "post",
                  "path": "/telegram",
                  "matched_protections": [
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "wecom_webhook_route",
                  "method": "post",
                  "path": "/wecom",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "feishu_webhook_route",
                  "method": "post",
                  "path": "/feishu",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "dingtalk_webhook_route",
                  "method": "post",
                  "path": "/dingtalk",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "method": "post",
                  "path": "/workflows/{trigger_path:path}",
                  "matched_protections": [
                    "rate_limit",
                    "payload_size",
                    "security_gateway"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_agent_route",
                  "method": "post",
                  "path": "/agents/register",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_skill_route",
                  "method": "post",
                  "path": "/skills/register",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_agent_heartbeat_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/heartbeat",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_skill_heartbeat_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/heartbeat",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                }
              ]
            },
            "dr_result_gate": {
              "ok": true,
              "status": "passed",
              "checks": [
                {
                  "key": "required_reports_present",
                  "ok": true,
                  "details": {
                    "expected": [
                      "precheck",
                      "prepare",
                      "post_verify",
                      "recovery"
                    ],
                    "missing": {},
                    "resolved": {
                      "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                      "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                      "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                      "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                    }
                  }
                },
                {
                  "key": "rto_rpo_fields_present",
                  "ok": true,
                  "details": {
                    "required_fields": [
                      "measurements.rto_seconds",
                      "measurements.estimated_rpo_seconds"
                    ],
                    "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
                  }
                },
                {
                  "key": "failed_manual_intervention_stats_present",
                  "ok": true,
                  "details": {
                    "required_fields": [
                      "gate_stats.failed",
                      "gate_stats.manual_intervention"
                    ]
                  }
                },
                {
                  "key": "formal_drill_kind_required",
                  "ok": true,
                  "details": {
                    "allow_smoke": false,
                    "required_kind": "formal",
                    "report_drill_kinds": {
                      "precheck": "formal",
                      "prepare": "formal",
                      "post_verify": "formal",
                      "recovery": "formal"
                    },
                    "non_formal_reports": {}
                  }
                }
              ],
              "failed_steps": [],
              "reports": {
                "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
              },
              "missing_reports": {},
              "allow_smoke": false,
              "report_drill_kinds": {
                "precheck": "formal",
                "prepare": "formal",
                "post_verify": "formal",
                "recovery": "formal"
              },
              "gate_stats": {
                "failed": 0,
                "manual_intervention": 10
              }
            },
            "nats_roundtrip": {
              "ok": false,
              "ran": false,
              "skipped": true,
              "nats_url": "nats://localhost:4222",
              "skip_reason": "nats_contract_not_ready"
            },
            "nats_transport": {
              "nats_url": "nats://localhost:4222",
              "connected": true,
              "connect_attempted": true,
              "loop_ready": true,
              "handler_registrations": 5,
              "subscription_registrations": 5,
              "retry_interval_seconds": 30.0,
              "operation_timeout_seconds": 1.5,
              "fallback_mode": false,
              "warning_emitted": false,
              "last_error": null
            },
            "strict_gates": [
              {
                "key": "persistent_truth_source_ready",
                "ok": false,
                "summary": {
                  "persistence_enabled": false,
                  "contract": {
                    "ok": false,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "scheme": "postgresql+psycopg",
                    "driver": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "is_sqlite": false,
                    "is_localhost": true,
                    "uses_default_url": true,
                    "persistence_enabled": true,
                    "probe_error": null,
                    "warnings": [
                      "database_url 仍为默认值。",
                      "database_url 指向 localhost，本机真源不符合生产部署约束。"
                    ]
                  }
                }
              },
              {
                "key": "nats_transport_ready",
                "ok": false,
                "summary": {
                  "nats_connected": true,
                  "fallback_event_bus_available": true,
                  "transport": {
                    "nats_url": "nats://localhost:4222",
                    "connected": true,
                    "connect_attempted": true,
                    "loop_ready": true,
                    "handler_registrations": 5,
                    "subscription_registrations": 5,
                    "retry_interval_seconds": 30.0,
                    "operation_timeout_seconds": 1.5,
                    "fallback_mode": false,
                    "warning_emitted": false,
                    "last_error": null
                  },
                  "contract": {
                    "ok": false,
                    "nats_url": "nats://localhost:4222",
                    "scheme": "nats",
                    "host": "localhost",
                    "port": 4222,
                    "uses_default_url": true,
                    "is_localhost": true,
                    "connected": true,
                    "fallback_mode": false,
                    "handler_registrations": 5,
                    "subscription_registrations": 5,
                    "last_error": null,
                    "probe_error": null,
                    "warnings": [
                      "nats_url 仍为默认值。",
                      "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
                    ]
                  },
                  "roundtrip": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "nats_url": "nats://localhost:4222",
                    "skip_reason": "nats_contract_not_ready"
                  }
                }
              },
              {
                "key": "scheduler_multi_instance_ready",
                "ok": true,
                "summary": {
                  "multi_instance_guard": {
                    "ok": true,
                    "mode": "enabled",
                    "summary": {
                      "persistence_enabled": true,
                      "strict_multi_instance_ready": true
                    },
                    "warnings": []
                  },
                  "pg_acceptance": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "skip_reason": "persistence_contract_not_ready"
                  }
                }
              },
              {
                "key": "scheduler_runtime_persistent",
                "ok": true,
                "summary": {
                  "dispatch_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_workflow_dispatch_jobs",
                        "release_workflow_dispatch_job_claim",
                        "list_workflow_dispatch_jobs",
                        "claim_due_workflow_runs",
                        "release_workflow_run_claim",
                        "list_workflow_runs"
                      ],
                      "missing": [],
                      "count": 6
                    }
                  },
                  "workflow_execution_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_workflow_execution_jobs",
                        "claim_workflow_execution_job",
                        "release_workflow_execution_job_claim",
                        "delete_workflow_execution_job",
                        "upsert_workflow_execution_job",
                        "list_workflow_execution_jobs",
                        "list_workflow_runs"
                      ],
                      "missing": [],
                      "count": 7
                    }
                  },
                  "agent_execution_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_agent_execution_jobs",
                        "claim_agent_execution_job",
                        "release_agent_execution_job_claim",
                        "delete_agent_execution_job",
                        "upsert_agent_execution_job",
                        "list_agent_execution_jobs",
                        "list_workflow_runs",
                        "list_tasks"
                      ],
                      "missing": [],
                      "count": 8
                    }
                  },
                  "pg_acceptance": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "skip_reason": "persistence_contract_not_ready"
                  }
                }
              },
              {
                "key": "security_entrypoint_coverage",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "ok": true,
                      "required_calls": [
                        "ingest_unified_message"
                      ],
                      "observed_calls": [
                        "Body",
                        "IngestMessageResponse",
                        "IngestUnifiedMessageRequest.model_validate",
                        "RequestValidationError",
                        "UnifiedMessage",
                        "exc.errors",
                        "ingest_unified_message",
                        "request_payload.model_dump",
                        "router.post",
                        "store.now_string"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "_ingest_channel_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "_validate_channel_secret",
                        "ingest_channel_webhook"
                      ],
                      "observed_calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_validate_channel_secret",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "ingest_channel_webhook",
                        "str"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "ingest_telegram_webhook"
                      ],
                      "observed_calls": [
                        "HTTPException",
                        "Header",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_telegram_webhook",
                        "payload.model_dump",
                        "router.post",
                        "str"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "security_gateway_service.inspect_text_entrypoint",
                        "trigger_workflow_webhook"
                      ],
                      "observed_calls": [
                        "WorkflowActionResponse",
                        "_workflow_webhook_security_text",
                        "_workflow_webhook_user_key",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "router.post",
                        "security_gateway_service.inspect_text_entrypoint",
                        "trigger_workflow_webhook"
                      ],
                      "missing_calls": []
                    }
                  ],
                  "summary": {
                    "total_checks": 4,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "security_controls_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "key": "allow_and_audit",
                      "ok": true,
                      "summary": {
                        "trace_id": "trace-f49d316aa913",
                        "audit_action": "安全网关放行"
                      }
                    },
                    {
                      "key": "redaction_and_audit",
                      "ok": true,
                      "summary": {
                        "audit_action": "安全网关改写放行",
                        "rewrite_rules": [
                          "pii_email",
                          "pii_phone",
                          "otp_code"
                        ]
                      }
                    },
                    {
                      "key": "prompt_injection_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "detail": "Prompt injection risk detected",
                        "audit_action": "安全网关拦截:prompt_injection"
                      }
                    },
                    {
                      "key": "auth_scope_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "detail": "Message ingest scope is not allowed",
                        "audit_action": "安全网关拦截:auth_rbac"
                      }
                    },
                    {
                      "key": "rate_limit_block",
                      "ok": true,
                      "summary": {
                        "status_code": 429,
                        "detail": "Rate limit exceeded for this user",
                        "audit_action": "安全网关拦截:rate_limit"
                      }
                    },
                    {
                      "key": "message_ingest_redaction_side_effects",
                      "ok": true,
                      "summary": {
                        "task_id": "7",
                        "audit_action": "安全网关改写放行",
                        "memory_total": 1
                      }
                    },
                    {
                      "key": "blocked_message_no_orchestration_side_effects",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "audit_action": "安全网关拦截:prompt_injection",
                        "task_total": 6,
                        "run_total": 0
                      }
                    },
                    {
                      "key": "message_ingest_auth_scope_route_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "audit_action": "安全网关拦截:auth_rbac"
                      }
                    },
                    {
                      "key": "message_ingest_rate_limit_route_block",
                      "ok": true,
                      "summary": {
                        "first_status": 200,
                        "second_status": 429,
                        "audit_action": "安全网关拦截:rate_limit"
                      }
                    },
                    {
                      "key": "workflow_webhook_block_no_orchestration_side_effects",
                      "ok": true,
                      "summary": {
                        "workflow_id": "workflow-2",
                        "status_code": 403,
                        "audit_action": "安全网关拦截:prompt_injection"
                      }
                    }
                  ],
                  "summary": {
                    "total_checks": 10,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "security_audit_persistence_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "key": "security_gateway_emit_all_audit_actions",
                      "ok": true,
                      "summary": {
                        "allow_trace_id": "trace-77d593404e94",
                        "rewrite_diff_count": 3,
                        "block_status_code": 403,
                        "block_detail": "Prompt injection risk detected"
                      }
                    },
                    {
                      "key": "runtime_store_has_audits",
                      "ok": true,
                      "summary": {
                        "runtime_log_count": 7
                      }
                    },
                    {
                      "key": "audit_logs_persisted_to_truth_source",
                      "ok": true,
                      "summary": {
                        "database_log_count": 10,
                        "expected_actions": [
                          "安全网关拦截:prompt_injection",
                          "安全网关改写放行",
                          "安全网关放行"
                        ],
                        "observed_actions": [
                          "Token 超限",
                          "安全网关拦截:prompt_injection",
                          "安全网关改写放行",
                          "安全网关放行",
                          "工作流修改",
                          "异常请求",
                          "敏感词检测",
                          "权限变更",
                          "用户登录",
                          "登录失败"
                        ]
                      }
                    },
                    {
                      "key": "truth_source_survives_runtime_reset",
                      "ok": true,
                      "summary": {
                        "runtime_log_ids_count": 7,
                        "persisted_ids_count": 10,
                        "runtime_cleared": true
                      }
                    },
                    {
                      "key": "persisted_audit_metadata_integrity",
                      "ok": true,
                      "summary": {
                        "actions": [
                          {
                            "action": "安全网关拦截:prompt_injection",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": false
                            }
                          },
                          {
                            "action": "安全网关改写放行",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": true
                            }
                          },
                          {
                            "action": "安全网关放行",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": false
                            }
                          }
                        ]
                      }
                    }
                  ],
                  "summary": {
                    "database_path": "/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/security-audit-persistence-fjnkeauo/audit-persistence.db",
                    "total_checks": 5,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "external_ingress_bypass_scan_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "summary": {
                    "total_routes": 29,
                    "public_external_ingress_routes": 10,
                    "authenticated_control_plane_routes": 19,
                    "failed_public_routes": 0,
                    "manual_review_required": 10
                  },
                  "routes": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "method": "post",
                      "path": "/ingest",
                      "calls": [
                        "Body",
                        "IngestMessageResponse",
                        "IngestUnifiedMessageRequest.model_validate",
                        "RequestValidationError",
                        "UnifiedMessage",
                        "exc.errors",
                        "ingest_unified_message",
                        "request_payload.model_dump",
                        "router.post",
                        "store.now_string"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "security_gateway"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [
                            "ingest_unified_message"
                          ],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "method": "post",
                      "path": "/telegram",
                      "calls": [
                        "HTTPException",
                        "Header",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_telegram_webhook",
                        "payload.model_dump",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "wecom_webhook_route",
                      "method": "post",
                      "path": "/wecom",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "feishu_webhook_route",
                      "method": "post",
                      "path": "/feishu",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "dingtalk_webhook_route",
                      "method": "post",
                      "path": "/dingtalk",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "method": "post",
                      "path": "/workflows/{trigger_path:path}",
                      "calls": [
                        "WorkflowActionResponse",
                        "_workflow_webhook_security_text",
                        "_workflow_webhook_user_key",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "forwarded_for.split",
                        "json.dumps",
                        "request.headers.get",
                        "router.post",
                        "sanitize_webhook_payload",
                        "security_gateway_service.inspect_text_entrypoint",
                        "str",
                        "str.strip",
                        "trigger_workflow_webhook"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [
                            "security_gateway_service.inspect_text_entrypoint"
                          ],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_agents_route",
                      "method": "get",
                      "path": "/agents",
                      "calls": [
                        "Agent",
                        "Depends",
                        "ExternalAgentListResponse",
                        "external_agent_registry_service.list_agents",
                        "len",
                        "require_permission",
                        "router.get"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_agent_versions_route",
                      "method": "get",
                      "path": "/agents/families/{family}/versions",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityVersionItem",
                        "ExternalCapabilityVersionListResponse",
                        "_agent_version_items",
                        "_rollback_policy",
                        "_rollout_policy",
                        "bool",
                        "external_agent_registry_service.list_versions",
                        "int",
                        "isinstance",
                        "item.get",
                        "len",
                        "list",
                        "raw.get",
                        "require_permission",
                        "router.get",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_skill_versions_route",
                      "method": "get",
                      "path": "/skills/families/{family}/versions",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityVersionItem",
                        "ExternalCapabilityVersionListResponse",
                        "_rollback_policy",
                        "_rollout_policy",
                        "_skill_version_items",
                        "bool",
                        "external_skill_registry_service.list_versions",
                        "int",
                        "isinstance",
                        "item.get",
                        "len",
                        "list",
                        "raw.get",
                        "require_permission",
                        "router.get",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "get_external_capability_health_route",
                      "method": "get",
                      "path": "/health",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityHealthItem",
                        "ExternalCapabilityHealthResponse",
                        "_health_items",
                        "bool",
                        "dict",
                        "external_agent_registry_service.list_agents",
                        "external_agent_registry_service.prune_expired",
                        "external_skill_registry_service.list_skills",
                        "external_skill_registry_service.prune_expired",
                        "int",
                        "item.get",
                        "items.append",
                        "items.sort",
                        "len",
                        "list",
                        "require_permission",
                        "router.get",
                        "str"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "get_external_capability_governance_route",
                      "method": "get",
                      "path": "/governance",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityGovernanceFamilySummary",
                        "ExternalCapabilityGovernanceOverviewResponse",
                        "ExternalCapabilityGovernanceSummary",
                        "Header",
                        "Query",
                        "ValueError",
                        "_agent_governance_summary",
                        "_governance_items",
                        "_pick_family_primary_item",
                        "_rollback_policy",
                        "_rollout_policy",
                        "_skill_governance_summary",
                        "bool",
                        "config_summary.get",
                        "default_item.get",
                        "dict",
                        "external_agent_registry_service.list_agents",
                        "external_agent_registry_service.list_versions",
                        "external_agent_registry_service.prune_expired",
                        "external_skill_registry_service.list_skills",
                        "external_skill_registry_service.list_versions",
                        "external_skill_registry_service.prune_expired",
                        "get_audit_logs",
                        "int",
                        "isinstance",
                        "item.get",
                        "items.append",
                        "items.sort",
                        "len",
                        "list",
                        "next",
                        "primary.get",
                        "raw.get",
                        "require_permission",
                        "resolve_scope",
                        "router.get",
                        "sorted",
                        "str",
                        "str.strip",
                        "sum"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_agent_route",
                      "method": "post",
                      "path": "/agents/register",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_agent_registry_service.register_agent",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_skill_route",
                      "method": "post",
                      "path": "/skills/register",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_skill_registry_service.register_skill",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_agent_heartbeat_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/heartbeat",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_agent_registry_service.report_heartbeat",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_skill_heartbeat_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/heartbeat",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_skill_registry_service.report_heartbeat",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "report_external_agent_failure_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/failures",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.report_failure",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "report_external_skill_failure_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/failures",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.report_failure",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "recover_external_agent_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/recover",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.recover_agent",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "recover_external_skill_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/recover",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.recover_skill",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "promote_external_agent_version_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/promote",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.promote_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "promote_external_skill_version_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/promote",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.promote_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_fallback_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/set-fallback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.set_fallback_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_fallback_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/set-fallback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.set_fallback_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_rollout_policy_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/rollout-policy",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollout_policy",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.set_rollout_policy",
                        "int",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_rollout_policy_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/rollout-policy",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollout_policy",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.set_rollout_policy",
                        "int",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_rollback_policy_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/rollback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollback_policy",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.set_rollback_policy",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_rollback_policy_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/rollback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollback_policy",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.set_rollback_policy",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_deprecated_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/deprecate",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.set_deprecated",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_deprecated_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/deprecate",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.set_deprecated",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    }
                  ],
                  "failed_public_routes": [],
                  "manual_review_required": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "method": "post",
                      "path": "/ingest",
                      "matched_protections": [
                        "security_gateway"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "method": "post",
                      "path": "/telegram",
                      "matched_protections": [
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "wecom_webhook_route",
                      "method": "post",
                      "path": "/wecom",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "feishu_webhook_route",
                      "method": "post",
                      "path": "/feishu",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "dingtalk_webhook_route",
                      "method": "post",
                      "path": "/dingtalk",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "method": "post",
                      "path": "/workflows/{trigger_path:path}",
                      "matched_protections": [
                        "rate_limit",
                        "payload_size",
                        "security_gateway"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_agent_route",
                      "method": "post",
                      "path": "/agents/register",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_skill_route",
                      "method": "post",
                      "path": "/skills/register",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_agent_heartbeat_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/heartbeat",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_skill_heartbeat_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/heartbeat",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    }
                  ]
                }
              },
              {
                "key": "dr_result_gate_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "status": "passed",
                  "checks": [
                    {
                      "key": "required_reports_present",
                      "ok": true,
                      "details": {
                        "expected": [
                          "precheck",
                          "prepare",
                          "post_verify",
                          "recovery"
                        ],
                        "missing": {},
                        "resolved": {
                          "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                          "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                          "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                          "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                        }
                      }
                    },
                    {
                      "key": "rto_rpo_fields_present",
                      "ok": true,
                      "details": {
                        "required_fields": [
                          "measurements.rto_seconds",
                          "measurements.estimated_rpo_seconds"
                        ],
                        "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
                      }
                    },
                    {
                      "key": "failed_manual_intervention_stats_present",
                      "ok": true,
                      "details": {
                        "required_fields": [
                          "gate_stats.failed",
                          "gate_stats.manual_intervention"
                        ]
                      }
                    },
                    {
                      "key": "formal_drill_kind_required",
                      "ok": true,
                      "details": {
                        "allow_smoke": false,
                        "required_kind": "formal",
                        "report_drill_kinds": {
                          "precheck": "formal",
                          "prepare": "formal",
                          "post_verify": "formal",
                          "recovery": "formal"
                        },
                        "non_formal_reports": {}
                      }
                    }
                  ],
                  "failed_steps": [],
                  "reports": {
                    "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                    "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                    "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                    "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                  },
                  "missing_reports": {},
                  "allow_smoke": false,
                  "report_drill_kinds": {
                    "precheck": "formal",
                    "prepare": "formal",
                    "post_verify": "formal",
                    "recovery": "formal"
                  },
                  "gate_stats": {
                    "failed": 0,
                    "manual_intervention": 10
                  }
                }
              },
              {
                "key": "release_preflight_green",
                "ok": true,
                "summary": {
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
                  }
                }
              },
              {
                "key": "runbook_and_result_template_ready",
                "ok": true,
                "summary": {
                  "runbook_exists": true,
                  "result_template_exists": true
                }
              }
            ]
          },
          "strict_blockers": [
            "未接入正式数据库真源，当前仍处于 fallback/degraded 启动模式。",
            "NATS 未建立正式连接，或真实 roundtrip/queue-group 验收未通过。"
          ],
          "summary": {
            "degraded_startable": true,
            "strict_gate_count": 11,
            "strict_passed": 9,
            "strict_failed": 2,
            "strict_failed_keys": [
              "persistent_truth_source_ready",
              "nats_transport_ready"
            ]
          }
        },
        "runtime_endpoints": {
          "ok": true,
          "status": "passed",
          "checked_at": "2026-04-15T19:43:35+00:00",
          "checks": [
            {
              "key": "health_endpoint_reachable",
              "ok": true,
              "details": {
                "status_code": 200
              }
            },
            {
              "key": "control_plane_auth_available",
              "ok": true,
              "details": {
                "require_control_plane": false,
                "used_access_token": false
              }
            },
            {
              "key": "required_runtime_endpoints_reachable",
              "ok": true,
              "details": {
                "required": [
                  "health"
                ],
                "failed_required": []
              }
            }
          ],
          "failed_steps": [],
          "auth": {
            "used_access_token": false,
            "login": null,
            "require_control_plane": false
          },
          "summary": {
            "backend_base_url": "http://127.0.0.1:8080",
            "required_endpoints": [
              "health"
            ],
            "reachable_required_endpoints": 1
          },
          "probes": [
            {
              "name": "health",
              "url": "http://127.0.0.1:8080/health",
              "ok": true,
              "status_code": 200,
              "error": null,
              "auth_used": "anonymous",
              "body_excerpt": "{\"status\":\"ok\",\"environment\":\"docker-compose\"}"
            },
            {
              "name": "dashboard_stats",
              "url": "http://127.0.0.1:8080/api/dashboard/stats",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            },
            {
              "name": "tools_health",
              "url": "http://127.0.0.1:8080/api/tools/health?refresh=true",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            },
            {
              "name": "external_health",
              "url": "http://127.0.0.1:8080/api/external-connections/health",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            }
          ]
        }
      }
    },
    "rollback": {
      "ok": true,
      "status": "passed",
      "scenario": "rollback",
      "checked_at": "2026-04-15T19:43:36+00:00",
      "checks": [
        {
          "key": "rollback_snapshot_available",
          "ok": true,
          "details": {
            "snapshot_root": "/Users/xiaoyuge/Documents/XXL/backend/data/release_snapshots",
            "total_snapshots": 1,
            "available_snapshots": [
              "20260414_031232"
            ],
            "selected_snapshot": "20260414_031232",
            "selected_exists": true,
            "selected_files": [
              "backend.env",
              "docker-compose.rendered.yml",
              "docker-compose.yml",
              "root.env"
            ]
          }
        },
        {
          "key": "release_preflight_ready",
          "ok": true,
          "details": {
            "include_live_database": true
          }
        },
        {
          "key": "brain_runtime_ready",
          "ok": true,
          "details": {
            "require_production_ready": false,
            "startup_ready": true,
            "production_ready": false,
            "status": "degraded_startable"
          }
        },
        {
          "key": "runtime_endpoints_ready",
          "ok": true,
          "details": {
            "backend_base_url": "http://127.0.0.1:8080",
            "required_endpoints": [
              "health"
            ],
            "reachable_required_endpoints": 1
          }
        }
      ],
      "failed_steps": [],
      "components": {
        "persistence_contract": {
          "ok": false,
          "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
          "scheme": "postgresql+psycopg",
          "driver": "postgresql",
          "host": "localhost",
          "port": 5432,
          "is_sqlite": false,
          "is_localhost": true,
          "uses_default_url": true,
          "persistence_enabled": true,
          "probe_error": null,
          "warnings": [
            "database_url 仍为默认值。",
            "database_url 指向 localhost，本机真源不符合生产部署约束。"
          ]
        },
        "release_preflight": {
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
          }
        },
        "brain_prelaunch": {
          "ok": true,
          "startup_ready": true,
          "production_ready": false,
          "status": "degraded_startable",
          "checks": {
            "platform_readiness": {
              "captured_at": "2026-04-15T19:43:35+00:00",
              "environment": "docker-compose",
              "persistence_enabled": false,
              "nats_connected": true,
              "fallback_event_bus_available": true,
              "runbook_exists": true,
              "result_template_exists": true,
              "warnings": [
                "当前未连接正式持久层，真源校验将基于内存/降级模式。"
              ]
            },
            "persistence_contract": {
              "ok": false,
              "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
              "scheme": "postgresql+psycopg",
              "driver": "postgresql",
              "host": "localhost",
              "port": 5432,
              "is_sqlite": false,
              "is_localhost": true,
              "uses_default_url": true,
              "persistence_enabled": true,
              "probe_error": null,
              "warnings": [
                "database_url 仍为默认值。",
                "database_url 指向 localhost，本机真源不符合生产部署约束。"
              ]
            },
            "nats_contract": {
              "ok": false,
              "nats_url": "nats://localhost:4222",
              "scheme": "nats",
              "host": "localhost",
              "port": 4222,
              "uses_default_url": true,
              "is_localhost": true,
              "connected": true,
              "fallback_mode": false,
              "handler_registrations": 5,
              "subscription_registrations": 5,
              "last_error": null,
              "probe_error": null,
              "warnings": [
                "nats_url 仍为默认值。",
                "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
              ]
            },
            "scheduler_startup": {
              "ok": true,
              "checks": {
                "platform_readiness": {
                  "ok": true,
                  "summary": {
                    "captured_at": "2026-04-15T19:43:35+00:00",
                    "environment": "docker-compose",
                    "persistence_enabled": false,
                    "nats_connected": true,
                    "fallback_event_bus_available": true,
                    "runbook_exists": true,
                    "result_template_exists": true,
                    "warnings": [
                      "当前未连接正式持久层，真源校验将基于内存/降级模式。"
                    ],
                    "persistence_contract": {
                      "ok": false,
                      "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                      "scheme": "postgresql+psycopg",
                      "driver": "postgresql",
                      "host": "localhost",
                      "port": 5432,
                      "is_sqlite": false,
                      "is_localhost": true,
                      "uses_default_url": true,
                      "persistence_enabled": true,
                      "probe_error": null,
                      "warnings": [
                        "database_url 仍为默认值。",
                        "database_url 指向 localhost，本机真源不符合生产部署约束。"
                      ]
                    },
                    "nats_contract": {
                      "ok": false,
                      "nats_url": "nats://localhost:4222",
                      "scheme": "nats",
                      "host": "localhost",
                      "port": 4222,
                      "uses_default_url": true,
                      "is_localhost": true,
                      "connected": true,
                      "fallback_mode": false,
                      "handler_registrations": 5,
                      "subscription_registrations": 5,
                      "last_error": null,
                      "probe_error": null,
                      "warnings": [
                        "nats_url 仍为默认值。",
                        "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
                      ]
                    }
                  }
                },
                "dispatch_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_workflow_dispatch_jobs",
                      "release_workflow_dispatch_job_claim",
                      "list_workflow_dispatch_jobs",
                      "claim_due_workflow_runs",
                      "release_workflow_run_claim",
                      "list_workflow_runs"
                    ],
                    "missing": [],
                    "count": 6
                  }
                },
                "workflow_execution_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_workflow_execution_jobs",
                      "claim_workflow_execution_job",
                      "release_workflow_execution_job_claim",
                      "delete_workflow_execution_job",
                      "upsert_workflow_execution_job",
                      "list_workflow_execution_jobs",
                      "list_workflow_runs"
                    ],
                    "missing": [],
                    "count": 7
                  }
                },
                "agent_execution_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_agent_execution_jobs",
                      "claim_agent_execution_job",
                      "release_agent_execution_job_claim",
                      "delete_agent_execution_job",
                      "upsert_agent_execution_job",
                      "list_agent_execution_jobs",
                      "list_workflow_runs",
                      "list_tasks"
                    ],
                    "missing": [],
                    "count": 8
                  }
                },
                "guard_runtime": {
                  "ok": true,
                  "methods": {
                    "available": [
                      "guard_dispatch_runtime",
                      "guard_workflow_execution_runtime",
                      "guard_agent_execution_runtime"
                    ],
                    "missing": [],
                    "count": 3
                  }
                },
                "lease_window": {
                  "ok": true,
                  "summary": {
                    "dispatch_lease_seconds": 30.0,
                    "dispatch_poll_interval_seconds": 1.0,
                    "workflow_execution_lease_seconds": 45.0,
                    "workflow_execution_poll_interval_seconds": 1.0,
                    "workflow_execution_scan_limit": 50
                  }
                },
                "multi_instance_guard": {
                  "ok": true,
                  "mode": "enabled",
                  "summary": {
                    "persistence_enabled": true,
                    "strict_multi_instance_ready": true
                  },
                  "warnings": []
                }
              }
            },
            "scheduler_runtime_pg_acceptance": {
              "ok": false,
              "ran": false,
              "skipped": true,
              "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
              "skip_reason": "persistence_contract_not_ready"
            },
            "release_preflight": {
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
              }
            },
            "security_controls": {
              "ok": true,
              "checks": [
                {
                  "key": "allow_and_audit",
                  "ok": true,
                  "summary": {
                    "trace_id": "trace-c4c5a042006d",
                    "audit_action": "安全网关放行"
                  }
                },
                {
                  "key": "redaction_and_audit",
                  "ok": true,
                  "summary": {
                    "audit_action": "安全网关改写放行",
                    "rewrite_rules": [
                      "pii_email",
                      "pii_phone",
                      "otp_code"
                    ]
                  }
                },
                {
                  "key": "prompt_injection_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "detail": "Prompt injection risk detected",
                    "audit_action": "安全网关拦截:prompt_injection"
                  }
                },
                {
                  "key": "auth_scope_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "detail": "Message ingest scope is not allowed",
                    "audit_action": "安全网关拦截:auth_rbac"
                  }
                },
                {
                  "key": "rate_limit_block",
                  "ok": true,
                  "summary": {
                    "status_code": 429,
                    "detail": "Rate limit exceeded for this user",
                    "audit_action": "安全网关拦截:rate_limit"
                  }
                },
                {
                  "key": "message_ingest_redaction_side_effects",
                  "ok": true,
                  "summary": {
                    "task_id": "7",
                    "audit_action": "安全网关改写放行",
                    "memory_total": 1
                  }
                },
                {
                  "key": "blocked_message_no_orchestration_side_effects",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "audit_action": "安全网关拦截:prompt_injection",
                    "task_total": 6,
                    "run_total": 0
                  }
                },
                {
                  "key": "message_ingest_auth_scope_route_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "audit_action": "安全网关拦截:auth_rbac"
                  }
                },
                {
                  "key": "message_ingest_rate_limit_route_block",
                  "ok": true,
                  "summary": {
                    "first_status": 200,
                    "second_status": 429,
                    "audit_action": "安全网关拦截:rate_limit"
                  }
                },
                {
                  "key": "workflow_webhook_block_no_orchestration_side_effects",
                  "ok": true,
                  "summary": {
                    "workflow_id": "workflow-2",
                    "status_code": 403,
                    "audit_action": "安全网关拦截:prompt_injection"
                  }
                }
              ],
              "summary": {
                "total_checks": 10,
                "failed_checks": 0
              }
            },
            "security_entrypoints": {
              "ok": true,
              "checks": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "ok": true,
                  "required_calls": [
                    "ingest_unified_message"
                  ],
                  "observed_calls": [
                    "Body",
                    "IngestMessageResponse",
                    "IngestUnifiedMessageRequest.model_validate",
                    "RequestValidationError",
                    "UnifiedMessage",
                    "exc.errors",
                    "ingest_unified_message",
                    "request_payload.model_dump",
                    "router.post",
                    "store.now_string"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "_ingest_channel_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "_validate_channel_secret",
                    "ingest_channel_webhook"
                  ],
                  "observed_calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_validate_channel_secret",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "ingest_channel_webhook",
                    "str"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "ingest_telegram_webhook"
                  ],
                  "observed_calls": [
                    "HTTPException",
                    "Header",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_telegram_webhook",
                    "payload.model_dump",
                    "router.post",
                    "str"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "security_gateway_service.inspect_text_entrypoint",
                    "trigger_workflow_webhook"
                  ],
                  "observed_calls": [
                    "WorkflowActionResponse",
                    "_workflow_webhook_security_text",
                    "_workflow_webhook_user_key",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "router.post",
                    "security_gateway_service.inspect_text_entrypoint",
                    "trigger_workflow_webhook"
                  ],
                  "missing_calls": []
                }
              ],
              "summary": {
                "total_checks": 4,
                "failed_checks": 0
              }
            },
            "security_audit_persistence": {
              "ok": true,
              "checks": [
                {
                  "key": "security_gateway_emit_all_audit_actions",
                  "ok": true,
                  "summary": {
                    "allow_trace_id": "trace-8b86117f0f21",
                    "rewrite_diff_count": 3,
                    "block_status_code": 403,
                    "block_detail": "Prompt injection risk detected"
                  }
                },
                {
                  "key": "runtime_store_has_audits",
                  "ok": true,
                  "summary": {
                    "runtime_log_count": 7
                  }
                },
                {
                  "key": "audit_logs_persisted_to_truth_source",
                  "ok": true,
                  "summary": {
                    "database_log_count": 10,
                    "expected_actions": [
                      "安全网关拦截:prompt_injection",
                      "安全网关改写放行",
                      "安全网关放行"
                    ],
                    "observed_actions": [
                      "Token 超限",
                      "安全网关拦截:prompt_injection",
                      "安全网关改写放行",
                      "安全网关放行",
                      "工作流修改",
                      "异常请求",
                      "敏感词检测",
                      "权限变更",
                      "用户登录",
                      "登录失败"
                    ]
                  }
                },
                {
                  "key": "truth_source_survives_runtime_reset",
                  "ok": true,
                  "summary": {
                    "runtime_log_ids_count": 7,
                    "persisted_ids_count": 10,
                    "runtime_cleared": true
                  }
                },
                {
                  "key": "persisted_audit_metadata_integrity",
                  "ok": true,
                  "summary": {
                    "actions": [
                      {
                        "action": "安全网关拦截:prompt_injection",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": false
                        }
                      },
                      {
                        "action": "安全网关改写放行",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": true
                        }
                      },
                      {
                        "action": "安全网关放行",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": false
                        }
                      }
                    ]
                  }
                }
              ],
              "summary": {
                "database_path": "/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/security-audit-persistence-i009lzdp/audit-persistence.db",
                "total_checks": 5,
                "failed_checks": 0
              }
            },
            "external_ingress_bypass": {
              "ok": true,
              "summary": {
                "total_routes": 29,
                "public_external_ingress_routes": 10,
                "authenticated_control_plane_routes": 19,
                "failed_public_routes": 0,
                "manual_review_required": 10
              },
              "routes": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "method": "post",
                  "path": "/ingest",
                  "calls": [
                    "Body",
                    "IngestMessageResponse",
                    "IngestUnifiedMessageRequest.model_validate",
                    "RequestValidationError",
                    "UnifiedMessage",
                    "exc.errors",
                    "ingest_unified_message",
                    "request_payload.model_dump",
                    "router.post",
                    "store.now_string"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "security_gateway"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [
                        "ingest_unified_message"
                      ],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "method": "post",
                  "path": "/telegram",
                  "calls": [
                    "HTTPException",
                    "Header",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_telegram_webhook",
                    "payload.model_dump",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "wecom_webhook_route",
                  "method": "post",
                  "path": "/wecom",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "feishu_webhook_route",
                  "method": "post",
                  "path": "/feishu",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "dingtalk_webhook_route",
                  "method": "post",
                  "path": "/dingtalk",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "method": "post",
                  "path": "/workflows/{trigger_path:path}",
                  "calls": [
                    "WorkflowActionResponse",
                    "_workflow_webhook_security_text",
                    "_workflow_webhook_user_key",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "forwarded_for.split",
                    "json.dumps",
                    "request.headers.get",
                    "router.post",
                    "sanitize_webhook_payload",
                    "security_gateway_service.inspect_text_entrypoint",
                    "str",
                    "str.strip",
                    "trigger_workflow_webhook"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [
                        "security_gateway_service.inspect_text_entrypoint"
                      ],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_agents_route",
                  "method": "get",
                  "path": "/agents",
                  "calls": [
                    "Agent",
                    "Depends",
                    "ExternalAgentListResponse",
                    "external_agent_registry_service.list_agents",
                    "len",
                    "require_permission",
                    "router.get"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_agent_versions_route",
                  "method": "get",
                  "path": "/agents/families/{family}/versions",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityVersionItem",
                    "ExternalCapabilityVersionListResponse",
                    "_agent_version_items",
                    "_rollback_policy",
                    "_rollout_policy",
                    "bool",
                    "external_agent_registry_service.list_versions",
                    "int",
                    "isinstance",
                    "item.get",
                    "len",
                    "list",
                    "raw.get",
                    "require_permission",
                    "router.get",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_skill_versions_route",
                  "method": "get",
                  "path": "/skills/families/{family}/versions",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityVersionItem",
                    "ExternalCapabilityVersionListResponse",
                    "_rollback_policy",
                    "_rollout_policy",
                    "_skill_version_items",
                    "bool",
                    "external_skill_registry_service.list_versions",
                    "int",
                    "isinstance",
                    "item.get",
                    "len",
                    "list",
                    "raw.get",
                    "require_permission",
                    "router.get",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "get_external_capability_health_route",
                  "method": "get",
                  "path": "/health",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityHealthItem",
                    "ExternalCapabilityHealthResponse",
                    "_health_items",
                    "bool",
                    "dict",
                    "external_agent_registry_service.list_agents",
                    "external_agent_registry_service.prune_expired",
                    "external_skill_registry_service.list_skills",
                    "external_skill_registry_service.prune_expired",
                    "int",
                    "item.get",
                    "items.append",
                    "items.sort",
                    "len",
                    "list",
                    "require_permission",
                    "router.get",
                    "str"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "get_external_capability_governance_route",
                  "method": "get",
                  "path": "/governance",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityGovernanceFamilySummary",
                    "ExternalCapabilityGovernanceOverviewResponse",
                    "ExternalCapabilityGovernanceSummary",
                    "Header",
                    "Query",
                    "ValueError",
                    "_agent_governance_summary",
                    "_governance_items",
                    "_pick_family_primary_item",
                    "_rollback_policy",
                    "_rollout_policy",
                    "_skill_governance_summary",
                    "bool",
                    "config_summary.get",
                    "default_item.get",
                    "dict",
                    "external_agent_registry_service.list_agents",
                    "external_agent_registry_service.list_versions",
                    "external_agent_registry_service.prune_expired",
                    "external_skill_registry_service.list_skills",
                    "external_skill_registry_service.list_versions",
                    "external_skill_registry_service.prune_expired",
                    "get_audit_logs",
                    "int",
                    "isinstance",
                    "item.get",
                    "items.append",
                    "items.sort",
                    "len",
                    "list",
                    "next",
                    "primary.get",
                    "raw.get",
                    "require_permission",
                    "resolve_scope",
                    "router.get",
                    "sorted",
                    "str",
                    "str.strip",
                    "sum"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_agent_route",
                  "method": "post",
                  "path": "/agents/register",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_agent_registry_service.register_agent",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_skill_route",
                  "method": "post",
                  "path": "/skills/register",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_skill_registry_service.register_skill",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_agent_heartbeat_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/heartbeat",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_agent_registry_service.report_heartbeat",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_skill_heartbeat_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/heartbeat",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_skill_registry_service.report_heartbeat",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "report_external_agent_failure_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/failures",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.report_failure",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "report_external_skill_failure_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/failures",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.report_failure",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "recover_external_agent_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/recover",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.recover_agent",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "recover_external_skill_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/recover",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.recover_skill",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "promote_external_agent_version_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/promote",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.promote_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "promote_external_skill_version_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/promote",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.promote_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_fallback_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/set-fallback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.set_fallback_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_fallback_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/set-fallback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.set_fallback_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_rollout_policy_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/rollout-policy",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollout_policy",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.set_rollout_policy",
                    "int",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_rollout_policy_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/rollout-policy",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollout_policy",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.set_rollout_policy",
                    "int",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_rollback_policy_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/rollback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollback_policy",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.set_rollback_policy",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_rollback_policy_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/rollback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollback_policy",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.set_rollback_policy",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_deprecated_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/deprecate",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.set_deprecated",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_deprecated_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/deprecate",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.set_deprecated",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                }
              ],
              "failed_public_routes": [],
              "manual_review_required": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "method": "post",
                  "path": "/ingest",
                  "matched_protections": [
                    "security_gateway"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "method": "post",
                  "path": "/telegram",
                  "matched_protections": [
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "wecom_webhook_route",
                  "method": "post",
                  "path": "/wecom",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "feishu_webhook_route",
                  "method": "post",
                  "path": "/feishu",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "dingtalk_webhook_route",
                  "method": "post",
                  "path": "/dingtalk",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "method": "post",
                  "path": "/workflows/{trigger_path:path}",
                  "matched_protections": [
                    "rate_limit",
                    "payload_size",
                    "security_gateway"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_agent_route",
                  "method": "post",
                  "path": "/agents/register",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_skill_route",
                  "method": "post",
                  "path": "/skills/register",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_agent_heartbeat_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/heartbeat",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_skill_heartbeat_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/heartbeat",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                }
              ]
            },
            "dr_result_gate": {
              "ok": true,
              "status": "passed",
              "checks": [
                {
                  "key": "required_reports_present",
                  "ok": true,
                  "details": {
                    "expected": [
                      "precheck",
                      "prepare",
                      "post_verify",
                      "recovery"
                    ],
                    "missing": {},
                    "resolved": {
                      "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                      "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                      "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                      "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                    }
                  }
                },
                {
                  "key": "rto_rpo_fields_present",
                  "ok": true,
                  "details": {
                    "required_fields": [
                      "measurements.rto_seconds",
                      "measurements.estimated_rpo_seconds"
                    ],
                    "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
                  }
                },
                {
                  "key": "failed_manual_intervention_stats_present",
                  "ok": true,
                  "details": {
                    "required_fields": [
                      "gate_stats.failed",
                      "gate_stats.manual_intervention"
                    ]
                  }
                },
                {
                  "key": "formal_drill_kind_required",
                  "ok": true,
                  "details": {
                    "allow_smoke": false,
                    "required_kind": "formal",
                    "report_drill_kinds": {
                      "precheck": "formal",
                      "prepare": "formal",
                      "post_verify": "formal",
                      "recovery": "formal"
                    },
                    "non_formal_reports": {}
                  }
                }
              ],
              "failed_steps": [],
              "reports": {
                "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
              },
              "missing_reports": {},
              "allow_smoke": false,
              "report_drill_kinds": {
                "precheck": "formal",
                "prepare": "formal",
                "post_verify": "formal",
                "recovery": "formal"
              },
              "gate_stats": {
                "failed": 0,
                "manual_intervention": 10
              }
            },
            "nats_roundtrip": {
              "ok": false,
              "ran": false,
              "skipped": true,
              "nats_url": "nats://localhost:4222",
              "skip_reason": "nats_contract_not_ready"
            },
            "nats_transport": {
              "nats_url": "nats://localhost:4222",
              "connected": true,
              "connect_attempted": true,
              "loop_ready": true,
              "handler_registrations": 5,
              "subscription_registrations": 5,
              "retry_interval_seconds": 30.0,
              "operation_timeout_seconds": 1.5,
              "fallback_mode": false,
              "warning_emitted": false,
              "last_error": null
            },
            "strict_gates": [
              {
                "key": "persistent_truth_source_ready",
                "ok": false,
                "summary": {
                  "persistence_enabled": false,
                  "contract": {
                    "ok": false,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "scheme": "postgresql+psycopg",
                    "driver": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "is_sqlite": false,
                    "is_localhost": true,
                    "uses_default_url": true,
                    "persistence_enabled": true,
                    "probe_error": null,
                    "warnings": [
                      "database_url 仍为默认值。",
                      "database_url 指向 localhost，本机真源不符合生产部署约束。"
                    ]
                  }
                }
              },
              {
                "key": "nats_transport_ready",
                "ok": false,
                "summary": {
                  "nats_connected": true,
                  "fallback_event_bus_available": true,
                  "transport": {
                    "nats_url": "nats://localhost:4222",
                    "connected": true,
                    "connect_attempted": true,
                    "loop_ready": true,
                    "handler_registrations": 5,
                    "subscription_registrations": 5,
                    "retry_interval_seconds": 30.0,
                    "operation_timeout_seconds": 1.5,
                    "fallback_mode": false,
                    "warning_emitted": false,
                    "last_error": null
                  },
                  "contract": {
                    "ok": false,
                    "nats_url": "nats://localhost:4222",
                    "scheme": "nats",
                    "host": "localhost",
                    "port": 4222,
                    "uses_default_url": true,
                    "is_localhost": true,
                    "connected": true,
                    "fallback_mode": false,
                    "handler_registrations": 5,
                    "subscription_registrations": 5,
                    "last_error": null,
                    "probe_error": null,
                    "warnings": [
                      "nats_url 仍为默认值。",
                      "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
                    ]
                  },
                  "roundtrip": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "nats_url": "nats://localhost:4222",
                    "skip_reason": "nats_contract_not_ready"
                  }
                }
              },
              {
                "key": "scheduler_multi_instance_ready",
                "ok": true,
                "summary": {
                  "multi_instance_guard": {
                    "ok": true,
                    "mode": "enabled",
                    "summary": {
                      "persistence_enabled": true,
                      "strict_multi_instance_ready": true
                    },
                    "warnings": []
                  },
                  "pg_acceptance": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "skip_reason": "persistence_contract_not_ready"
                  }
                }
              },
              {
                "key": "scheduler_runtime_persistent",
                "ok": true,
                "summary": {
                  "dispatch_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_workflow_dispatch_jobs",
                        "release_workflow_dispatch_job_claim",
                        "list_workflow_dispatch_jobs",
                        "claim_due_workflow_runs",
                        "release_workflow_run_claim",
                        "list_workflow_runs"
                      ],
                      "missing": [],
                      "count": 6
                    }
                  },
                  "workflow_execution_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_workflow_execution_jobs",
                        "claim_workflow_execution_job",
                        "release_workflow_execution_job_claim",
                        "delete_workflow_execution_job",
                        "upsert_workflow_execution_job",
                        "list_workflow_execution_jobs",
                        "list_workflow_runs"
                      ],
                      "missing": [],
                      "count": 7
                    }
                  },
                  "agent_execution_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_agent_execution_jobs",
                        "claim_agent_execution_job",
                        "release_agent_execution_job_claim",
                        "delete_agent_execution_job",
                        "upsert_agent_execution_job",
                        "list_agent_execution_jobs",
                        "list_workflow_runs",
                        "list_tasks"
                      ],
                      "missing": [],
                      "count": 8
                    }
                  },
                  "pg_acceptance": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "skip_reason": "persistence_contract_not_ready"
                  }
                }
              },
              {
                "key": "security_entrypoint_coverage",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "ok": true,
                      "required_calls": [
                        "ingest_unified_message"
                      ],
                      "observed_calls": [
                        "Body",
                        "IngestMessageResponse",
                        "IngestUnifiedMessageRequest.model_validate",
                        "RequestValidationError",
                        "UnifiedMessage",
                        "exc.errors",
                        "ingest_unified_message",
                        "request_payload.model_dump",
                        "router.post",
                        "store.now_string"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "_ingest_channel_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "_validate_channel_secret",
                        "ingest_channel_webhook"
                      ],
                      "observed_calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_validate_channel_secret",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "ingest_channel_webhook",
                        "str"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "ingest_telegram_webhook"
                      ],
                      "observed_calls": [
                        "HTTPException",
                        "Header",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_telegram_webhook",
                        "payload.model_dump",
                        "router.post",
                        "str"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "security_gateway_service.inspect_text_entrypoint",
                        "trigger_workflow_webhook"
                      ],
                      "observed_calls": [
                        "WorkflowActionResponse",
                        "_workflow_webhook_security_text",
                        "_workflow_webhook_user_key",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "router.post",
                        "security_gateway_service.inspect_text_entrypoint",
                        "trigger_workflow_webhook"
                      ],
                      "missing_calls": []
                    }
                  ],
                  "summary": {
                    "total_checks": 4,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "security_controls_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "key": "allow_and_audit",
                      "ok": true,
                      "summary": {
                        "trace_id": "trace-c4c5a042006d",
                        "audit_action": "安全网关放行"
                      }
                    },
                    {
                      "key": "redaction_and_audit",
                      "ok": true,
                      "summary": {
                        "audit_action": "安全网关改写放行",
                        "rewrite_rules": [
                          "pii_email",
                          "pii_phone",
                          "otp_code"
                        ]
                      }
                    },
                    {
                      "key": "prompt_injection_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "detail": "Prompt injection risk detected",
                        "audit_action": "安全网关拦截:prompt_injection"
                      }
                    },
                    {
                      "key": "auth_scope_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "detail": "Message ingest scope is not allowed",
                        "audit_action": "安全网关拦截:auth_rbac"
                      }
                    },
                    {
                      "key": "rate_limit_block",
                      "ok": true,
                      "summary": {
                        "status_code": 429,
                        "detail": "Rate limit exceeded for this user",
                        "audit_action": "安全网关拦截:rate_limit"
                      }
                    },
                    {
                      "key": "message_ingest_redaction_side_effects",
                      "ok": true,
                      "summary": {
                        "task_id": "7",
                        "audit_action": "安全网关改写放行",
                        "memory_total": 1
                      }
                    },
                    {
                      "key": "blocked_message_no_orchestration_side_effects",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "audit_action": "安全网关拦截:prompt_injection",
                        "task_total": 6,
                        "run_total": 0
                      }
                    },
                    {
                      "key": "message_ingest_auth_scope_route_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "audit_action": "安全网关拦截:auth_rbac"
                      }
                    },
                    {
                      "key": "message_ingest_rate_limit_route_block",
                      "ok": true,
                      "summary": {
                        "first_status": 200,
                        "second_status": 429,
                        "audit_action": "安全网关拦截:rate_limit"
                      }
                    },
                    {
                      "key": "workflow_webhook_block_no_orchestration_side_effects",
                      "ok": true,
                      "summary": {
                        "workflow_id": "workflow-2",
                        "status_code": 403,
                        "audit_action": "安全网关拦截:prompt_injection"
                      }
                    }
                  ],
                  "summary": {
                    "total_checks": 10,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "security_audit_persistence_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "key": "security_gateway_emit_all_audit_actions",
                      "ok": true,
                      "summary": {
                        "allow_trace_id": "trace-8b86117f0f21",
                        "rewrite_diff_count": 3,
                        "block_status_code": 403,
                        "block_detail": "Prompt injection risk detected"
                      }
                    },
                    {
                      "key": "runtime_store_has_audits",
                      "ok": true,
                      "summary": {
                        "runtime_log_count": 7
                      }
                    },
                    {
                      "key": "audit_logs_persisted_to_truth_source",
                      "ok": true,
                      "summary": {
                        "database_log_count": 10,
                        "expected_actions": [
                          "安全网关拦截:prompt_injection",
                          "安全网关改写放行",
                          "安全网关放行"
                        ],
                        "observed_actions": [
                          "Token 超限",
                          "安全网关拦截:prompt_injection",
                          "安全网关改写放行",
                          "安全网关放行",
                          "工作流修改",
                          "异常请求",
                          "敏感词检测",
                          "权限变更",
                          "用户登录",
                          "登录失败"
                        ]
                      }
                    },
                    {
                      "key": "truth_source_survives_runtime_reset",
                      "ok": true,
                      "summary": {
                        "runtime_log_ids_count": 7,
                        "persisted_ids_count": 10,
                        "runtime_cleared": true
                      }
                    },
                    {
                      "key": "persisted_audit_metadata_integrity",
                      "ok": true,
                      "summary": {
                        "actions": [
                          {
                            "action": "安全网关拦截:prompt_injection",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": false
                            }
                          },
                          {
                            "action": "安全网关改写放行",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": true
                            }
                          },
                          {
                            "action": "安全网关放行",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": false
                            }
                          }
                        ]
                      }
                    }
                  ],
                  "summary": {
                    "database_path": "/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/security-audit-persistence-i009lzdp/audit-persistence.db",
                    "total_checks": 5,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "external_ingress_bypass_scan_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "summary": {
                    "total_routes": 29,
                    "public_external_ingress_routes": 10,
                    "authenticated_control_plane_routes": 19,
                    "failed_public_routes": 0,
                    "manual_review_required": 10
                  },
                  "routes": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "method": "post",
                      "path": "/ingest",
                      "calls": [
                        "Body",
                        "IngestMessageResponse",
                        "IngestUnifiedMessageRequest.model_validate",
                        "RequestValidationError",
                        "UnifiedMessage",
                        "exc.errors",
                        "ingest_unified_message",
                        "request_payload.model_dump",
                        "router.post",
                        "store.now_string"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "security_gateway"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [
                            "ingest_unified_message"
                          ],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "method": "post",
                      "path": "/telegram",
                      "calls": [
                        "HTTPException",
                        "Header",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_telegram_webhook",
                        "payload.model_dump",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "wecom_webhook_route",
                      "method": "post",
                      "path": "/wecom",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "feishu_webhook_route",
                      "method": "post",
                      "path": "/feishu",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "dingtalk_webhook_route",
                      "method": "post",
                      "path": "/dingtalk",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "method": "post",
                      "path": "/workflows/{trigger_path:path}",
                      "calls": [
                        "WorkflowActionResponse",
                        "_workflow_webhook_security_text",
                        "_workflow_webhook_user_key",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "forwarded_for.split",
                        "json.dumps",
                        "request.headers.get",
                        "router.post",
                        "sanitize_webhook_payload",
                        "security_gateway_service.inspect_text_entrypoint",
                        "str",
                        "str.strip",
                        "trigger_workflow_webhook"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [
                            "security_gateway_service.inspect_text_entrypoint"
                          ],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_agents_route",
                      "method": "get",
                      "path": "/agents",
                      "calls": [
                        "Agent",
                        "Depends",
                        "ExternalAgentListResponse",
                        "external_agent_registry_service.list_agents",
                        "len",
                        "require_permission",
                        "router.get"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_agent_versions_route",
                      "method": "get",
                      "path": "/agents/families/{family}/versions",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityVersionItem",
                        "ExternalCapabilityVersionListResponse",
                        "_agent_version_items",
                        "_rollback_policy",
                        "_rollout_policy",
                        "bool",
                        "external_agent_registry_service.list_versions",
                        "int",
                        "isinstance",
                        "item.get",
                        "len",
                        "list",
                        "raw.get",
                        "require_permission",
                        "router.get",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_skill_versions_route",
                      "method": "get",
                      "path": "/skills/families/{family}/versions",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityVersionItem",
                        "ExternalCapabilityVersionListResponse",
                        "_rollback_policy",
                        "_rollout_policy",
                        "_skill_version_items",
                        "bool",
                        "external_skill_registry_service.list_versions",
                        "int",
                        "isinstance",
                        "item.get",
                        "len",
                        "list",
                        "raw.get",
                        "require_permission",
                        "router.get",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "get_external_capability_health_route",
                      "method": "get",
                      "path": "/health",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityHealthItem",
                        "ExternalCapabilityHealthResponse",
                        "_health_items",
                        "bool",
                        "dict",
                        "external_agent_registry_service.list_agents",
                        "external_agent_registry_service.prune_expired",
                        "external_skill_registry_service.list_skills",
                        "external_skill_registry_service.prune_expired",
                        "int",
                        "item.get",
                        "items.append",
                        "items.sort",
                        "len",
                        "list",
                        "require_permission",
                        "router.get",
                        "str"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "get_external_capability_governance_route",
                      "method": "get",
                      "path": "/governance",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityGovernanceFamilySummary",
                        "ExternalCapabilityGovernanceOverviewResponse",
                        "ExternalCapabilityGovernanceSummary",
                        "Header",
                        "Query",
                        "ValueError",
                        "_agent_governance_summary",
                        "_governance_items",
                        "_pick_family_primary_item",
                        "_rollback_policy",
                        "_rollout_policy",
                        "_skill_governance_summary",
                        "bool",
                        "config_summary.get",
                        "default_item.get",
                        "dict",
                        "external_agent_registry_service.list_agents",
                        "external_agent_registry_service.list_versions",
                        "external_agent_registry_service.prune_expired",
                        "external_skill_registry_service.list_skills",
                        "external_skill_registry_service.list_versions",
                        "external_skill_registry_service.prune_expired",
                        "get_audit_logs",
                        "int",
                        "isinstance",
                        "item.get",
                        "items.append",
                        "items.sort",
                        "len",
                        "list",
                        "next",
                        "primary.get",
                        "raw.get",
                        "require_permission",
                        "resolve_scope",
                        "router.get",
                        "sorted",
                        "str",
                        "str.strip",
                        "sum"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_agent_route",
                      "method": "post",
                      "path": "/agents/register",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_agent_registry_service.register_agent",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_skill_route",
                      "method": "post",
                      "path": "/skills/register",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_skill_registry_service.register_skill",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_agent_heartbeat_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/heartbeat",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_agent_registry_service.report_heartbeat",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_skill_heartbeat_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/heartbeat",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_skill_registry_service.report_heartbeat",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "report_external_agent_failure_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/failures",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.report_failure",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "report_external_skill_failure_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/failures",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.report_failure",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "recover_external_agent_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/recover",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.recover_agent",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "recover_external_skill_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/recover",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.recover_skill",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "promote_external_agent_version_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/promote",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.promote_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "promote_external_skill_version_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/promote",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.promote_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_fallback_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/set-fallback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.set_fallback_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_fallback_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/set-fallback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.set_fallback_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_rollout_policy_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/rollout-policy",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollout_policy",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.set_rollout_policy",
                        "int",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_rollout_policy_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/rollout-policy",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollout_policy",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.set_rollout_policy",
                        "int",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_rollback_policy_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/rollback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollback_policy",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.set_rollback_policy",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_rollback_policy_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/rollback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollback_policy",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.set_rollback_policy",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_deprecated_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/deprecate",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.set_deprecated",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_deprecated_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/deprecate",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.set_deprecated",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    }
                  ],
                  "failed_public_routes": [],
                  "manual_review_required": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "method": "post",
                      "path": "/ingest",
                      "matched_protections": [
                        "security_gateway"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "method": "post",
                      "path": "/telegram",
                      "matched_protections": [
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "wecom_webhook_route",
                      "method": "post",
                      "path": "/wecom",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "feishu_webhook_route",
                      "method": "post",
                      "path": "/feishu",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "dingtalk_webhook_route",
                      "method": "post",
                      "path": "/dingtalk",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "method": "post",
                      "path": "/workflows/{trigger_path:path}",
                      "matched_protections": [
                        "rate_limit",
                        "payload_size",
                        "security_gateway"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_agent_route",
                      "method": "post",
                      "path": "/agents/register",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_skill_route",
                      "method": "post",
                      "path": "/skills/register",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_agent_heartbeat_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/heartbeat",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_skill_heartbeat_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/heartbeat",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    }
                  ]
                }
              },
              {
                "key": "dr_result_gate_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "status": "passed",
                  "checks": [
                    {
                      "key": "required_reports_present",
                      "ok": true,
                      "details": {
                        "expected": [
                          "precheck",
                          "prepare",
                          "post_verify",
                          "recovery"
                        ],
                        "missing": {},
                        "resolved": {
                          "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                          "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                          "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                          "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                        }
                      }
                    },
                    {
                      "key": "rto_rpo_fields_present",
                      "ok": true,
                      "details": {
                        "required_fields": [
                          "measurements.rto_seconds",
                          "measurements.estimated_rpo_seconds"
                        ],
                        "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
                      }
                    },
                    {
                      "key": "failed_manual_intervention_stats_present",
                      "ok": true,
                      "details": {
                        "required_fields": [
                          "gate_stats.failed",
                          "gate_stats.manual_intervention"
                        ]
                      }
                    },
                    {
                      "key": "formal_drill_kind_required",
                      "ok": true,
                      "details": {
                        "allow_smoke": false,
                        "required_kind": "formal",
                        "report_drill_kinds": {
                          "precheck": "formal",
                          "prepare": "formal",
                          "post_verify": "formal",
                          "recovery": "formal"
                        },
                        "non_formal_reports": {}
                      }
                    }
                  ],
                  "failed_steps": [],
                  "reports": {
                    "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                    "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                    "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                    "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                  },
                  "missing_reports": {},
                  "allow_smoke": false,
                  "report_drill_kinds": {
                    "precheck": "formal",
                    "prepare": "formal",
                    "post_verify": "formal",
                    "recovery": "formal"
                  },
                  "gate_stats": {
                    "failed": 0,
                    "manual_intervention": 10
                  }
                }
              },
              {
                "key": "release_preflight_green",
                "ok": true,
                "summary": {
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
                  }
                }
              },
              {
                "key": "runbook_and_result_template_ready",
                "ok": true,
                "summary": {
                  "runbook_exists": true,
                  "result_template_exists": true
                }
              }
            ]
          },
          "strict_blockers": [
            "未接入正式数据库真源，当前仍处于 fallback/degraded 启动模式。",
            "NATS 未建立正式连接，或真实 roundtrip/queue-group 验收未通过。"
          ],
          "summary": {
            "degraded_startable": true,
            "strict_gate_count": 11,
            "strict_passed": 9,
            "strict_failed": 2,
            "strict_failed_keys": [
              "persistent_truth_source_ready",
              "nats_transport_ready"
            ]
          }
        },
        "runtime_endpoints": {
          "ok": true,
          "status": "passed",
          "checked_at": "2026-04-15T19:43:36+00:00",
          "checks": [
            {
              "key": "health_endpoint_reachable",
              "ok": true,
              "details": {
                "status_code": 200
              }
            },
            {
              "key": "control_plane_auth_available",
              "ok": true,
              "details": {
                "require_control_plane": false,
                "used_access_token": false
              }
            },
            {
              "key": "required_runtime_endpoints_reachable",
              "ok": true,
              "details": {
                "required": [
                  "health"
                ],
                "failed_required": []
              }
            }
          ],
          "failed_steps": [],
          "auth": {
            "used_access_token": false,
            "login": null,
            "require_control_plane": false
          },
          "summary": {
            "backend_base_url": "http://127.0.0.1:8080",
            "required_endpoints": [
              "health"
            ],
            "reachable_required_endpoints": 1
          },
          "probes": [
            {
              "name": "health",
              "url": "http://127.0.0.1:8080/health",
              "ok": true,
              "status_code": 200,
              "error": null,
              "auth_used": "anonymous",
              "body_excerpt": "{\"status\":\"ok\",\"environment\":\"docker-compose\"}"
            },
            {
              "name": "dashboard_stats",
              "url": "http://127.0.0.1:8080/api/dashboard/stats",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            },
            {
              "name": "tools_health",
              "url": "http://127.0.0.1:8080/api/tools/health?refresh=true",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            },
            {
              "name": "external_health",
              "url": "http://127.0.0.1:8080/api/external-connections/health",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            }
          ]
        },
        "snapshot_inventory": {
          "snapshot_root": "/Users/xiaoyuge/Documents/XXL/backend/data/release_snapshots",
          "total_snapshots": 1,
          "available_snapshots": [
            "20260414_031232"
          ],
          "selected_snapshot": "20260414_031232",
          "selected_exists": true,
          "selected_files": [
            "backend.env",
            "docker-compose.rendered.yml",
            "docker-compose.yml",
            "root.env"
          ]
        }
      }
    },
    "recovery": {
      "ok": true,
      "status": "passed",
      "scenario": "recovery",
      "checked_at": "2026-04-15T19:43:36+00:00",
      "checks": [
        {
          "key": "release_preflight_ready",
          "ok": true,
          "details": {
            "include_live_database": true
          }
        },
        {
          "key": "brain_runtime_ready",
          "ok": true,
          "details": {
            "require_production_ready": false,
            "startup_ready": true,
            "production_ready": false,
            "status": "degraded_startable"
          }
        },
        {
          "key": "runtime_endpoints_ready",
          "ok": true,
          "details": {
            "backend_base_url": "http://127.0.0.1:8080",
            "required_endpoints": [
              "health"
            ],
            "reachable_required_endpoints": 1
          }
        },
        {
          "key": "external_tentacle_recovered",
          "ok": true,
          "details": {
            "status": "passed",
            "failed_steps": []
          }
        },
        {
          "key": "memory_governance_stable",
          "ok": true,
          "details": {
            "status": null,
            "failed_steps": []
          }
        }
      ],
      "failed_steps": [],
      "components": {
        "persistence_contract": {
          "ok": false,
          "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
          "scheme": "postgresql+psycopg",
          "driver": "postgresql",
          "host": "localhost",
          "port": 5432,
          "is_sqlite": false,
          "is_localhost": true,
          "uses_default_url": true,
          "persistence_enabled": true,
          "probe_error": null,
          "warnings": [
            "database_url 仍为默认值。",
            "database_url 指向 localhost，本机真源不符合生产部署约束。"
          ]
        },
        "release_preflight": {
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
          }
        },
        "brain_prelaunch": {
          "ok": true,
          "startup_ready": true,
          "production_ready": false,
          "status": "degraded_startable",
          "checks": {
            "platform_readiness": {
              "captured_at": "2026-04-15T19:43:36+00:00",
              "environment": "docker-compose",
              "persistence_enabled": false,
              "nats_connected": true,
              "fallback_event_bus_available": true,
              "runbook_exists": true,
              "result_template_exists": true,
              "warnings": [
                "当前未连接正式持久层，真源校验将基于内存/降级模式。"
              ]
            },
            "persistence_contract": {
              "ok": false,
              "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
              "scheme": "postgresql+psycopg",
              "driver": "postgresql",
              "host": "localhost",
              "port": 5432,
              "is_sqlite": false,
              "is_localhost": true,
              "uses_default_url": true,
              "persistence_enabled": true,
              "probe_error": null,
              "warnings": [
                "database_url 仍为默认值。",
                "database_url 指向 localhost，本机真源不符合生产部署约束。"
              ]
            },
            "nats_contract": {
              "ok": false,
              "nats_url": "nats://localhost:4222",
              "scheme": "nats",
              "host": "localhost",
              "port": 4222,
              "uses_default_url": true,
              "is_localhost": true,
              "connected": true,
              "fallback_mode": false,
              "handler_registrations": 5,
              "subscription_registrations": 5,
              "last_error": null,
              "probe_error": null,
              "warnings": [
                "nats_url 仍为默认值。",
                "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
              ]
            },
            "scheduler_startup": {
              "ok": true,
              "checks": {
                "platform_readiness": {
                  "ok": true,
                  "summary": {
                    "captured_at": "2026-04-15T19:43:36+00:00",
                    "environment": "docker-compose",
                    "persistence_enabled": false,
                    "nats_connected": true,
                    "fallback_event_bus_available": true,
                    "runbook_exists": true,
                    "result_template_exists": true,
                    "warnings": [
                      "当前未连接正式持久层，真源校验将基于内存/降级模式。"
                    ],
                    "persistence_contract": {
                      "ok": false,
                      "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                      "scheme": "postgresql+psycopg",
                      "driver": "postgresql",
                      "host": "localhost",
                      "port": 5432,
                      "is_sqlite": false,
                      "is_localhost": true,
                      "uses_default_url": true,
                      "persistence_enabled": true,
                      "probe_error": null,
                      "warnings": [
                        "database_url 仍为默认值。",
                        "database_url 指向 localhost，本机真源不符合生产部署约束。"
                      ]
                    },
                    "nats_contract": {
                      "ok": false,
                      "nats_url": "nats://localhost:4222",
                      "scheme": "nats",
                      "host": "localhost",
                      "port": 4222,
                      "uses_default_url": true,
                      "is_localhost": true,
                      "connected": true,
                      "fallback_mode": false,
                      "handler_registrations": 5,
                      "subscription_registrations": 5,
                      "last_error": null,
                      "probe_error": null,
                      "warnings": [
                        "nats_url 仍为默认值。",
                        "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
                      ]
                    }
                  }
                },
                "dispatch_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_workflow_dispatch_jobs",
                      "release_workflow_dispatch_job_claim",
                      "list_workflow_dispatch_jobs",
                      "claim_due_workflow_runs",
                      "release_workflow_run_claim",
                      "list_workflow_runs"
                    ],
                    "missing": [],
                    "count": 6
                  }
                },
                "workflow_execution_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_workflow_execution_jobs",
                      "claim_workflow_execution_job",
                      "release_workflow_execution_job_claim",
                      "delete_workflow_execution_job",
                      "upsert_workflow_execution_job",
                      "list_workflow_execution_jobs",
                      "list_workflow_runs"
                    ],
                    "missing": [],
                    "count": 7
                  }
                },
                "agent_execution_runtime": {
                  "ok": true,
                  "mode": "persistent",
                  "warnings": [],
                  "methods": {
                    "available": [
                      "claim_due_agent_execution_jobs",
                      "claim_agent_execution_job",
                      "release_agent_execution_job_claim",
                      "delete_agent_execution_job",
                      "upsert_agent_execution_job",
                      "list_agent_execution_jobs",
                      "list_workflow_runs",
                      "list_tasks"
                    ],
                    "missing": [],
                    "count": 8
                  }
                },
                "guard_runtime": {
                  "ok": true,
                  "methods": {
                    "available": [
                      "guard_dispatch_runtime",
                      "guard_workflow_execution_runtime",
                      "guard_agent_execution_runtime"
                    ],
                    "missing": [],
                    "count": 3
                  }
                },
                "lease_window": {
                  "ok": true,
                  "summary": {
                    "dispatch_lease_seconds": 30.0,
                    "dispatch_poll_interval_seconds": 1.0,
                    "workflow_execution_lease_seconds": 45.0,
                    "workflow_execution_poll_interval_seconds": 1.0,
                    "workflow_execution_scan_limit": 50
                  }
                },
                "multi_instance_guard": {
                  "ok": true,
                  "mode": "enabled",
                  "summary": {
                    "persistence_enabled": true,
                    "strict_multi_instance_ready": true
                  },
                  "warnings": []
                }
              }
            },
            "scheduler_runtime_pg_acceptance": {
              "ok": false,
              "ran": false,
              "skipped": true,
              "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
              "skip_reason": "persistence_contract_not_ready"
            },
            "release_preflight": {
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
              }
            },
            "security_controls": {
              "ok": true,
              "checks": [
                {
                  "key": "allow_and_audit",
                  "ok": true,
                  "summary": {
                    "trace_id": "trace-474989148b02",
                    "audit_action": "安全网关放行"
                  }
                },
                {
                  "key": "redaction_and_audit",
                  "ok": true,
                  "summary": {
                    "audit_action": "安全网关改写放行",
                    "rewrite_rules": [
                      "pii_email",
                      "pii_phone",
                      "otp_code"
                    ]
                  }
                },
                {
                  "key": "prompt_injection_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "detail": "Prompt injection risk detected",
                    "audit_action": "安全网关拦截:prompt_injection"
                  }
                },
                {
                  "key": "auth_scope_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "detail": "Message ingest scope is not allowed",
                    "audit_action": "安全网关拦截:auth_rbac"
                  }
                },
                {
                  "key": "rate_limit_block",
                  "ok": true,
                  "summary": {
                    "status_code": 429,
                    "detail": "Rate limit exceeded for this user",
                    "audit_action": "安全网关拦截:rate_limit"
                  }
                },
                {
                  "key": "message_ingest_redaction_side_effects",
                  "ok": true,
                  "summary": {
                    "task_id": "7",
                    "audit_action": "安全网关改写放行",
                    "memory_total": 1
                  }
                },
                {
                  "key": "blocked_message_no_orchestration_side_effects",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "audit_action": "安全网关拦截:prompt_injection",
                    "task_total": 6,
                    "run_total": 0
                  }
                },
                {
                  "key": "message_ingest_auth_scope_route_block",
                  "ok": true,
                  "summary": {
                    "status_code": 403,
                    "audit_action": "安全网关拦截:auth_rbac"
                  }
                },
                {
                  "key": "message_ingest_rate_limit_route_block",
                  "ok": true,
                  "summary": {
                    "first_status": 200,
                    "second_status": 429,
                    "audit_action": "安全网关拦截:rate_limit"
                  }
                },
                {
                  "key": "workflow_webhook_block_no_orchestration_side_effects",
                  "ok": true,
                  "summary": {
                    "workflow_id": "workflow-2",
                    "status_code": 403,
                    "audit_action": "安全网关拦截:prompt_injection"
                  }
                }
              ],
              "summary": {
                "total_checks": 10,
                "failed_checks": 0
              }
            },
            "security_entrypoints": {
              "ok": true,
              "checks": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "ok": true,
                  "required_calls": [
                    "ingest_unified_message"
                  ],
                  "observed_calls": [
                    "Body",
                    "IngestMessageResponse",
                    "IngestUnifiedMessageRequest.model_validate",
                    "RequestValidationError",
                    "UnifiedMessage",
                    "exc.errors",
                    "ingest_unified_message",
                    "request_payload.model_dump",
                    "router.post",
                    "store.now_string"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "_ingest_channel_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "_validate_channel_secret",
                    "ingest_channel_webhook"
                  ],
                  "observed_calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_validate_channel_secret",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "ingest_channel_webhook",
                    "str"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "ingest_telegram_webhook"
                  ],
                  "observed_calls": [
                    "HTTPException",
                    "Header",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_telegram_webhook",
                    "payload.model_dump",
                    "router.post",
                    "str"
                  ],
                  "missing_calls": []
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "ok": true,
                  "required_calls": [
                    "enforce_webhook_rate_limit",
                    "enforce_webhook_payload_size",
                    "security_gateway_service.inspect_text_entrypoint",
                    "trigger_workflow_webhook"
                  ],
                  "observed_calls": [
                    "WorkflowActionResponse",
                    "_workflow_webhook_security_text",
                    "_workflow_webhook_user_key",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "router.post",
                    "security_gateway_service.inspect_text_entrypoint",
                    "trigger_workflow_webhook"
                  ],
                  "missing_calls": []
                }
              ],
              "summary": {
                "total_checks": 4,
                "failed_checks": 0
              }
            },
            "security_audit_persistence": {
              "ok": true,
              "checks": [
                {
                  "key": "security_gateway_emit_all_audit_actions",
                  "ok": true,
                  "summary": {
                    "allow_trace_id": "trace-2636f282129a",
                    "rewrite_diff_count": 3,
                    "block_status_code": 403,
                    "block_detail": "Prompt injection risk detected"
                  }
                },
                {
                  "key": "runtime_store_has_audits",
                  "ok": true,
                  "summary": {
                    "runtime_log_count": 7
                  }
                },
                {
                  "key": "audit_logs_persisted_to_truth_source",
                  "ok": true,
                  "summary": {
                    "database_log_count": 10,
                    "expected_actions": [
                      "安全网关拦截:prompt_injection",
                      "安全网关改写放行",
                      "安全网关放行"
                    ],
                    "observed_actions": [
                      "Token 超限",
                      "安全网关拦截:prompt_injection",
                      "安全网关改写放行",
                      "安全网关放行",
                      "工作流修改",
                      "异常请求",
                      "敏感词检测",
                      "权限变更",
                      "用户登录",
                      "登录失败"
                    ]
                  }
                },
                {
                  "key": "truth_source_survives_runtime_reset",
                  "ok": true,
                  "summary": {
                    "runtime_log_ids_count": 7,
                    "persisted_ids_count": 10,
                    "runtime_cleared": true
                  }
                },
                {
                  "key": "persisted_audit_metadata_integrity",
                  "ok": true,
                  "summary": {
                    "actions": [
                      {
                        "action": "安全网关拦截:prompt_injection",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": false
                        }
                      },
                      {
                        "action": "安全网关改写放行",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": true
                        }
                      },
                      {
                        "action": "安全网关放行",
                        "ok": true,
                        "summary": {
                          "has_trace_id": true,
                          "has_prompt_injection_assessment": true,
                          "has_rewrite_diffs": false
                        }
                      }
                    ]
                  }
                }
              ],
              "summary": {
                "database_path": "/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/security-audit-persistence-iqak63my/audit-persistence.db",
                "total_checks": 5,
                "failed_checks": 0
              }
            },
            "external_ingress_bypass": {
              "ok": true,
              "summary": {
                "total_routes": 29,
                "public_external_ingress_routes": 10,
                "authenticated_control_plane_routes": 19,
                "failed_public_routes": 0,
                "manual_review_required": 10
              },
              "routes": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "method": "post",
                  "path": "/ingest",
                  "calls": [
                    "Body",
                    "IngestMessageResponse",
                    "IngestUnifiedMessageRequest.model_validate",
                    "RequestValidationError",
                    "UnifiedMessage",
                    "exc.errors",
                    "ingest_unified_message",
                    "request_payload.model_dump",
                    "router.post",
                    "store.now_string"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "security_gateway"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [
                        "ingest_unified_message"
                      ],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "method": "post",
                  "path": "/telegram",
                  "calls": [
                    "HTTPException",
                    "Header",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_telegram_webhook",
                    "payload.model_dump",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "wecom_webhook_route",
                  "method": "post",
                  "path": "/wecom",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "feishu_webhook_route",
                  "method": "post",
                  "path": "/feishu",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "dingtalk_webhook_route",
                  "method": "post",
                  "path": "/dingtalk",
                  "calls": [
                    "HTTPException",
                    "IngestMessageResponse",
                    "_channel_enabled",
                    "_channel_secret_error_label",
                    "_configured_channel_secret",
                    "_ingest_channel_webhook_route",
                    "_validate_channel_secret",
                    "bool",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "get_channel_integration_runtime_settings",
                    "ingest_channel_webhook",
                    "provider.get",
                    "request.headers.get",
                    "request.query_params.get",
                    "router.post",
                    "str"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size"
                    ],
                    "missing": [
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_validate_channel_secret"
                      ],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "method": "post",
                  "path": "/workflows/{trigger_path:path}",
                  "calls": [
                    "WorkflowActionResponse",
                    "_workflow_webhook_security_text",
                    "_workflow_webhook_user_key",
                    "enforce_webhook_payload_size",
                    "enforce_webhook_rate_limit",
                    "forwarded_for.split",
                    "json.dumps",
                    "request.headers.get",
                    "router.post",
                    "sanitize_webhook_payload",
                    "security_gateway_service.inspect_text_entrypoint",
                    "str",
                    "str.strip",
                    "trigger_workflow_webhook"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [
                        "enforce_webhook_rate_limit"
                      ],
                      "payload_size": [
                        "enforce_webhook_payload_size"
                      ],
                      "security_gateway": [
                        "security_gateway_service.inspect_text_entrypoint"
                      ],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_agents_route",
                  "method": "get",
                  "path": "/agents",
                  "calls": [
                    "Agent",
                    "Depends",
                    "ExternalAgentListResponse",
                    "external_agent_registry_service.list_agents",
                    "len",
                    "require_permission",
                    "router.get"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_agent_versions_route",
                  "method": "get",
                  "path": "/agents/families/{family}/versions",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityVersionItem",
                    "ExternalCapabilityVersionListResponse",
                    "_agent_version_items",
                    "_rollback_policy",
                    "_rollout_policy",
                    "bool",
                    "external_agent_registry_service.list_versions",
                    "int",
                    "isinstance",
                    "item.get",
                    "len",
                    "list",
                    "raw.get",
                    "require_permission",
                    "router.get",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "list_external_skill_versions_route",
                  "method": "get",
                  "path": "/skills/families/{family}/versions",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityVersionItem",
                    "ExternalCapabilityVersionListResponse",
                    "_rollback_policy",
                    "_rollout_policy",
                    "_skill_version_items",
                    "bool",
                    "external_skill_registry_service.list_versions",
                    "int",
                    "isinstance",
                    "item.get",
                    "len",
                    "list",
                    "raw.get",
                    "require_permission",
                    "router.get",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "get_external_capability_health_route",
                  "method": "get",
                  "path": "/health",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityHealthItem",
                    "ExternalCapabilityHealthResponse",
                    "_health_items",
                    "bool",
                    "dict",
                    "external_agent_registry_service.list_agents",
                    "external_agent_registry_service.prune_expired",
                    "external_skill_registry_service.list_skills",
                    "external_skill_registry_service.prune_expired",
                    "int",
                    "item.get",
                    "items.append",
                    "items.sort",
                    "len",
                    "list",
                    "require_permission",
                    "router.get",
                    "str"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "get_external_capability_governance_route",
                  "method": "get",
                  "path": "/governance",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityGovernanceFamilySummary",
                    "ExternalCapabilityGovernanceOverviewResponse",
                    "ExternalCapabilityGovernanceSummary",
                    "Header",
                    "Query",
                    "ValueError",
                    "_agent_governance_summary",
                    "_governance_items",
                    "_pick_family_primary_item",
                    "_rollback_policy",
                    "_rollout_policy",
                    "_skill_governance_summary",
                    "bool",
                    "config_summary.get",
                    "default_item.get",
                    "dict",
                    "external_agent_registry_service.list_agents",
                    "external_agent_registry_service.list_versions",
                    "external_agent_registry_service.prune_expired",
                    "external_skill_registry_service.list_skills",
                    "external_skill_registry_service.list_versions",
                    "external_skill_registry_service.prune_expired",
                    "get_audit_logs",
                    "int",
                    "isinstance",
                    "item.get",
                    "items.append",
                    "items.sort",
                    "len",
                    "list",
                    "next",
                    "primary.get",
                    "raw.get",
                    "require_permission",
                    "resolve_scope",
                    "router.get",
                    "sorted",
                    "str",
                    "str.strip",
                    "sum"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_agent_route",
                  "method": "post",
                  "path": "/agents/register",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_agent_registry_service.register_agent",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_skill_route",
                  "method": "post",
                  "path": "/skills/register",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_skill_registry_service.register_skill",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_agent_heartbeat_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/heartbeat",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_agent_registry_service.report_heartbeat",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_skill_heartbeat_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/heartbeat",
                  "calls": [
                    "ExternalCapabilityActionResponse",
                    "Header",
                    "_request_payload",
                    "_require_external_auth",
                    "dict",
                    "external_skill_registry_service.report_heartbeat",
                    "isinstance",
                    "payload.model_dump",
                    "request.json",
                    "router.post",
                    "verify_external_request"
                  ],
                  "dependencies": [],
                  "route_type": "public_external_ingress",
                  "protection_summary": {
                    "matched": [
                      "secret_or_signature"
                    ],
                    "missing": [
                      "rate_limit",
                      "payload_size",
                      "security_gateway",
                      "authenticated_user"
                    ],
                    "matched_details": {
                      "secret_or_signature": [
                        "_require_external_auth",
                        "verify_external_request"
                      ],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": []
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "report_external_agent_failure_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/failures",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.report_failure",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "report_external_skill_failure_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/failures",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.report_failure",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "recover_external_agent_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/recover",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.recover_agent",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "recover_external_skill_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/recover",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.recover_skill",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "promote_external_agent_version_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/promote",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.promote_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "promote_external_skill_version_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/promote",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.promote_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_fallback_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/set-fallback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.set_fallback_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_fallback_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/set-fallback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.set_fallback_version",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_rollout_policy_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/rollout-policy",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollout_policy",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_agent_registry_service.set_rollout_policy",
                    "int",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_rollout_policy_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/rollout-policy",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollout_policy",
                    "append_control_plane_audit_log",
                    "current_user.get",
                    "external_skill_registry_service.set_rollout_policy",
                    "int",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_rollback_policy_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/rollback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollback_policy",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.set_rollback_policy",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_rollback_policy_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/rollback",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "_rollback_policy",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.set_rollback_policy",
                    "isinstance",
                    "item.get",
                    "raw.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_agent_deprecated_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/deprecate",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_agent_registry_service.set_deprecated",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "set_external_skill_deprecated_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/deprecate",
                  "calls": [
                    "Depends",
                    "ExternalCapabilityActionResponse",
                    "HTTPException",
                    "_operator_identity",
                    "append_control_plane_audit_log",
                    "bool",
                    "current_user.get",
                    "external_skill_registry_service.set_deprecated",
                    "item.get",
                    "require_permission",
                    "router.post",
                    "str",
                    "str.strip"
                  ],
                  "dependencies": [
                    "require_authenticated_user",
                    "require_permission"
                  ],
                  "route_type": "authenticated_control_plane",
                  "protection_summary": {
                    "matched": [
                      "authenticated_user"
                    ],
                    "missing": [
                      "secret_or_signature",
                      "rate_limit",
                      "payload_size",
                      "security_gateway"
                    ],
                    "matched_details": {
                      "secret_or_signature": [],
                      "rate_limit": [],
                      "payload_size": [],
                      "security_gateway": [],
                      "authenticated_user": [
                        "require_authenticated_user"
                      ]
                    },
                    "is_protected": true
                  }
                }
              ],
              "failed_public_routes": [],
              "manual_review_required": [
                {
                  "file": "backend/app/api/routes/messages.py",
                  "function": "ingest_message_route",
                  "method": "post",
                  "path": "/ingest",
                  "matched_protections": [
                    "security_gateway"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "telegram_webhook_route",
                  "method": "post",
                  "path": "/telegram",
                  "matched_protections": [
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "wecom_webhook_route",
                  "method": "post",
                  "path": "/wecom",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "feishu_webhook_route",
                  "method": "post",
                  "path": "/feishu",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "dingtalk_webhook_route",
                  "method": "post",
                  "path": "/dingtalk",
                  "matched_protections": [
                    "secret_or_signature",
                    "rate_limit",
                    "payload_size"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/webhooks.py",
                  "function": "workflow_webhook_route",
                  "method": "post",
                  "path": "/workflows/{trigger_path:path}",
                  "matched_protections": [
                    "rate_limit",
                    "payload_size",
                    "security_gateway"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_agent_route",
                  "method": "post",
                  "path": "/agents/register",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "register_external_skill_route",
                  "method": "post",
                  "path": "/skills/register",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_agent_heartbeat_route",
                  "method": "post",
                  "path": "/agents/{agent_id}/heartbeat",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                },
                {
                  "file": "backend/app/api/routes/external_connections.py",
                  "function": "external_skill_heartbeat_route",
                  "method": "post",
                  "path": "/skills/{skill_id}/heartbeat",
                  "matched_protections": [
                    "secret_or_signature"
                  ],
                  "reason": "static_check_only_needs_runtime_verification"
                }
              ]
            },
            "dr_result_gate": {
              "ok": true,
              "status": "passed",
              "checks": [
                {
                  "key": "required_reports_present",
                  "ok": true,
                  "details": {
                    "expected": [
                      "precheck",
                      "prepare",
                      "post_verify",
                      "recovery"
                    ],
                    "missing": {},
                    "resolved": {
                      "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                      "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                      "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                      "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                    }
                  }
                },
                {
                  "key": "rto_rpo_fields_present",
                  "ok": true,
                  "details": {
                    "required_fields": [
                      "measurements.rto_seconds",
                      "measurements.estimated_rpo_seconds"
                    ],
                    "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
                  }
                },
                {
                  "key": "failed_manual_intervention_stats_present",
                  "ok": true,
                  "details": {
                    "required_fields": [
                      "gate_stats.failed",
                      "gate_stats.manual_intervention"
                    ]
                  }
                },
                {
                  "key": "formal_drill_kind_required",
                  "ok": true,
                  "details": {
                    "allow_smoke": false,
                    "required_kind": "formal",
                    "report_drill_kinds": {
                      "precheck": "formal",
                      "prepare": "formal",
                      "post_verify": "formal",
                      "recovery": "formal"
                    },
                    "non_formal_reports": {}
                  }
                }
              ],
              "failed_steps": [],
              "reports": {
                "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
              },
              "missing_reports": {},
              "allow_smoke": false,
              "report_drill_kinds": {
                "precheck": "formal",
                "prepare": "formal",
                "post_verify": "formal",
                "recovery": "formal"
              },
              "gate_stats": {
                "failed": 0,
                "manual_intervention": 10
              }
            },
            "nats_roundtrip": {
              "ok": false,
              "ran": false,
              "skipped": true,
              "nats_url": "nats://localhost:4222",
              "skip_reason": "nats_contract_not_ready"
            },
            "nats_transport": {
              "nats_url": "nats://localhost:4222",
              "connected": true,
              "connect_attempted": true,
              "loop_ready": true,
              "handler_registrations": 5,
              "subscription_registrations": 5,
              "retry_interval_seconds": 30.0,
              "operation_timeout_seconds": 1.5,
              "fallback_mode": false,
              "warning_emitted": false,
              "last_error": null
            },
            "strict_gates": [
              {
                "key": "persistent_truth_source_ready",
                "ok": false,
                "summary": {
                  "persistence_enabled": false,
                  "contract": {
                    "ok": false,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "scheme": "postgresql+psycopg",
                    "driver": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "is_sqlite": false,
                    "is_localhost": true,
                    "uses_default_url": true,
                    "persistence_enabled": true,
                    "probe_error": null,
                    "warnings": [
                      "database_url 仍为默认值。",
                      "database_url 指向 localhost，本机真源不符合生产部署约束。"
                    ]
                  }
                }
              },
              {
                "key": "nats_transport_ready",
                "ok": false,
                "summary": {
                  "nats_connected": true,
                  "fallback_event_bus_available": true,
                  "transport": {
                    "nats_url": "nats://localhost:4222",
                    "connected": true,
                    "connect_attempted": true,
                    "loop_ready": true,
                    "handler_registrations": 5,
                    "subscription_registrations": 5,
                    "retry_interval_seconds": 30.0,
                    "operation_timeout_seconds": 1.5,
                    "fallback_mode": false,
                    "warning_emitted": false,
                    "last_error": null
                  },
                  "contract": {
                    "ok": false,
                    "nats_url": "nats://localhost:4222",
                    "scheme": "nats",
                    "host": "localhost",
                    "port": 4222,
                    "uses_default_url": true,
                    "is_localhost": true,
                    "connected": true,
                    "fallback_mode": false,
                    "handler_registrations": 5,
                    "subscription_registrations": 5,
                    "last_error": null,
                    "probe_error": null,
                    "warnings": [
                      "nats_url 仍为默认值。",
                      "nats_url 指向 localhost，本机 NATS 不符合生产部署约束。"
                    ]
                  },
                  "roundtrip": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "nats_url": "nats://localhost:4222",
                    "skip_reason": "nats_contract_not_ready"
                  }
                }
              },
              {
                "key": "scheduler_multi_instance_ready",
                "ok": true,
                "summary": {
                  "multi_instance_guard": {
                    "ok": true,
                    "mode": "enabled",
                    "summary": {
                      "persistence_enabled": true,
                      "strict_multi_instance_ready": true
                    },
                    "warnings": []
                  },
                  "pg_acceptance": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "skip_reason": "persistence_contract_not_ready"
                  }
                }
              },
              {
                "key": "scheduler_runtime_persistent",
                "ok": true,
                "summary": {
                  "dispatch_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_workflow_dispatch_jobs",
                        "release_workflow_dispatch_job_claim",
                        "list_workflow_dispatch_jobs",
                        "claim_due_workflow_runs",
                        "release_workflow_run_claim",
                        "list_workflow_runs"
                      ],
                      "missing": [],
                      "count": 6
                    }
                  },
                  "workflow_execution_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_workflow_execution_jobs",
                        "claim_workflow_execution_job",
                        "release_workflow_execution_job_claim",
                        "delete_workflow_execution_job",
                        "upsert_workflow_execution_job",
                        "list_workflow_execution_jobs",
                        "list_workflow_runs"
                      ],
                      "missing": [],
                      "count": 7
                    }
                  },
                  "agent_execution_runtime": {
                    "ok": true,
                    "mode": "persistent",
                    "warnings": [],
                    "methods": {
                      "available": [
                        "claim_due_agent_execution_jobs",
                        "claim_agent_execution_job",
                        "release_agent_execution_job_claim",
                        "delete_agent_execution_job",
                        "upsert_agent_execution_job",
                        "list_agent_execution_jobs",
                        "list_workflow_runs",
                        "list_tasks"
                      ],
                      "missing": [],
                      "count": 8
                    }
                  },
                  "pg_acceptance": {
                    "ok": false,
                    "ran": false,
                    "skipped": true,
                    "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
                    "skip_reason": "persistence_contract_not_ready"
                  }
                }
              },
              {
                "key": "security_entrypoint_coverage",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "ok": true,
                      "required_calls": [
                        "ingest_unified_message"
                      ],
                      "observed_calls": [
                        "Body",
                        "IngestMessageResponse",
                        "IngestUnifiedMessageRequest.model_validate",
                        "RequestValidationError",
                        "UnifiedMessage",
                        "exc.errors",
                        "ingest_unified_message",
                        "request_payload.model_dump",
                        "router.post",
                        "store.now_string"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "_ingest_channel_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "_validate_channel_secret",
                        "ingest_channel_webhook"
                      ],
                      "observed_calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_validate_channel_secret",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "ingest_channel_webhook",
                        "str"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "ingest_telegram_webhook"
                      ],
                      "observed_calls": [
                        "HTTPException",
                        "Header",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_telegram_webhook",
                        "payload.model_dump",
                        "router.post",
                        "str"
                      ],
                      "missing_calls": []
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "ok": true,
                      "required_calls": [
                        "enforce_webhook_rate_limit",
                        "enforce_webhook_payload_size",
                        "security_gateway_service.inspect_text_entrypoint",
                        "trigger_workflow_webhook"
                      ],
                      "observed_calls": [
                        "WorkflowActionResponse",
                        "_workflow_webhook_security_text",
                        "_workflow_webhook_user_key",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "router.post",
                        "security_gateway_service.inspect_text_entrypoint",
                        "trigger_workflow_webhook"
                      ],
                      "missing_calls": []
                    }
                  ],
                  "summary": {
                    "total_checks": 4,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "security_controls_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "key": "allow_and_audit",
                      "ok": true,
                      "summary": {
                        "trace_id": "trace-474989148b02",
                        "audit_action": "安全网关放行"
                      }
                    },
                    {
                      "key": "redaction_and_audit",
                      "ok": true,
                      "summary": {
                        "audit_action": "安全网关改写放行",
                        "rewrite_rules": [
                          "pii_email",
                          "pii_phone",
                          "otp_code"
                        ]
                      }
                    },
                    {
                      "key": "prompt_injection_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "detail": "Prompt injection risk detected",
                        "audit_action": "安全网关拦截:prompt_injection"
                      }
                    },
                    {
                      "key": "auth_scope_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "detail": "Message ingest scope is not allowed",
                        "audit_action": "安全网关拦截:auth_rbac"
                      }
                    },
                    {
                      "key": "rate_limit_block",
                      "ok": true,
                      "summary": {
                        "status_code": 429,
                        "detail": "Rate limit exceeded for this user",
                        "audit_action": "安全网关拦截:rate_limit"
                      }
                    },
                    {
                      "key": "message_ingest_redaction_side_effects",
                      "ok": true,
                      "summary": {
                        "task_id": "7",
                        "audit_action": "安全网关改写放行",
                        "memory_total": 1
                      }
                    },
                    {
                      "key": "blocked_message_no_orchestration_side_effects",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "audit_action": "安全网关拦截:prompt_injection",
                        "task_total": 6,
                        "run_total": 0
                      }
                    },
                    {
                      "key": "message_ingest_auth_scope_route_block",
                      "ok": true,
                      "summary": {
                        "status_code": 403,
                        "audit_action": "安全网关拦截:auth_rbac"
                      }
                    },
                    {
                      "key": "message_ingest_rate_limit_route_block",
                      "ok": true,
                      "summary": {
                        "first_status": 200,
                        "second_status": 429,
                        "audit_action": "安全网关拦截:rate_limit"
                      }
                    },
                    {
                      "key": "workflow_webhook_block_no_orchestration_side_effects",
                      "ok": true,
                      "summary": {
                        "workflow_id": "workflow-2",
                        "status_code": 403,
                        "audit_action": "安全网关拦截:prompt_injection"
                      }
                    }
                  ],
                  "summary": {
                    "total_checks": 10,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "security_audit_persistence_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "checks": [
                    {
                      "key": "security_gateway_emit_all_audit_actions",
                      "ok": true,
                      "summary": {
                        "allow_trace_id": "trace-2636f282129a",
                        "rewrite_diff_count": 3,
                        "block_status_code": 403,
                        "block_detail": "Prompt injection risk detected"
                      }
                    },
                    {
                      "key": "runtime_store_has_audits",
                      "ok": true,
                      "summary": {
                        "runtime_log_count": 7
                      }
                    },
                    {
                      "key": "audit_logs_persisted_to_truth_source",
                      "ok": true,
                      "summary": {
                        "database_log_count": 10,
                        "expected_actions": [
                          "安全网关拦截:prompt_injection",
                          "安全网关改写放行",
                          "安全网关放行"
                        ],
                        "observed_actions": [
                          "Token 超限",
                          "安全网关拦截:prompt_injection",
                          "安全网关改写放行",
                          "安全网关放行",
                          "工作流修改",
                          "异常请求",
                          "敏感词检测",
                          "权限变更",
                          "用户登录",
                          "登录失败"
                        ]
                      }
                    },
                    {
                      "key": "truth_source_survives_runtime_reset",
                      "ok": true,
                      "summary": {
                        "runtime_log_ids_count": 7,
                        "persisted_ids_count": 10,
                        "runtime_cleared": true
                      }
                    },
                    {
                      "key": "persisted_audit_metadata_integrity",
                      "ok": true,
                      "summary": {
                        "actions": [
                          {
                            "action": "安全网关拦截:prompt_injection",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": false
                            }
                          },
                          {
                            "action": "安全网关改写放行",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": true
                            }
                          },
                          {
                            "action": "安全网关放行",
                            "ok": true,
                            "summary": {
                              "has_trace_id": true,
                              "has_prompt_injection_assessment": true,
                              "has_rewrite_diffs": false
                            }
                          }
                        ]
                      }
                    }
                  ],
                  "summary": {
                    "database_path": "/var/folders/m3/qhkxdt1d3hldmhbjskg7cp5w0000gn/T/security-audit-persistence-iqak63my/audit-persistence.db",
                    "total_checks": 5,
                    "failed_checks": 0
                  }
                }
              },
              {
                "key": "external_ingress_bypass_scan_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "summary": {
                    "total_routes": 29,
                    "public_external_ingress_routes": 10,
                    "authenticated_control_plane_routes": 19,
                    "failed_public_routes": 0,
                    "manual_review_required": 10
                  },
                  "routes": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "method": "post",
                      "path": "/ingest",
                      "calls": [
                        "Body",
                        "IngestMessageResponse",
                        "IngestUnifiedMessageRequest.model_validate",
                        "RequestValidationError",
                        "UnifiedMessage",
                        "exc.errors",
                        "ingest_unified_message",
                        "request_payload.model_dump",
                        "router.post",
                        "store.now_string"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "security_gateway"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [
                            "ingest_unified_message"
                          ],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "method": "post",
                      "path": "/telegram",
                      "calls": [
                        "HTTPException",
                        "Header",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_telegram_webhook",
                        "payload.model_dump",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "wecom_webhook_route",
                      "method": "post",
                      "path": "/wecom",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "feishu_webhook_route",
                      "method": "post",
                      "path": "/feishu",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "dingtalk_webhook_route",
                      "method": "post",
                      "path": "/dingtalk",
                      "calls": [
                        "HTTPException",
                        "IngestMessageResponse",
                        "_channel_enabled",
                        "_channel_secret_error_label",
                        "_configured_channel_secret",
                        "_ingest_channel_webhook_route",
                        "_validate_channel_secret",
                        "bool",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "get_channel_integration_runtime_settings",
                        "ingest_channel_webhook",
                        "provider.get",
                        "request.headers.get",
                        "request.query_params.get",
                        "router.post",
                        "str"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size"
                        ],
                        "missing": [
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_validate_channel_secret"
                          ],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "method": "post",
                      "path": "/workflows/{trigger_path:path}",
                      "calls": [
                        "WorkflowActionResponse",
                        "_workflow_webhook_security_text",
                        "_workflow_webhook_user_key",
                        "enforce_webhook_payload_size",
                        "enforce_webhook_rate_limit",
                        "forwarded_for.split",
                        "json.dumps",
                        "request.headers.get",
                        "router.post",
                        "sanitize_webhook_payload",
                        "security_gateway_service.inspect_text_entrypoint",
                        "str",
                        "str.strip",
                        "trigger_workflow_webhook"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [
                            "enforce_webhook_rate_limit"
                          ],
                          "payload_size": [
                            "enforce_webhook_payload_size"
                          ],
                          "security_gateway": [
                            "security_gateway_service.inspect_text_entrypoint"
                          ],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_agents_route",
                      "method": "get",
                      "path": "/agents",
                      "calls": [
                        "Agent",
                        "Depends",
                        "ExternalAgentListResponse",
                        "external_agent_registry_service.list_agents",
                        "len",
                        "require_permission",
                        "router.get"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_agent_versions_route",
                      "method": "get",
                      "path": "/agents/families/{family}/versions",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityVersionItem",
                        "ExternalCapabilityVersionListResponse",
                        "_agent_version_items",
                        "_rollback_policy",
                        "_rollout_policy",
                        "bool",
                        "external_agent_registry_service.list_versions",
                        "int",
                        "isinstance",
                        "item.get",
                        "len",
                        "list",
                        "raw.get",
                        "require_permission",
                        "router.get",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "list_external_skill_versions_route",
                      "method": "get",
                      "path": "/skills/families/{family}/versions",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityVersionItem",
                        "ExternalCapabilityVersionListResponse",
                        "_rollback_policy",
                        "_rollout_policy",
                        "_skill_version_items",
                        "bool",
                        "external_skill_registry_service.list_versions",
                        "int",
                        "isinstance",
                        "item.get",
                        "len",
                        "list",
                        "raw.get",
                        "require_permission",
                        "router.get",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "get_external_capability_health_route",
                      "method": "get",
                      "path": "/health",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityHealthItem",
                        "ExternalCapabilityHealthResponse",
                        "_health_items",
                        "bool",
                        "dict",
                        "external_agent_registry_service.list_agents",
                        "external_agent_registry_service.prune_expired",
                        "external_skill_registry_service.list_skills",
                        "external_skill_registry_service.prune_expired",
                        "int",
                        "item.get",
                        "items.append",
                        "items.sort",
                        "len",
                        "list",
                        "require_permission",
                        "router.get",
                        "str"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "get_external_capability_governance_route",
                      "method": "get",
                      "path": "/governance",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityGovernanceFamilySummary",
                        "ExternalCapabilityGovernanceOverviewResponse",
                        "ExternalCapabilityGovernanceSummary",
                        "Header",
                        "Query",
                        "ValueError",
                        "_agent_governance_summary",
                        "_governance_items",
                        "_pick_family_primary_item",
                        "_rollback_policy",
                        "_rollout_policy",
                        "_skill_governance_summary",
                        "bool",
                        "config_summary.get",
                        "default_item.get",
                        "dict",
                        "external_agent_registry_service.list_agents",
                        "external_agent_registry_service.list_versions",
                        "external_agent_registry_service.prune_expired",
                        "external_skill_registry_service.list_skills",
                        "external_skill_registry_service.list_versions",
                        "external_skill_registry_service.prune_expired",
                        "get_audit_logs",
                        "int",
                        "isinstance",
                        "item.get",
                        "items.append",
                        "items.sort",
                        "len",
                        "list",
                        "next",
                        "primary.get",
                        "raw.get",
                        "require_permission",
                        "resolve_scope",
                        "router.get",
                        "sorted",
                        "str",
                        "str.strip",
                        "sum"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_agent_route",
                      "method": "post",
                      "path": "/agents/register",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_agent_registry_service.register_agent",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_skill_route",
                      "method": "post",
                      "path": "/skills/register",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_skill_registry_service.register_skill",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_agent_heartbeat_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/heartbeat",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_agent_registry_service.report_heartbeat",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_skill_heartbeat_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/heartbeat",
                      "calls": [
                        "ExternalCapabilityActionResponse",
                        "Header",
                        "_request_payload",
                        "_require_external_auth",
                        "dict",
                        "external_skill_registry_service.report_heartbeat",
                        "isinstance",
                        "payload.model_dump",
                        "request.json",
                        "router.post",
                        "verify_external_request"
                      ],
                      "dependencies": [],
                      "route_type": "public_external_ingress",
                      "protection_summary": {
                        "matched": [
                          "secret_or_signature"
                        ],
                        "missing": [
                          "rate_limit",
                          "payload_size",
                          "security_gateway",
                          "authenticated_user"
                        ],
                        "matched_details": {
                          "secret_or_signature": [
                            "_require_external_auth",
                            "verify_external_request"
                          ],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": []
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "report_external_agent_failure_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/failures",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.report_failure",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "report_external_skill_failure_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/failures",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.report_failure",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "recover_external_agent_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/recover",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.recover_agent",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "recover_external_skill_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/recover",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.recover_skill",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "promote_external_agent_version_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/promote",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.promote_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "promote_external_skill_version_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/promote",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.promote_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_fallback_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/set-fallback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.set_fallback_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_fallback_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/set-fallback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.set_fallback_version",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_rollout_policy_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/rollout-policy",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollout_policy",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_agent_registry_service.set_rollout_policy",
                        "int",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_rollout_policy_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/rollout-policy",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollout_policy",
                        "append_control_plane_audit_log",
                        "current_user.get",
                        "external_skill_registry_service.set_rollout_policy",
                        "int",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_rollback_policy_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/rollback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollback_policy",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.set_rollback_policy",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_rollback_policy_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/rollback",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "_rollback_policy",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.set_rollback_policy",
                        "isinstance",
                        "item.get",
                        "raw.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_agent_deprecated_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/deprecate",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_agent_registry_service.set_deprecated",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "set_external_skill_deprecated_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/deprecate",
                      "calls": [
                        "Depends",
                        "ExternalCapabilityActionResponse",
                        "HTTPException",
                        "_operator_identity",
                        "append_control_plane_audit_log",
                        "bool",
                        "current_user.get",
                        "external_skill_registry_service.set_deprecated",
                        "item.get",
                        "require_permission",
                        "router.post",
                        "str",
                        "str.strip"
                      ],
                      "dependencies": [
                        "require_authenticated_user",
                        "require_permission"
                      ],
                      "route_type": "authenticated_control_plane",
                      "protection_summary": {
                        "matched": [
                          "authenticated_user"
                        ],
                        "missing": [
                          "secret_or_signature",
                          "rate_limit",
                          "payload_size",
                          "security_gateway"
                        ],
                        "matched_details": {
                          "secret_or_signature": [],
                          "rate_limit": [],
                          "payload_size": [],
                          "security_gateway": [],
                          "authenticated_user": [
                            "require_authenticated_user"
                          ]
                        },
                        "is_protected": true
                      }
                    }
                  ],
                  "failed_public_routes": [],
                  "manual_review_required": [
                    {
                      "file": "backend/app/api/routes/messages.py",
                      "function": "ingest_message_route",
                      "method": "post",
                      "path": "/ingest",
                      "matched_protections": [
                        "security_gateway"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "telegram_webhook_route",
                      "method": "post",
                      "path": "/telegram",
                      "matched_protections": [
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "wecom_webhook_route",
                      "method": "post",
                      "path": "/wecom",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "feishu_webhook_route",
                      "method": "post",
                      "path": "/feishu",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "dingtalk_webhook_route",
                      "method": "post",
                      "path": "/dingtalk",
                      "matched_protections": [
                        "secret_or_signature",
                        "rate_limit",
                        "payload_size"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/webhooks.py",
                      "function": "workflow_webhook_route",
                      "method": "post",
                      "path": "/workflows/{trigger_path:path}",
                      "matched_protections": [
                        "rate_limit",
                        "payload_size",
                        "security_gateway"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_agent_route",
                      "method": "post",
                      "path": "/agents/register",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "register_external_skill_route",
                      "method": "post",
                      "path": "/skills/register",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_agent_heartbeat_route",
                      "method": "post",
                      "path": "/agents/{agent_id}/heartbeat",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    },
                    {
                      "file": "backend/app/api/routes/external_connections.py",
                      "function": "external_skill_heartbeat_route",
                      "method": "post",
                      "path": "/skills/{skill_id}/heartbeat",
                      "matched_protections": [
                        "secret_or_signature"
                      ],
                      "reason": "static_check_only_needs_runtime_verification"
                    }
                  ]
                }
              },
              {
                "key": "dr_result_gate_ready",
                "ok": true,
                "summary": {
                  "ok": true,
                  "status": "passed",
                  "checks": [
                    {
                      "key": "required_reports_present",
                      "ok": true,
                      "details": {
                        "expected": [
                          "precheck",
                          "prepare",
                          "post_verify",
                          "recovery"
                        ],
                        "missing": {},
                        "resolved": {
                          "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                          "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                          "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                          "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                        }
                      }
                    },
                    {
                      "key": "rto_rpo_fields_present",
                      "ok": true,
                      "details": {
                        "required_fields": [
                          "measurements.rto_seconds",
                          "measurements.estimated_rpo_seconds"
                        ],
                        "post_verify_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json"
                      }
                    },
                    {
                      "key": "failed_manual_intervention_stats_present",
                      "ok": true,
                      "details": {
                        "required_fields": [
                          "gate_stats.failed",
                          "gate_stats.manual_intervention"
                        ]
                      }
                    },
                    {
                      "key": "formal_drill_kind_required",
                      "ok": true,
                      "details": {
                        "allow_smoke": false,
                        "required_kind": "formal",
                        "report_drill_kinds": {
                          "precheck": "formal",
                          "prepare": "formal",
                          "post_verify": "formal",
                          "recovery": "formal"
                        },
                        "non_formal_reports": {}
                      }
                    }
                  ],
                  "failed_steps": [],
                  "reports": {
                    "precheck": "/Users/xiaoyuge/Documents/XXL/backend/docs/dr_precheck_20260415_052850.json",
                    "prepare": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json",
                    "post_verify": "/Users/xiaoyuge/Documents/XXL/backend/docs/post_failover_verify_20260415_052850.json",
                    "recovery": "/Users/xiaoyuge/Documents/XXL/backend/docs/external_tentacle_recovery_20260415_052850.json"
                  },
                  "missing_reports": {},
                  "allow_smoke": false,
                  "report_drill_kinds": {
                    "precheck": "formal",
                    "prepare": "formal",
                    "post_verify": "formal",
                    "recovery": "formal"
                  },
                  "gate_stats": {
                    "failed": 0,
                    "manual_intervention": 10
                  }
                }
              },
              {
                "key": "release_preflight_green",
                "ok": true,
                "summary": {
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
                  }
                }
              },
              {
                "key": "runbook_and_result_template_ready",
                "ok": true,
                "summary": {
                  "runbook_exists": true,
                  "result_template_exists": true
                }
              }
            ]
          },
          "strict_blockers": [
            "未接入正式数据库真源，当前仍处于 fallback/degraded 启动模式。",
            "NATS 未建立正式连接，或真实 roundtrip/queue-group 验收未通过。"
          ],
          "summary": {
            "degraded_startable": true,
            "strict_gate_count": 11,
            "strict_passed": 9,
            "strict_failed": 2,
            "strict_failed_keys": [
              "persistent_truth_source_ready",
              "nats_transport_ready"
            ]
          }
        },
        "runtime_endpoints": {
          "ok": true,
          "status": "passed",
          "checked_at": "2026-04-15T19:43:36+00:00",
          "checks": [
            {
              "key": "health_endpoint_reachable",
              "ok": true,
              "details": {
                "status_code": 200
              }
            },
            {
              "key": "control_plane_auth_available",
              "ok": true,
              "details": {
                "require_control_plane": false,
                "used_access_token": false
              }
            },
            {
              "key": "required_runtime_endpoints_reachable",
              "ok": true,
              "details": {
                "required": [
                  "health"
                ],
                "failed_required": []
              }
            }
          ],
          "failed_steps": [],
          "auth": {
            "used_access_token": false,
            "login": null,
            "require_control_plane": false
          },
          "summary": {
            "backend_base_url": "http://127.0.0.1:8080",
            "required_endpoints": [
              "health"
            ],
            "reachable_required_endpoints": 1
          },
          "probes": [
            {
              "name": "health",
              "url": "http://127.0.0.1:8080/health",
              "ok": true,
              "status_code": 200,
              "error": null,
              "auth_used": "anonymous",
              "body_excerpt": "{\"status\":\"ok\",\"environment\":\"docker-compose\"}"
            },
            {
              "name": "dashboard_stats",
              "url": "http://127.0.0.1:8080/api/dashboard/stats",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            },
            {
              "name": "tools_health",
              "url": "http://127.0.0.1:8080/api/tools/health?refresh=true",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            },
            {
              "name": "external_health",
              "url": "http://127.0.0.1:8080/api/external-connections/health",
              "ok": false,
              "status_code": 401,
              "error": "HTTPError: Unauthorized",
              "auth_used": "anonymous",
              "body_excerpt": "{\"detail\":\"Missing bearer token\"}"
            }
          ]
        },
        "external_tentacle_recovery": {
          "drill_name": "brain_failover_drill",
          "scenario": "level2_brain_failover",
          "generated_at": "2026-04-15T19:43:36+00:00",
          "objectives": {
            "brain_api_failover_rto_seconds": 300,
            "external_reregistration_rto_seconds": 600,
            "observability_restore_rto_seconds": 600,
            "truth_source_rpo_seconds": 60,
            "audit_rpo_seconds": 0
          },
          "timeline": {
            "failover_started_at": "2026-04-15T05:28:50+00:00",
            "verified_at": "2026-04-15T19:43:36+00:00"
          },
          "baseline": {
            "truth_sources": {
              "captured_at": "2026-04-15T05:28:50+00:00",
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
            },
            "external_manifest": {
              "captured_at": "2026-04-15T05:28:50+00:00",
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
          },
          "post_state": {
            "truth_sources": {},
            "external_manifest": {
              "captured_at": "2026-04-15T19:43:36+00:00",
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
          },
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
          "evidence": {
            "drill_kind": "formal",
            "evidence_level": "full",
            "operator_notes": ""
          },
          "measurements": {
            "rto_seconds": null,
            "external_recovery_rto_seconds": 51286.0,
            "estimated_rpo_seconds": null,
            "estimated_lost_records": 0
          },
          "status": "passed",
          "tentacle_recovery_scope": {
            "agent": true,
            "skill": true,
            "mcp": false
          },
          "ok": true,
          "gate_stats": {
            "failed": 0,
            "manual_intervention": 0
          },
          "baseline_report": "/Users/xiaoyuge/Documents/XXL/backend/docs/failover_prepare_20260415_052850.json"
        },
        "memory_governance": {
          "ok": true,
          "checks": {
            "long_term_whitelist_defined": {
              "ok": true,
              "memory_types": [
                "agent_decision",
                "event_digest",
                "session_summary",
                "task_result",
                "user_preference"
              ]
            },
            "external_long_term_write_blocked": {
              "ok": true
            },
            "local_only_filtering_active": {
              "ok": true,
              "filtered_count": 1,
              "filtered_reasons": [
                "debug_log_fragment"
              ]
            },
            "tenant_scope_isolation": {
              "ok": true,
              "cross_scope_total": 0
            },
            "global_scope_fallback": {
              "ok": true,
              "scope_breakdown": {
                "tenant": 0,
                "global": 2,
                "total": 2
              }
            },
            "lifecycle_archive_active": {
              "ok": true
            },
            "distill_outputs_present": {
              "ok": true
            }
          },
          "governance": {
            "long_term_whitelist": [
              {
                "memory_type": "agent_decision",
                "label": "执行决策",
                "memory_layer_kind": "working",
                "retention_days": 30,
                "allowed_scopes": [
                  "tenant",
                  "global"
                ],
                "allowed_write_sources": [
                  "distillation"
                ]
              },
              {
                "memory_type": "event_digest",
                "label": "关键事件",
                "memory_layer_kind": "conversation",
                "retention_days": 7,
                "allowed_scopes": [
                  "tenant",
                  "global"
                ],
                "allowed_write_sources": [
                  "distillation"
                ]
              },
              {
                "memory_type": "session_summary",
                "label": "会话摘要",
                "memory_layer_kind": "conversation",
                "retention_days": 7,
                "allowed_scopes": [
                  "tenant",
                  "global"
                ],
                "allowed_write_sources": [
                  "distillation"
                ]
              },
              {
                "memory_type": "task_result",
                "label": "任务结果",
                "memory_layer_kind": "fact",
                "retention_days": null,
                "allowed_scopes": [
                  "tenant",
                  "global"
                ],
                "allowed_write_sources": [
                  "distillation"
                ]
              },
              {
                "memory_type": "user_preference",
                "label": "用户偏好",
                "memory_layer_kind": "fact",
                "retention_days": null,
                "allowed_scopes": [
                  "tenant",
                  "global"
                ],
                "allowed_write_sources": [
                  "distillation"
                ]
              }
            ],
            "local_only_reason_codes": [
              {
                "code": "credential_api_key",
                "description": "命中 API Key 等凭据脱敏规则，不允许进入中长期记忆。"
              },
              {
                "code": "credential_bearer_token",
                "description": "命中 Bearer Token 脱敏规则，不允许进入中长期记忆。"
              },
              {
                "code": "credential_bot_token",
                "description": "命中 Bot Token 脱敏规则，不允许进入中长期记忆。"
              },
              {
                "code": "credential_otp",
                "description": "命中一次性验证码规则，不允许进入中长期记忆。"
              },
              {
                "code": "credential_password",
                "description": "命中密码/口令模式，不允许进入中长期记忆。"
              },
              {
                "code": "credential_secret_assignment",
                "description": "命中 secret/token 赋值规则，不允许进入中长期记忆。"
              },
              {
                "code": "credential_session_secret",
                "description": "命中会话密钥/授权码模式，不允许进入中长期记忆。"
              },
              {
                "code": "debug_log_fragment",
                "description": "命中临时调试日志/排障片段模式，不允许进入中长期记忆。"
              },
              {
                "code": "financial_bank_card",
                "description": "命中银行卡类敏感标识规则，不允许进入中长期记忆。"
              },
              {
                "code": "pii_cn_id_card",
                "description": "命中身份证类敏感标识规则，不允许进入中长期记忆。"
              },
              {
                "code": "secret_mnemonic",
                "description": "命中助记词/seed phrase 模式，不允许进入中长期记忆。"
              },
              {
                "code": "secret_private_key",
                "description": "命中私钥内容模式，不允许进入中长期记忆。"
              }
            ],
            "supported_memory_scopes": [
              "tenant",
              "global"
            ],
            "restricted_external_write_sources": [
              "external_agent",
              "external_skill"
            ],
            "retention_days": {
              "conversation": 7,
              "working": 30
            },
            "review_flow": [
              "pending",
              "approved",
              "rejected"
            ],
            "lifecycle_statuses": [
              "active",
              "archived",
              "deleted"
            ]
          },
          "summary": {
            "passed_checks": 7,
            "failed_checks": 0
          }
        }
      }
    }
  },
  "generated_at": "2026-04-15T19:43:36+00:00"
}
```
