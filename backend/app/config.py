from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


EXTERNAL_CONNECTION_DEFAULT_SHARED_SECRET = "workbot-external-secret"


class Settings(BaseSettings):
    app_name: str = "WorkBot Backend"
    api_prefix: str = "/api"
    environment: str = "development"
    agent_config_root: str = "agents"
    database_url: str = "postgresql+psycopg://workbot:workbot@localhost:5432/workbot"
    redis_url: str = "redis://localhost:6379/0"
    memory_sqlite_path: str = "data/memory-midterm.sqlite3"
    enable_wiki_knowledge: bool = True
    nats_url: str = "nats://localhost:4222"
    chroma_url: str = "http://localhost:8000"
    chroma_client_mode: str = "http"
    chroma_persist_path: str | None = None
    chroma_collection_name: str = "workbot_long_term_memory"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    demo_admin_email: str = "admin@workbot.ai"
    demo_admin_password: str = "workbot123"
    auth_jwt_secret: str = "workbot-dev-secret"
    metrics_scrape_token: str | None = None
    data_encryption_key: str | None = None
    auth_access_token_ttl_seconds: int = 3600
    auth_refresh_token_ttl_seconds: int = 604800
    auth_demo_fallback_enabled: bool = True
    message_rate_limit_per_minute: int = 5
    message_rate_limit_cooldown_seconds: int = 30
    message_rate_limit_ban_threshold: int = 3
    message_rate_limit_ban_seconds: int = 300
    message_debounce_seconds: float = 0.5
    nats_operation_timeout_seconds: float = 0.25
    workflow_execution_poll_interval_seconds: float = 0.2
    workflow_execution_lease_seconds: float = 45.0
    workflow_execution_scan_limit: int = 50
    memory_retrieve_limit: int = 5
    memory_session_idle_seconds: int = 900
    memory_weekly_distill_seconds: int = 604800
    internal_event_retry_poll_interval_seconds: float = 5.0
    internal_event_retry_backoff_seconds: int = 15
    internal_event_retry_lease_seconds: int = 60
    internal_event_retry_scan_limit: int = 20
    security_incident_window_seconds: int = 600
    trace_export_enabled: bool = False
    trace_export_endpoint: str | None = None
    trace_export_file_path: str | None = None
    trace_export_timeout_seconds: float = 3.0
    telegram_bot_token: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_http_timeout_seconds: float = 10.0
    wecom_bot_webhook_key: str | None = None
    wecom_bot_webhook_base_url: str = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
    wecom_http_timeout_seconds: float = 10.0
    feishu_bot_webhook_key: str | None = None
    feishu_bot_webhook_base_url: str = "https://open.feishu.cn/open-apis/bot/v2/hook"
    feishu_http_timeout_seconds: float = 10.0
    dingtalk_app_id: str | None = None
    dingtalk_agent_id: str | None = None
    dingtalk_client_id: str | None = None
    dingtalk_client_secret: str | None = None
    dingtalk_corp_id: str | None = None
    dingtalk_api_base_url: str = "https://oapi.dingtalk.com"
    dingtalk_http_timeout_seconds: float = 10.0
    telegram_webhook_secret: str | None = None
    wecom_webhook_secret: str | None = None
    wecom_webhook_secret_header: str = "X-WorkBot-Webhook-Secret"
    wecom_webhook_secret_query_param: str = "token"
    feishu_webhook_secret: str | None = None
    feishu_webhook_secret_header: str = "X-WorkBot-Webhook-Secret"
    feishu_webhook_secret_query_param: str = "token"
    dingtalk_webhook_secret: str | None = None
    dingtalk_webhook_secret_header: str = "X-WorkBot-Webhook-Secret"
    dingtalk_webhook_secret_query_param: str = "token"
    webhook_rate_limit_max_requests: int = 120
    webhook_rate_limit_window_seconds: int = 60
    webhook_max_payload_bytes: int = 128 * 1024
    external_connection_shared_secret: str = EXTERNAL_CONNECTION_DEFAULT_SHARED_SECRET
    external_connection_signature_ttl_seconds: int = 300
    external_connection_circuit_breaker_threshold: int = 3
    external_connection_backoff_base_seconds: int = 15
    external_connection_backoff_max_seconds: int = 300

    model_config = SettingsConfigDict(
        env_prefix="WORKBOT_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
