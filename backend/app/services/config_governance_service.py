from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from app.config import get_settings
from app.services.persistence_service import persistence_service
from app.services.settings_service import (
    DEFAULT_AGENT_API_SETTINGS,
    DEFAULT_CHANNEL_INTEGRATION_SETTINGS,
    DEFAULT_GENERAL_SETTINGS,
    DEFAULT_SECURITY_POLICY_SETTINGS,
    get_agent_api_runtime_settings,
    get_channel_integration_runtime_settings,
    get_general_settings,
    get_security_policy_settings,
)
from app.services.store import store


SYSTEM_SETTING_PRIORITY = [
    "database_system_settings",
    "runtime_cache",
    "deployment_defaults",
]

DEPLOYMENT_PRIORITY = [
    "deployment_env",
]


def _mask_secret(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:4]}***{normalized[-2:]}"


def _risk_level(*, warnings: list[str]) -> str:
    return "warning" if warnings else "ok"


def _read_setting_source(key: str) -> tuple[str, str]:
    persisted_setting = persistence_service.get_system_setting(key)
    if persisted_setting is not None:
        return "database_system_settings", str(persisted_setting.get("updated_at") or "")
    cached_setting = store.system_settings.get(key)
    if cached_setting is not None:
        return "runtime_cache", ""
    return "deployment_defaults", ""


def _settings_change_audits(*, limit: int = 20) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for log in store.audit_logs:
        action = str(log.get("action") or "")
        if not action.startswith("settings."):
            continue
        items.append(
            {
                "id": str(log.get("id") or ""),
                "timestamp": str(log.get("timestamp") or ""),
                "action": action,
                "user": str(log.get("user") or ""),
                "resource": str(log.get("resource") or ""),
                "details": str(log.get("details") or ""),
                "status": str(log.get("status") or "success"),
            }
        )
        if len(items) >= limit:
            break
    return items


