from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.services.encryption_service import ENCRYPTED_TEXT_PREFIX, encryption_service
from app.services.persistence_service import persistence_service
from app.services.store import store


DEFAULT_GENERAL_SETTINGS = {
    "dashboard_auto_refresh": True,
    "show_system_status": True,
}
_runtime_defaults = get_settings()
DEFAULT_WEBHOOK_SECRET_HEADER = "X-WorkBot-Webhook-Secret"
DEFAULT_WEBHOOK_SECRET_QUERY_PARAM = "token"
DEFAULT_SECURITY_POLICY_SETTINGS = {
    "message_rate_limit_per_minute": int(_runtime_defaults.message_rate_limit_per_minute),
    "message_rate_limit_cooldown_seconds": int(_runtime_defaults.message_rate_limit_cooldown_seconds),
    "message_rate_limit_ban_threshold": int(_runtime_defaults.message_rate_limit_ban_threshold),
    "message_rate_limit_ban_seconds": int(_runtime_defaults.message_rate_limit_ban_seconds),
    "security_incident_window_seconds": int(_runtime_defaults.security_incident_window_seconds),
    "prompt_rule_block_threshold": 4,
    "prompt_classifier_block_threshold": 3,
    "prompt_injection_enabled": True,
    "content_redaction_enabled": True,
}
AGENT_API_PROVIDER_KEYS = (
    "openai",
    "codex",
    "claude",
    "kimi",
    "minimax",
    "gemini",
    "deepseek",
    "openapi",
)
DEFAULT_AGENT_API_PROVIDER_SETTINGS = {
    "enabled": False,
    "base_url": "",
    "model": "",
    "organization_id": "",
    "project_id": "",
    "group_id": "",
    "endpoint_path": "",
    "notes": "",
    "api_key": None,
}
DEFAULT_AGENT_API_SETTINGS = {
    "providers": {
        "openai": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.4",
            "endpoint_path": "/responses",
            "notes": "OpenAI 标准 Responses API。",
        },
        "codex": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5-codex",
            "endpoint_path": "/responses",
            "notes": "用于编码类 Agent 的 Codex / OpenAI 兼容入口。",
        },
        "claude": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-sonnet-4-0",
            "endpoint_path": "/messages",
            "notes": "Anthropic Claude Messages API。",
        },
        "kimi": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-128k",
            "endpoint_path": "/chat/completions",
            "notes": "Moonshot / Kimi 兼容 OpenAI 风格接口。",
        },
        "minimax": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.minimaxi.com/v1",
            "model": "MiniMax-M1",
            "endpoint_path": "/text/chatcompletion_v2",
            "notes": "MiniMax 需要额外填写 Group ID。",
        },
        "gemini": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-2.5-pro",
            "endpoint_path": "/chat/completions",
            "notes": "Gemini OpenAI-compatible 入口。",
        },
        "deepseek": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "endpoint_path": "/chat/completions",
            "notes": "DeepSeek OpenAI-compatible 入口。",
        },
        "openapi": {
            **DEFAULT_AGENT_API_PROVIDER_SETTINGS,
            "base_url": "https://api.example.com/v1",
            "model": "",
            "endpoint_path": "/chat/completions",
            "notes": "自定义 OpenAI-compatible 网关。",
        },
    }
}
DEFAULT_CHANNEL_INTEGRATION_SETTINGS = {
    "telegram": {
        "enabled": True,
        "api_base_url": str(_runtime_defaults.telegram_api_base_url),
        "http_timeout_seconds": float(_runtime_defaults.telegram_http_timeout_seconds),
        "tenant_id": None,
        "tenant_name": None,
        "bot_token": str(_runtime_defaults.telegram_bot_token or "").strip() or None,
        "webhook_secret": str(_runtime_defaults.telegram_webhook_secret or "").strip() or None,
    },
    "wecom": {
        "enabled": True,
        "tenant_id": None,
        "tenant_name": None,
        "webhook_secret": str(_runtime_defaults.wecom_webhook_secret or "").strip() or None,
        "webhook_secret_header": str(
            getattr(_runtime_defaults, "wecom_webhook_secret_header", DEFAULT_WEBHOOK_SECRET_HEADER)
            or DEFAULT_WEBHOOK_SECRET_HEADER
        ),
        "webhook_secret_query_param": str(
            getattr(_runtime_defaults, "wecom_webhook_secret_query_param", DEFAULT_WEBHOOK_SECRET_QUERY_PARAM)
            or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM
        ),
        "bot_webhook_base_url": str(
            getattr(
                _runtime_defaults,
                "wecom_bot_webhook_base_url",
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
            )
            or "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
        ),
        "bot_webhook_key": str(getattr(_runtime_defaults, "wecom_bot_webhook_key", "") or "").strip() or None,
        "http_timeout_seconds": float(getattr(_runtime_defaults, "wecom_http_timeout_seconds", 10.0) or 10.0),
    },
    "feishu": {
        "enabled": True,
        "tenant_id": None,
        "tenant_name": None,
        "webhook_secret": str(_runtime_defaults.feishu_webhook_secret or "").strip() or None,
        "webhook_secret_header": str(
            getattr(_runtime_defaults, "feishu_webhook_secret_header", DEFAULT_WEBHOOK_SECRET_HEADER)
            or DEFAULT_WEBHOOK_SECRET_HEADER
        ),
        "webhook_secret_query_param": str(
            getattr(_runtime_defaults, "feishu_webhook_secret_query_param", DEFAULT_WEBHOOK_SECRET_QUERY_PARAM)
            or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM
        ),
        "bot_webhook_base_url": str(
            getattr(
                _runtime_defaults,
                "feishu_bot_webhook_base_url",
                "https://open.feishu.cn/open-apis/bot/v2/hook",
            )
            or "https://open.feishu.cn/open-apis/bot/v2/hook"
        ),
        "bot_webhook_key": str(getattr(_runtime_defaults, "feishu_bot_webhook_key", "") or "").strip() or None,
        "http_timeout_seconds": float(getattr(_runtime_defaults, "feishu_http_timeout_seconds", 10.0) or 10.0),
    },
    "dingtalk": {
        "enabled": True,
        "tenant_id": None,
        "tenant_name": None,
        "app_id": str(getattr(_runtime_defaults, "dingtalk_app_id", "") or "").strip(),
        "agent_id": str(getattr(_runtime_defaults, "dingtalk_agent_id", "") or "").strip(),
        "client_id": str(getattr(_runtime_defaults, "dingtalk_client_id", "") or "").strip(),
        "client_secret": str(getattr(_runtime_defaults, "dingtalk_client_secret", "") or "").strip() or None,
        "corp_id": str(getattr(_runtime_defaults, "dingtalk_corp_id", "") or "").strip(),
        "api_base_url": str(_runtime_defaults.dingtalk_api_base_url),
        "http_timeout_seconds": float(_runtime_defaults.dingtalk_http_timeout_seconds),
        "webhook_secret": str(_runtime_defaults.dingtalk_webhook_secret or "").strip() or None,
        "webhook_secret_header": str(
            getattr(_runtime_defaults, "dingtalk_webhook_secret_header", DEFAULT_WEBHOOK_SECRET_HEADER)
            or DEFAULT_WEBHOOK_SECRET_HEADER
        ),
        "webhook_secret_query_param": str(
            getattr(_runtime_defaults, "dingtalk_webhook_secret_query_param", DEFAULT_WEBHOOK_SECRET_QUERY_PARAM)
            or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM
        ),
    },
}
CHANNEL_INTEGRATION_SECRET_FIELDS = {
    "telegram": ("bot_token", "webhook_secret"),
    "wecom": ("bot_webhook_key", "webhook_secret"),
    "feishu": ("bot_webhook_key", "webhook_secret"),
    "dingtalk": ("client_secret", "webhook_secret"),
}


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_string(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_positive_int(
    value: Any,
    *,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    if value in {None, ""}:
        normalized = default
    else:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = default
    if normalized < minimum:
        normalized = minimum
    if maximum is not None and normalized > maximum:
        normalized = maximum
    return normalized


def _coerce_positive_float(
    value: Any,
    *,
    default: float,
    minimum: float = 0.1,
    maximum: float | None = None,
) -> float:
    if value in {None, ""}:
        normalized = default
    else:
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            normalized = default
    if normalized < minimum:
        normalized = minimum
    if maximum is not None and normalized > maximum:
        normalized = maximum
    return normalized


def _normalize_general_settings(payload: dict[str, Any] | None) -> dict[str, bool]:
    source = payload or {}
    return {
        "dashboard_auto_refresh": _coerce_bool(
            source.get("dashboard_auto_refresh", source.get("dashboardAutoRefresh")),
            default=DEFAULT_GENERAL_SETTINGS["dashboard_auto_refresh"],
        ),
        "show_system_status": _coerce_bool(
            source.get("show_system_status", source.get("showSystemStatus")),
            default=DEFAULT_GENERAL_SETTINGS["show_system_status"],
        ),
    }


def _normalize_security_policy_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload or {}
    return {
        "message_rate_limit_per_minute": _coerce_positive_int(
            source.get("message_rate_limit_per_minute", source.get("messageRateLimitPerMinute")),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_per_minute"],
            minimum=1,
            maximum=500,
        ),
        "message_rate_limit_cooldown_seconds": _coerce_positive_int(
            source.get(
                "message_rate_limit_cooldown_seconds",
                source.get("messageRateLimitCooldownSeconds"),
            ),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_cooldown_seconds"],
            minimum=1,
            maximum=3600,
        ),
        "message_rate_limit_ban_threshold": _coerce_positive_int(
            source.get("message_rate_limit_ban_threshold", source.get("messageRateLimitBanThreshold")),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_ban_threshold"],
            minimum=1,
            maximum=100,
        ),
        "message_rate_limit_ban_seconds": _coerce_positive_int(
            source.get("message_rate_limit_ban_seconds", source.get("messageRateLimitBanSeconds")),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["message_rate_limit_ban_seconds"],
            minimum=1,
            maximum=24 * 3600,
        ),
        "security_incident_window_seconds": _coerce_positive_int(
            source.get(
                "security_incident_window_seconds",
                source.get("securityIncidentWindowSeconds"),
            ),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["security_incident_window_seconds"],
            minimum=1,
            maximum=24 * 3600,
        ),
        "prompt_rule_block_threshold": _coerce_positive_int(
            source.get("prompt_rule_block_threshold", source.get("promptRuleBlockThreshold")),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["prompt_rule_block_threshold"],
            minimum=1,
            maximum=10,
        ),
        "prompt_classifier_block_threshold": _coerce_positive_int(
            source.get(
                "prompt_classifier_block_threshold",
                source.get("promptClassifierBlockThreshold"),
            ),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["prompt_classifier_block_threshold"],
            minimum=1,
            maximum=10,
        ),
        "prompt_injection_enabled": _coerce_bool(
            source.get("prompt_injection_enabled", source.get("promptInjectionEnabled")),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["prompt_injection_enabled"],
        ),
        "content_redaction_enabled": _coerce_bool(
            source.get("content_redaction_enabled", source.get("contentRedactionEnabled")),
            default=DEFAULT_SECURITY_POLICY_SETTINGS["content_redaction_enabled"],
        ),
    }


def _extract_agent_api_provider_map(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload or {}
    providers = source.get("providers")
    if isinstance(providers, dict):
        return providers
    return source


def _normalize_agent_api_key(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(ENCRYPTED_TEXT_PREFIX):
        decrypted = encryption_service.decrypt_text(text)
        normalized = str(decrypted).strip() if decrypted is not None else ""
        return normalized or None
    return text


def _normalize_secret_value(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(ENCRYPTED_TEXT_PREFIX):
        decrypted = encryption_service.decrypt_text(text)
        normalized = str(decrypted).strip() if decrypted is not None else ""
        return normalized or None
    return text


def _normalize_agent_api_provider_settings(
    payload: dict[str, Any] | None,
    *,
    defaults: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = payload or {}
    base = {**defaults, **(current or {})}
    has_api_key_field = "api_key" in source or "apiKey" in source
    raw_api_key = source.get("api_key", source.get("apiKey"))
    clear_api_key = _coerce_bool(
        source.get("clear_api_key", source.get("clearApiKey")),
        default=False,
    )

    api_key = _normalize_agent_api_key(base.get("api_key"))
    if clear_api_key:
        api_key = None
    elif has_api_key_field:
        candidate = _coerce_string(raw_api_key, default="")
        if candidate:
            api_key = candidate

    return {
        "enabled": _coerce_bool(source.get("enabled"), default=bool(base["enabled"])),
        "base_url": _coerce_string(
            source.get("base_url", source.get("baseUrl")),
            default=str(base["base_url"]),
        ),
        "model": _coerce_string(source.get("model"), default=str(base["model"])),
        "organization_id": _coerce_string(
            source.get(
                "organization_id",
                source.get("organizationId", source.get("organization")),
            ),
            default=str(base["organization_id"]),
        ),
        "project_id": _coerce_string(
            source.get("project_id", source.get("projectId", source.get("project"))),
            default=str(base["project_id"]),
        ),
        "group_id": _coerce_string(
            source.get("group_id", source.get("groupId")),
            default=str(base["group_id"]),
        ),
        "endpoint_path": _coerce_string(
            source.get("endpoint_path", source.get("endpointPath")),
            default=str(base["endpoint_path"]),
        ),
        "notes": _coerce_string(source.get("notes"), default=str(base["notes"])),
        "api_key": api_key,
    }


def _normalize_agent_api_settings(
    payload: dict[str, Any] | None,
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider_source = _extract_agent_api_provider_map(payload)
    current_source = _extract_agent_api_provider_map(current)
    normalized = {"providers": {}}
    for provider_key in AGENT_API_PROVIDER_KEYS:
        provider_payload = provider_source.get(provider_key)
        current_payload = current_source.get(provider_key)
        normalized["providers"][provider_key] = _normalize_agent_api_provider_settings(
            provider_payload if isinstance(provider_payload, dict) else None,
            defaults=DEFAULT_AGENT_API_SETTINGS["providers"][provider_key],
            current=current_payload if isinstance(current_payload, dict) else None,
        )
    return normalized


def _mask_agent_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return f"{normalized[:2]}{'*' * max(len(normalized) - 2, 0)}"
    return f"{normalized[:4]}{'*' * max(len(normalized) - 8, 4)}{normalized[-4:]}"


def _mask_secret_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return f"{normalized[:2]}{'*' * max(len(normalized) - 2, 0)}"
    return f"{normalized[:4]}{'*' * max(len(normalized) - 8, 4)}{normalized[-4:]}"


def _to_agent_api_response_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_agent_api_settings(payload)
    response = {"providers": {}}
    for provider_key, settings_payload in normalized["providers"].items():
        api_key = _normalize_agent_api_key(settings_payload.get("api_key"))
        response["providers"][provider_key] = {
            "enabled": bool(settings_payload["enabled"]),
            "base_url": str(settings_payload["base_url"]),
            "model": str(settings_payload["model"]),
            "organization_id": str(settings_payload["organization_id"]),
            "project_id": str(settings_payload["project_id"]),
            "group_id": str(settings_payload["group_id"]),
            "endpoint_path": str(settings_payload["endpoint_path"]),
            "notes": str(settings_payload["notes"]),
            "has_api_key": api_key is not None,
            "api_key_masked": _mask_agent_api_key(api_key),
        }
    return response


def _encrypt_agent_api_settings_for_storage(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_agent_api_settings(payload)
    encrypted = {"providers": {}}
    for provider_key, settings_payload in normalized["providers"].items():
        encrypted["providers"][provider_key] = {
            **settings_payload,
            "api_key": encryption_service.encrypt_text(settings_payload.get("api_key")),
        }
    return encrypted


def _decode_agent_api_payload(payload: Any) -> dict[str, Any]:
    decrypted_payload = encryption_service.decrypt_json(payload)
    if not isinstance(decrypted_payload, dict):
        return store.clone(DEFAULT_AGENT_API_SETTINGS)
    return _normalize_agent_api_settings(decrypted_payload)


def _channel_payload_value(source: dict[str, Any], snake_key: str, camel_key: str) -> Any:
    if snake_key in source:
        return source.get(snake_key)
    return source.get(camel_key)


def _camel_case_field_name(field: str) -> str:
    parts = field.split("_")
    return "".join([parts[0], *[part.capitalize() for part in parts[1:]]])


def _clear_channel_secret_value(source: dict[str, Any], field: str) -> bool:
    camel_field = _camel_case_field_name(field)
    return _coerce_bool(
        source.get(f"clear_{field}", source.get(f"clear{camel_field[:1].upper()}{camel_field[1:]}")),
        default=False,
    )


def _normalize_channel_tenant_binding(
    channel_payload: dict[str, Any],
    *,
    base: dict[str, Any],
) -> tuple[str | None, str | None]:
    has_tenant_id = "tenant_id" in channel_payload or "tenantId" in channel_payload
    has_tenant_name = "tenant_name" in channel_payload or "tenantName" in channel_payload
    base_tenant_id = _coerce_string(base.get("tenant_id"), default="") or None
    tenant_id = base_tenant_id
    tenant_name = _coerce_string(base.get("tenant_name"), default="") or None

    if has_tenant_id:
        tenant_id = _coerce_string(
            _channel_payload_value(channel_payload, "tenant_id", "tenantId"),
            default="",
        ) or None
        if tenant_id is None:
            tenant_name = None

    if has_tenant_name:
        tenant_name = _coerce_string(
            _channel_payload_value(channel_payload, "tenant_name", "tenantName"),
            default="",
        ) or None
    elif has_tenant_id and tenant_id is not None and tenant_id != base_tenant_id:
        tenant_name = tenant_id

    if tenant_id is None:
        tenant_name = None

    return tenant_id, tenant_name


def _normalize_channel_integration_settings(
    payload: dict[str, Any] | None,
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = payload or {}
    current_source = current or {}
    normalized: dict[str, Any] = {}

    for channel_key, defaults in DEFAULT_CHANNEL_INTEGRATION_SETTINGS.items():
        channel_payload = source.get(channel_key)
        if not isinstance(channel_payload, dict):
            channel_payload = {}
        current_payload = current_source.get(channel_key)
        if not isinstance(current_payload, dict):
            current_payload = {}
        base = {**defaults, **current_payload}
        secret_fields = CHANNEL_INTEGRATION_SECRET_FIELDS.get(channel_key, ())
        channel_settings = {**base}
        channel_settings["enabled"] = _coerce_bool(
            _channel_payload_value(channel_payload, "enabled", "enabled"),
            default=bool(base.get("enabled", True)),
        )
        tenant_id, tenant_name = _normalize_channel_tenant_binding(channel_payload, base=base)
        channel_settings["tenant_id"] = tenant_id
        channel_settings["tenant_name"] = tenant_name

        for field in secret_fields:
            normalized_secret = _normalize_secret_value(base.get(field))
            clear_value = _clear_channel_secret_value(channel_payload, field)
            incoming_value = _channel_payload_value(
                channel_payload,
                field,
                _camel_case_field_name(field),
            )
            if clear_value:
                normalized_secret = None
            elif incoming_value not in {None, ""}:
                normalized_secret = _normalize_secret_value(incoming_value)
            channel_settings[field] = normalized_secret

        if channel_key == "telegram":
            channel_settings["api_base_url"] = _coerce_string(
                _channel_payload_value(channel_payload, "api_base_url", "apiBaseUrl"),
                default=str(base["api_base_url"]),
            )
            channel_settings["http_timeout_seconds"] = _coerce_positive_float(
                _channel_payload_value(channel_payload, "http_timeout_seconds", "httpTimeoutSeconds"),
                default=float(base["http_timeout_seconds"]),
                minimum=0.1,
                maximum=120.0,
            )
        elif channel_key in {"wecom", "feishu"}:
            channel_settings["webhook_secret_header"] = _coerce_string(
                _channel_payload_value(channel_payload, "webhook_secret_header", "webhookSecretHeader"),
                default=str(base["webhook_secret_header"]),
            ) or DEFAULT_WEBHOOK_SECRET_HEADER
            channel_settings["webhook_secret_query_param"] = _coerce_string(
                _channel_payload_value(channel_payload, "webhook_secret_query_param", "webhookSecretQueryParam"),
                default=str(base["webhook_secret_query_param"]),
            ) or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM
            channel_settings["bot_webhook_base_url"] = _coerce_string(
                _channel_payload_value(channel_payload, "bot_webhook_base_url", "botWebhookBaseUrl"),
                default=str(base["bot_webhook_base_url"]),
            )
            channel_settings["http_timeout_seconds"] = _coerce_positive_float(
                _channel_payload_value(channel_payload, "http_timeout_seconds", "httpTimeoutSeconds"),
                default=float(base["http_timeout_seconds"]),
                minimum=0.1,
                maximum=120.0,
            )
        elif channel_key == "dingtalk":
            channel_settings["app_id"] = _coerce_string(
                _channel_payload_value(channel_payload, "app_id", "appId"),
                default=str(base["app_id"]),
            )
            channel_settings["agent_id"] = _coerce_string(
                _channel_payload_value(channel_payload, "agent_id", "agentId"),
                default=str(base.get("agent_id", "")),
            )
            channel_settings["client_id"] = _coerce_string(
                _channel_payload_value(channel_payload, "client_id", "clientId"),
                default=str(base["client_id"]),
            )
            channel_settings["corp_id"] = _coerce_string(
                _channel_payload_value(channel_payload, "corp_id", "corpId"),
                default=str(base["corp_id"]),
            )
            channel_settings["api_base_url"] = _coerce_string(
                _channel_payload_value(channel_payload, "api_base_url", "apiBaseUrl"),
                default=str(base["api_base_url"]),
            )
            channel_settings["http_timeout_seconds"] = _coerce_positive_float(
                _channel_payload_value(channel_payload, "http_timeout_seconds", "httpTimeoutSeconds"),
                default=float(base["http_timeout_seconds"]),
                minimum=0.1,
                maximum=120.0,
            )
            channel_settings["webhook_secret_header"] = _coerce_string(
                _channel_payload_value(channel_payload, "webhook_secret_header", "webhookSecretHeader"),
                default=str(base["webhook_secret_header"]),
            ) or DEFAULT_WEBHOOK_SECRET_HEADER
            channel_settings["webhook_secret_query_param"] = _coerce_string(
                _channel_payload_value(channel_payload, "webhook_secret_query_param", "webhookSecretQueryParam"),
                default=str(base["webhook_secret_query_param"]),
            ) or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM

        normalized[channel_key] = channel_settings

    return normalized


def _to_channel_integration_response_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_channel_integration_settings(payload)
    return {
        "telegram": {
            "enabled": bool(normalized["telegram"].get("enabled", True)),
            "api_base_url": str(normalized["telegram"]["api_base_url"]),
            "http_timeout_seconds": float(normalized["telegram"]["http_timeout_seconds"]),
            "tenant_id": normalized["telegram"].get("tenant_id"),
            "tenant_name": normalized["telegram"].get("tenant_name"),
            "has_bot_token": normalized["telegram"].get("bot_token") is not None,
            "bot_token_masked": _mask_secret_value(normalized["telegram"].get("bot_token")),
            "has_webhook_secret": normalized["telegram"].get("webhook_secret") is not None,
            "webhook_secret_masked": _mask_secret_value(normalized["telegram"].get("webhook_secret")),
        },
        "wecom": {
            "enabled": bool(normalized["wecom"].get("enabled", True)),
            "tenant_id": normalized["wecom"].get("tenant_id"),
            "tenant_name": normalized["wecom"].get("tenant_name"),
            "webhook_secret_header": str(normalized["wecom"]["webhook_secret_header"]),
            "webhook_secret_query_param": str(normalized["wecom"]["webhook_secret_query_param"]),
            "bot_webhook_base_url": str(normalized["wecom"]["bot_webhook_base_url"]),
            "http_timeout_seconds": float(normalized["wecom"]["http_timeout_seconds"]),
            "has_bot_webhook_key": normalized["wecom"].get("bot_webhook_key") is not None,
            "bot_webhook_key_masked": _mask_secret_value(normalized["wecom"].get("bot_webhook_key")),
            "has_webhook_secret": normalized["wecom"].get("webhook_secret") is not None,
            "webhook_secret_masked": _mask_secret_value(normalized["wecom"].get("webhook_secret")),
        },
        "feishu": {
            "enabled": bool(normalized["feishu"].get("enabled", True)),
            "tenant_id": normalized["feishu"].get("tenant_id"),
            "tenant_name": normalized["feishu"].get("tenant_name"),
            "webhook_secret_header": str(normalized["feishu"]["webhook_secret_header"]),
            "webhook_secret_query_param": str(normalized["feishu"]["webhook_secret_query_param"]),
            "bot_webhook_base_url": str(normalized["feishu"]["bot_webhook_base_url"]),
            "http_timeout_seconds": float(normalized["feishu"]["http_timeout_seconds"]),
            "has_bot_webhook_key": normalized["feishu"].get("bot_webhook_key") is not None,
            "bot_webhook_key_masked": _mask_secret_value(normalized["feishu"].get("bot_webhook_key")),
            "has_webhook_secret": normalized["feishu"].get("webhook_secret") is not None,
            "webhook_secret_masked": _mask_secret_value(normalized["feishu"].get("webhook_secret")),
        },
        "dingtalk": {
            "enabled": bool(normalized["dingtalk"].get("enabled", True)),
            "tenant_id": normalized["dingtalk"].get("tenant_id"),
            "tenant_name": normalized["dingtalk"].get("tenant_name"),
            "app_id": str(normalized["dingtalk"]["app_id"]),
            "agent_id": str(normalized["dingtalk"].get("agent_id") or ""),
            "client_id": str(normalized["dingtalk"]["client_id"]),
            "corp_id": str(normalized["dingtalk"]["corp_id"]),
            "api_base_url": str(normalized["dingtalk"]["api_base_url"]),
            "http_timeout_seconds": float(normalized["dingtalk"]["http_timeout_seconds"]),
            "webhook_secret_header": str(normalized["dingtalk"]["webhook_secret_header"]),
            "webhook_secret_query_param": str(normalized["dingtalk"]["webhook_secret_query_param"]),
            "has_client_secret": normalized["dingtalk"].get("client_secret") is not None,
            "client_secret_masked": _mask_secret_value(normalized["dingtalk"].get("client_secret")),
            "has_webhook_secret": normalized["dingtalk"].get("webhook_secret") is not None,
            "webhook_secret_masked": _mask_secret_value(normalized["dingtalk"].get("webhook_secret")),
        },
    }


def _encrypt_channel_integration_settings_for_storage(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_channel_integration_settings(payload)
    encrypted = {}
    for channel_key, channel_payload in normalized.items():
        encrypted[channel_key] = dict(channel_payload)
        for field in CHANNEL_INTEGRATION_SECRET_FIELDS.get(channel_key, ()):
            encrypted[channel_key][field] = encryption_service.encrypt_text(channel_payload.get(field))
    return encrypted


def _decode_channel_integration_payload(payload: Any) -> dict[str, Any]:
    decrypted_payload = encryption_service.decrypt_json(payload)
    if not isinstance(decrypted_payload, dict):
        return store.clone(DEFAULT_CHANNEL_INTEGRATION_SETTINGS)
    return _normalize_channel_integration_settings(decrypted_payload)


def _sync_runtime_general_settings(settings_payload: dict[str, Any]) -> dict[str, bool]:
    normalized = _normalize_general_settings(settings_payload)
    store.system_settings["general"] = store.clone(normalized)
    return store.clone(normalized)


def _sync_runtime_security_policy_settings(settings_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_security_policy_settings(settings_payload)
    store.system_settings["security_policy"] = store.clone(normalized)
    return store.clone(normalized)


def _sync_runtime_agent_api_settings(settings_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_agent_api_settings(settings_payload)
    store.system_settings["agent_api"] = store.clone(normalized)
    return store.clone(normalized)


def _sync_runtime_channel_integration_settings(settings_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_channel_integration_settings(settings_payload)
    store.system_settings["channel_integrations"] = store.clone(normalized)
    store.system_settings["channel_integration"] = store.clone(normalized)
    return store.clone(normalized)


def _read_setting_with_source(key: str) -> tuple[dict[str, Any] | None, bool]:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        persisted_setting, database_authoritative = read_setting(key)
        if persisted_setting is not None or database_authoritative:
            return persisted_setting, database_authoritative
        if getattr(persistence_service, "enabled", False):
            return None, True
        return None, False

    persisted_setting = persistence_service.get_system_setting(key)
    if persisted_setting is not None:
        return persisted_setting, True
    if getattr(persistence_service, "enabled", False):
        return None, True
    return None, False


def _read_general_setting_with_source() -> tuple[dict[str, Any] | None, bool]:
    return _read_setting_with_source("general")


def _read_security_policy_setting_with_source() -> tuple[dict[str, Any] | None, bool]:
    return _read_setting_with_source("security_policy")


def _read_agent_api_setting_with_source() -> tuple[dict[str, Any] | None, bool]:
    return _read_setting_with_source("agent_api")


def _read_channel_integration_setting_with_source() -> tuple[dict[str, Any] | None, bool]:
    persisted_setting, database_authoritative = _read_setting_with_source("channel_integrations")
    if persisted_setting is not None:
        return persisted_setting, database_authoritative

    legacy_setting, legacy_database_authoritative = _read_setting_with_source("channel_integration")
    if legacy_setting is not None:
        return legacy_setting, legacy_database_authoritative

    return None, database_authoritative or legacy_database_authoritative


def _current_general_settings_payload() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_general_setting_with_source()
    if persisted_setting is not None:
        payload = persisted_setting.get("payload")
        if isinstance(payload, dict):
            return store.clone(payload)
    if database_authoritative:
        return store.clone(DEFAULT_GENERAL_SETTINGS)

    cached_setting = store.system_settings.get("general")
    if isinstance(cached_setting, dict):
        return store.clone(cached_setting)

    return store.clone(DEFAULT_GENERAL_SETTINGS)


def _current_security_policy_settings_payload() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_security_policy_setting_with_source()
    if persisted_setting is not None:
        payload = persisted_setting.get("payload")
        if isinstance(payload, dict):
            return store.clone(payload)
    if database_authoritative:
        return store.clone(DEFAULT_SECURITY_POLICY_SETTINGS)

    cached_setting = store.system_settings.get("security_policy")
    if isinstance(cached_setting, dict):
        return store.clone(cached_setting)

    return store.clone(DEFAULT_SECURITY_POLICY_SETTINGS)


def _current_agent_api_settings_payload() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_agent_api_setting_with_source()
    if persisted_setting is not None:
        return _decode_agent_api_payload(persisted_setting.get("payload"))
    if database_authoritative:
        return store.clone(DEFAULT_AGENT_API_SETTINGS)

    cached_setting = store.system_settings.get("agent_api")
    if isinstance(cached_setting, dict):
        return _normalize_agent_api_settings(cached_setting)

    return store.clone(DEFAULT_AGENT_API_SETTINGS)


def _current_channel_integration_settings_payload() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_channel_integration_setting_with_source()
    if persisted_setting is not None:
        return _decode_channel_integration_payload(persisted_setting.get("payload"))
    if database_authoritative:
        return store.clone(DEFAULT_CHANNEL_INTEGRATION_SETTINGS)

    cached_setting = store.system_settings.get("channel_integrations")
    if not isinstance(cached_setting, dict):
        cached_setting = store.system_settings.get("channel_integration")
    if isinstance(cached_setting, dict):
        return _normalize_channel_integration_settings(cached_setting)

    return store.clone(DEFAULT_CHANNEL_INTEGRATION_SETTINGS)


def get_general_settings() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_general_setting_with_source()
    if persisted_setting is not None:
        settings_payload = _sync_runtime_general_settings(persisted_setting.get("payload") or {})
        return {
            "key": "general",
            "updated_at": str(persisted_setting.get("updated_at") or ""),
            "settings": settings_payload,
        }
    if database_authoritative:
        return {
            "key": "general",
            "updated_at": "",
            "settings": _sync_runtime_general_settings(DEFAULT_GENERAL_SETTINGS),
        }

    cached_setting = store.system_settings.get("general") or DEFAULT_GENERAL_SETTINGS
    return {
        "key": "general",
        "updated_at": "",
        "settings": _sync_runtime_general_settings(cached_setting),
    }


def update_general_settings(payload: dict[str, Any]) -> dict[str, Any]:
    partial_payload = {key: value for key, value in (payload or {}).items() if value is not None}
    merged_payload = {
        **_current_general_settings_payload(),
        **partial_payload,
    }
    normalized = _sync_runtime_general_settings(merged_payload)
    updated_at = datetime.now(UTC).isoformat()
    persistence_service.persist_system_setting(
        key="general",
        payload=normalized,
        updated_at=updated_at,
    )
    return {
        "key": "general",
        "updated_at": updated_at,
        "settings": store.clone(normalized),
    }


def get_security_policy_settings() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_security_policy_setting_with_source()
    if persisted_setting is not None:
        settings_payload = _sync_runtime_security_policy_settings(persisted_setting.get("payload") or {})
        return {
            "key": "security_policy",
            "updated_at": str(persisted_setting.get("updated_at") or ""),
            "settings": settings_payload,
        }
    if database_authoritative:
        return {
            "key": "security_policy",
            "updated_at": "",
            "settings": _sync_runtime_security_policy_settings(DEFAULT_SECURITY_POLICY_SETTINGS),
        }

    cached_setting = store.system_settings.get("security_policy") or DEFAULT_SECURITY_POLICY_SETTINGS
    return {
        "key": "security_policy",
        "updated_at": "",
        "settings": _sync_runtime_security_policy_settings(cached_setting),
    }


def update_security_policy_settings(payload: dict[str, Any]) -> dict[str, Any]:
    partial_payload = {key: value for key, value in (payload or {}).items() if value is not None}
    merged_payload = {
        **_current_security_policy_settings_payload(),
        **partial_payload,
    }
    normalized = _sync_runtime_security_policy_settings(merged_payload)
    updated_at = datetime.now(UTC).isoformat()
    persistence_service.persist_system_setting(
        key="security_policy",
        payload=normalized,
        updated_at=updated_at,
    )
    return {
        "key": "security_policy",
        "updated_at": updated_at,
        "settings": store.clone(normalized),
    }


def get_agent_api_settings() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_agent_api_setting_with_source()
    if persisted_setting is not None:
        normalized = _sync_runtime_agent_api_settings(_decode_agent_api_payload(persisted_setting.get("payload")))
        return {
            "key": "agent_api",
            "updated_at": str(persisted_setting.get("updated_at") or ""),
            "settings": _to_agent_api_response_settings(normalized),
        }
    if database_authoritative:
        normalized = _sync_runtime_agent_api_settings(DEFAULT_AGENT_API_SETTINGS)
        return {
            "key": "agent_api",
            "updated_at": "",
            "settings": _to_agent_api_response_settings(normalized),
        }

    cached_setting = store.system_settings.get("agent_api") or DEFAULT_AGENT_API_SETTINGS
    normalized = _sync_runtime_agent_api_settings(cached_setting)
    return {
        "key": "agent_api",
        "updated_at": "",
        "settings": _to_agent_api_response_settings(normalized),
    }


def update_agent_api_settings(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_agent_api_settings(payload, current=_current_agent_api_settings_payload())
    updated_at = datetime.now(UTC).isoformat()
    persistence_service.persist_system_setting(
        key="agent_api",
        payload=_encrypt_agent_api_settings_for_storage(normalized),
        updated_at=updated_at,
    )
    runtime_payload = _sync_runtime_agent_api_settings(normalized)
    return {
        "key": "agent_api",
        "updated_at": updated_at,
        "settings": _to_agent_api_response_settings(runtime_payload),
    }


def get_agent_api_runtime_settings() -> dict[str, Any]:
    return _sync_runtime_agent_api_settings(_current_agent_api_settings_payload())


def get_channel_integration_settings() -> dict[str, Any]:
    persisted_setting, database_authoritative = _read_channel_integration_setting_with_source()
    if persisted_setting is not None:
        normalized = _sync_runtime_channel_integration_settings(
            _decode_channel_integration_payload(persisted_setting.get("payload"))
        )
        return {
            "key": "channel_integrations",
            "updated_at": str(persisted_setting.get("updated_at") or ""),
            "settings": _to_channel_integration_response_settings(normalized),
        }
    if database_authoritative:
        normalized = _sync_runtime_channel_integration_settings(DEFAULT_CHANNEL_INTEGRATION_SETTINGS)
        return {
            "key": "channel_integrations",
            "updated_at": "",
            "settings": _to_channel_integration_response_settings(normalized),
        }

    cached_setting = (
        store.system_settings.get("channel_integrations")
        or store.system_settings.get("channel_integration")
        or DEFAULT_CHANNEL_INTEGRATION_SETTINGS
    )
    normalized = _sync_runtime_channel_integration_settings(cached_setting)
    return {
        "key": "channel_integrations",
        "updated_at": "",
        "settings": _to_channel_integration_response_settings(normalized),
    }


def update_channel_integration_settings(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_channel_integration_settings(
        payload,
        current=_current_channel_integration_settings_payload(),
    )
    updated_at = datetime.now(UTC).isoformat()
    persistence_service.persist_system_setting(
        key="channel_integrations",
        payload=_encrypt_channel_integration_settings_for_storage(normalized),
        updated_at=updated_at,
    )
    runtime_payload = _sync_runtime_channel_integration_settings(normalized)
    return {
        "key": "channel_integrations",
        "updated_at": updated_at,
        "settings": _to_channel_integration_response_settings(runtime_payload),
    }


def get_channel_integration_runtime_settings() -> dict[str, Any]:
    return _sync_runtime_channel_integration_settings(_current_channel_integration_settings_payload())
