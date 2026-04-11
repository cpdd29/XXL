from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.base import APIModel


class ChannelType(str, Enum):
    TELEGRAM = "telegram"
    WECOM = "wecom"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"


CHANNEL_DISPLAY_NAMES = {
    ChannelType.TELEGRAM: "Telegram",
    ChannelType.WECOM: "WeCom",
    ChannelType.FEISHU: "Feishu",
    ChannelType.DINGTALK: "DingTalk",
}


def normalize_channel_type(channel: ChannelType | str) -> ChannelType:
    if isinstance(channel, ChannelType):
        return channel
    return ChannelType(str(channel).strip().lower())


def channel_display_name(channel: ChannelType | str) -> str:
    return CHANNEL_DISPLAY_NAMES[normalize_channel_type(channel)]


def webhook_auth_scope(channel: ChannelType | str) -> str:
    return f"webhook:{normalize_channel_type(channel).value}"


def allowed_ingest_auth_scopes() -> set[str]:
    return {"messages:ingest", *(webhook_auth_scope(channel) for channel in ChannelType)}


class UnifiedMessage(APIModel):
    message_id: str
    channel: ChannelType
    platform_user_id: str
    chat_id: str
    text: str
    received_at: str
    raw_payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    user_key: str | None = None
    detected_lang: str | None = None


class TelegramFrom(APIModel):
    id: int
    is_bot: bool = False
    first_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class TelegramChat(APIModel):
    id: int
    type: str
    title: str | None = None
    username: str | None = None


class TelegramMessage(APIModel):
    message_id: int
    date: int
    text: str | None = None
    from_: TelegramFrom = Field(alias="from")
    chat: TelegramChat


class TelegramWebhookUpdate(APIModel):
    update_id: int
    message: TelegramMessage | None = None


class IngestUnifiedMessageRequest(APIModel):
    channel: ChannelType
    platform_user_id: str
    chat_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    received_at: str | None = None
    session_id: str | None = None
    auth_scope: str = "messages:ingest"


class MessageRouteDecision(APIModel):
    intent: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    execution_agent_id: str | None = None
    execution_agent: str | None = None
    interaction_mode: str | None = None
    reception_mode: str | None = None
    workflow_mode: str | None = None
    requires_permission: bool | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    user_visible_workflow_mode: str | None = None
    execution_plan: dict[str, Any] | None = None
    selected_by_message_trigger: bool = False
    route_message: str | None = None
    intent_confidence: float | None = None
    intent_scores: dict[str, int] = Field(default_factory=dict)
    intent_reasons: dict[str, list[str]] = Field(default_factory=dict)
    candidate_workflows: list[dict[str, Any]] = Field(default_factory=list)
    skipped_workflows: list[dict[str, str]] = Field(default_factory=list)
    routing_strategy: str | None = None
    execution_support: dict[str, Any] | None = None
    route_version: str | None = None
    confirmation_required: bool | None = None
    confirmation_status: str | None = None
    confirmation_deadline_at: str | None = None
    requires_approval: bool | None = None
    approval_required: bool | None = None
    approval_status: str | None = None
    audit_id: str | None = None
    idempotency_key: str | None = None
    execution_scope: str | None = None
    evidence_policy: str | None = None
    schedule_plan: dict[str, Any] | None = None


class IngestMessageResponse(APIModel):
    ok: bool
    message: str
    entrypoint: str
    task_id: str | None = None
    run_id: str | None = None
    intent: str | None = None
    interaction_mode: str | None = None
    reception_mode: str | None = None
    unified_message: UnifiedMessage
    trace_id: str | None = None
    detected_lang: str | None = None
    memory_hits: int = 0
    warnings: list[str] = Field(default_factory=list)
    merged_into_task_id: str | None = None
    route_decision: MessageRouteDecision | None = None