def _governed_runtime_sections() -> list[dict[str, Any]]:
    general_source, general_updated_at = _read_setting_source("general")
    security_source, security_updated_at = _read_setting_source("security_policy")
    agent_api_source, agent_api_updated_at = _read_setting_source("agent_api")
    channel_source, channel_updated_at = _read_setting_source("channel_integrations")

    agent_api = get_agent_api_runtime_settings()
    channel_integrations = get_channel_integration_runtime_settings()

    agent_warnings: list[str] = []
    for provider_key, provider in (agent_api.get("providers") or {}).items():
        if not provider.get("enabled"):
            continue
        if not str(provider.get("base_url") or "").strip():
            agent_warnings.append(f"{provider_key} 已启用但未配置 base_url。")
        if not str(provider.get("model") or "").strip():
            agent_warnings.append(f"{provider_key} 已启用但未配置默认模型。")
        if not str(provider.get("api_key") or "").strip():
            agent_warnings.append(f"{provider_key} 已启用但未配置 API Key。")

    channel_warnings: list[str] = []
    telegram = channel_integrations.get("telegram") or {}
    if telegram.get("enabled") and not str(telegram.get("bot_token") or "").strip():
        channel_warnings.append("Telegram 已启用但未配置 bot token。")
    wecom = channel_integrations.get("wecom") or {}
    if wecom.get("enabled") and not str(wecom.get("bot_webhook_key") or "").strip():
        channel_warnings.append("WeCom 已启用但未配置 bot webhook key。")
    feishu = channel_integrations.get("feishu") or {}
    if feishu.get("enabled") and not str(feishu.get("bot_webhook_key") or "").strip():
        channel_warnings.append("Feishu 已启用但未配置 bot webhook key。")
    dingtalk = channel_integrations.get("dingtalk") or {}
    if dingtalk.get("enabled") and not str(dingtalk.get("client_secret") or "").strip():
        channel_warnings.append("DingTalk 已启用但未配置 client secret。")

    return [
        {
            "key": "general",
            "label": "通用设置",
            "category": "runtime",
            "mutability": "mutable",
            "effective_source": general_source,
            "read_priority": SYSTEM_SETTING_PRIORITY,
            "updated_at": general_updated_at,
            "defaults_from": "deployment_defaults",
            "current": get_general_settings()["settings"],
            "defaults": deepcopy(DEFAULT_GENERAL_SETTINGS),
            "warnings": [],
            "risk_level": "ok",
        },
        {
            "key": "security_policy",
            "label": "安全策略",
            "category": "runtime",
            "mutability": "mutable",
            "effective_source": security_source,
            "read_priority": SYSTEM_SETTING_PRIORITY,
            "updated_at": security_updated_at,
            "defaults_from": "deployment_defaults",
            "current": get_security_policy_settings()["settings"],
            "defaults": deepcopy(DEFAULT_SECURITY_POLICY_SETTINGS),
            "warnings": [],
            "risk_level": "ok",
        },
        {
            "key": "agent_api",
            "label": "Agent API 供应商",
            "category": "runtime",
            "mutability": "mutable",
            "effective_source": agent_api_source,
            "read_priority": SYSTEM_SETTING_PRIORITY,
            "updated_at": agent_api_updated_at,
            "defaults_from": "deployment_defaults",
            "current": {
                "providers": {
                    key: {
                        **{k: v for k, v in provider.items() if k != "api_key"},
                        "has_api_key": bool(provider.get("api_key")),
                        "api_key_masked": _mask_secret(provider.get("api_key")),
                    }
                    for key, provider in (agent_api.get("providers") or {}).items()
                }
            },
            "defaults": deepcopy(DEFAULT_AGENT_API_SETTINGS),
            "warnings": agent_warnings,
            "risk_level": _risk_level(warnings=agent_warnings),
        },
        {
            "key": "channel_integrations",
            "label": "渠道接入",
            "category": "runtime",
            "mutability": "mutable",
            "effective_source": channel_source,
            "read_priority": SYSTEM_SETTING_PRIORITY,
            "updated_at": channel_updated_at,
            "defaults_from": "deployment_defaults",
            "current": {
                "telegram": {
                    **{k: v for k, v in telegram.items() if k not in {"bot_token", "webhook_secret"}},
                    "has_bot_token": bool(telegram.get("bot_token")),
                    "bot_token_masked": _mask_secret(telegram.get("bot_token")),
                    "has_webhook_secret": bool(telegram.get("webhook_secret")),
                    "webhook_secret_masked": _mask_secret(telegram.get("webhook_secret")),
                },
                "wecom": {
                    **{k: v for k, v in wecom.items() if k not in {"bot_webhook_key", "webhook_secret"}},
                    "has_bot_webhook_key": bool(wecom.get("bot_webhook_key")),
                    "bot_webhook_key_masked": _mask_secret(wecom.get("bot_webhook_key")),
                    "has_webhook_secret": bool(wecom.get("webhook_secret")),
                    "webhook_secret_masked": _mask_secret(wecom.get("webhook_secret")),
                },
                "feishu": {
                    **{k: v for k, v in feishu.items() if k not in {"bot_webhook_key", "webhook_secret"}},
                    "has_bot_webhook_key": bool(feishu.get("bot_webhook_key")),
                    "bot_webhook_key_masked": _mask_secret(feishu.get("bot_webhook_key")),
                    "has_webhook_secret": bool(feishu.get("webhook_secret")),
                    "webhook_secret_masked": _mask_secret(feishu.get("webhook_secret")),
                },
                "dingtalk": {
                    **{k: v for k, v in dingtalk.items() if k not in {"client_secret", "webhook_secret"}},
                    "has_client_secret": bool(dingtalk.get("client_secret")),
                    "client_secret_masked": _mask_secret(dingtalk.get("client_secret")),
                    "has_webhook_secret": bool(dingtalk.get("webhook_secret")),
                    "webhook_secret_masked": _mask_secret(dingtalk.get("webhook_secret")),
                },
            },
            "defaults": deepcopy(DEFAULT_CHANNEL_INTEGRATION_SETTINGS),
            "warnings": channel_warnings,
            "risk_level": _risk_level(warnings=channel_warnings),
        },
    ]


