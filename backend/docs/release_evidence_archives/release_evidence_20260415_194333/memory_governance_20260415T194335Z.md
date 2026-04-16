# Memory Governance

## Status

```json
{
  "ok": true,
  "status": null,
  "generated_at": "2026-04-15T19:43:35+00:00"
}
```

## Payload

```json
{
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
  },
  "generated_at": "2026-04-15T19:43:35+00:00"
}
```