def _deployment_sections() -> list[dict[str, Any]]:
    settings = get_settings()
    auth_warnings: list[str] = []
    if settings.auth_jwt_secret == "workbot-dev-secret":
        auth_warnings.append("仍在使用默认 auth_jwt_secret。")
    if not str(settings.data_encryption_key or "").strip():
        auth_warnings.append("未显式配置 data_encryption_key，将退回到 jwt secret 派生密钥。")
    if settings.auth_demo_fallback_enabled:
        auth_warnings.append("auth_demo_fallback_enabled 仍为开启状态。")
    if str(settings.demo_admin_password or "") == "workbot123":
        auth_warnings.append("仍在使用默认 demo_admin_password。")

    infra_warnings: list[str] = []
    if settings.environment.lower() == "production":
        if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
            infra_warnings.append("production 环境仍在使用本地 database_url。")
        if "localhost" in settings.redis_url or "127.0.0.1" in settings.redis_url:
            infra_warnings.append("production 环境仍在使用本地 redis_url。")
        if "localhost" in settings.nats_url or "127.0.0.1" in settings.nats_url:
            infra_warnings.append("production 环境仍在使用本地 nats_url。")

    tool_source_mode = str(os.getenv("WORKBOT_TOOL_SOURCES_MODE", "hybrid") or "hybrid").strip().lower()
    external_tool_sources_file = str(os.getenv("WORKBOT_EXTERNAL_TOOL_SOURCES_FILE", "") or "").strip()
    strict_external_skills = str(os.getenv("WORKBOT_STRICT_EXTERNAL_SKILLS", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    webhook_warnings: list[str] = []
    if settings.webhook_max_payload_bytes > 1024 * 1024:
        webhook_warnings.append("webhook_max_payload_bytes 超过 1MB，入口面增大。")
    if settings.webhook_rate_limit_max_requests > 500:
        webhook_warnings.append("webhook_rate_limit_max_requests 偏高，可能削弱入口防护。")

    return [
        {
            "key": "auth_runtime",
            "label": "认证与密钥",
            "category": "deployment",
            "mutability": "immutable",
            "effective_source": "deployment_env",
            "read_priority": DEPLOYMENT_PRIORITY,
            "updated_at": "",
            "defaults_from": "env_defaults",
            "current": {
                "environment": settings.environment,
                "demo_admin_email": settings.demo_admin_email,
                "auth_access_token_ttl_seconds": settings.auth_access_token_ttl_seconds,
                "auth_refresh_token_ttl_seconds": settings.auth_refresh_token_ttl_seconds,
                "auth_demo_fallback_enabled": settings.auth_demo_fallback_enabled,
                "auth_jwt_secret_masked": _mask_secret(settings.auth_jwt_secret),
                "data_encryption_key_masked": _mask_secret(settings.data_encryption_key),
            },
            "defaults": {},
            "warnings": auth_warnings,
            "risk_level": _risk_level(warnings=auth_warnings),
        },
        {
            "key": "orchestration_runtime",
            "label": "执行与调度参数",
            "category": "deployment",
            "mutability": "immutable",
            "effective_source": "deployment_env",
            "read_priority": DEPLOYMENT_PRIORITY,
            "updated_at": "",
            "defaults_from": "env_defaults",
            "current": {
                "message_debounce_seconds": settings.message_debounce_seconds,
                "workflow_execution_poll_interval_seconds": settings.workflow_execution_poll_interval_seconds,
                "workflow_execution_lease_seconds": settings.workflow_execution_lease_seconds,
                "workflow_execution_scan_limit": settings.workflow_execution_scan_limit,
                "internal_event_retry_poll_interval_seconds": settings.internal_event_retry_poll_interval_seconds,
                "internal_event_retry_backoff_seconds": settings.internal_event_retry_backoff_seconds,
                "internal_event_retry_lease_seconds": settings.internal_event_retry_lease_seconds,
                "internal_event_retry_scan_limit": settings.internal_event_retry_scan_limit,
            },
            "defaults": {},
            "warnings": [],
            "risk_level": "ok",
        },
        {
            "key": "memory_runtime",
            "label": "记忆系统参数",
            "category": "deployment",
            "mutability": "immutable",
            "effective_source": "deployment_env",
            "read_priority": DEPLOYMENT_PRIORITY,
            "updated_at": "",
            "defaults_from": "env_defaults",
            "current": {
                "memory_sqlite_path": settings.memory_sqlite_path,
                "memory_retrieve_limit": settings.memory_retrieve_limit,
                "memory_session_idle_seconds": settings.memory_session_idle_seconds,
                "memory_weekly_distill_seconds": settings.memory_weekly_distill_seconds,
                "chroma_url": settings.chroma_url,
                "chroma_client_mode": settings.chroma_client_mode,
                "chroma_collection_name": settings.chroma_collection_name,
            },
            "defaults": {},
            "warnings": [],
            "risk_level": "ok",
        },
        {
            "key": "infrastructure_runtime",
            "label": "基础设施链路",
            "category": "deployment",
            "mutability": "immutable",
            "effective_source": "deployment_env",
            "read_priority": DEPLOYMENT_PRIORITY,
            "updated_at": "",
            "defaults_from": "env_defaults",
            "current": {
                "database_url": settings.database_url,
                "redis_url": settings.redis_url,
                "nats_url": settings.nats_url,
                "trace_export_enabled": settings.trace_export_enabled,
                "trace_export_endpoint": settings.trace_export_endpoint,
                "trace_export_file_path": settings.trace_export_file_path,
                "trace_export_timeout_seconds": settings.trace_export_timeout_seconds,
            },
            "defaults": {},
            "warnings": infra_warnings,
            "risk_level": _risk_level(warnings=infra_warnings),
        },
        {
            "key": "tool_source_topology",
            "label": "工具源与外接拓扑",
            "category": "deployment",
            "mutability": "immutable",
            "effective_source": "deployment_env",
            "read_priority": DEPLOYMENT_PRIORITY,
            "updated_at": "",
            "defaults_from": "env_defaults",
            "current": {
                "agent_config_root": settings.agent_config_root,
                "tool_sources_mode": tool_source_mode,
                "external_tool_sources_file": external_tool_sources_file or None,
                "strict_external_skills": strict_external_skills,
                "search_mcp_base_url": os.getenv("WORKBOT_SEARCH_MCP_BASE_URL", "http://127.0.0.1:8093"),
                "pdf_mcp_base_url": os.getenv("WORKBOT_PDF_MCP_BASE_URL", "http://127.0.0.1:8092"),
                "writer_mcp_base_url": os.getenv("WORKBOT_WRITER_MCP_BASE_URL", "http://127.0.0.1:8094"),
                "weather_mcp_base_url": os.getenv("WORKBOT_WEATHER_MCP_BASE_URL", "http://127.0.0.1:8095"),
                "order_mcp_base_url": os.getenv("WORKBOT_ORDER_MCP_BASE_URL", "http://127.0.0.1:8096"),
                "crm_mcp_base_url": os.getenv("WORKBOT_CRM_MCP_BASE_URL", "http://127.0.0.1:8097"),
            },
            "defaults": {},
            "warnings": [],
            "risk_level": "ok",
        },
        {
            "key": "webhook_guard",
            "label": "Webhook 入口防护",
            "category": "deployment",
            "mutability": "immutable",
            "effective_source": "deployment_env",
            "read_priority": DEPLOYMENT_PRIORITY,
            "updated_at": "",
            "defaults_from": "env_defaults",
            "current": {
                "webhook_rate_limit_max_requests": settings.webhook_rate_limit_max_requests,
                "webhook_rate_limit_window_seconds": settings.webhook_rate_limit_window_seconds,
                "webhook_max_payload_bytes": settings.webhook_max_payload_bytes,
            },
            "defaults": {},
            "warnings": webhook_warnings,
            "risk_level": _risk_level(warnings=webhook_warnings),
        },
    ]


def get_config_governance_snapshot() -> dict[str, Any]:
    runtime_sections = _governed_runtime_sections()
    deployment_sections = _deployment_sections()
    sections = [*runtime_sections, *deployment_sections]
    warning_count = sum(len(section["warnings"]) for section in sections)
    return {
        "summary": {
            "total_sections": len(sections),
            "runtime_mutable_sections": len(runtime_sections),
            "deployment_immutable_sections": len(deployment_sections),
            "warning_count": warning_count,
        },
        "read_priority_model": {
            "runtime_mutable": SYSTEM_SETTING_PRIORITY,
            "deployment_immutable": DEPLOYMENT_PRIORITY,
        },
        "sections": sections,
        "recent_change_audits": _settings_change_audits(),
    }
