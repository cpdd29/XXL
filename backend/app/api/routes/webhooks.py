from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.schemas.messages import ChannelType, IngestMessageResponse, TelegramWebhookUpdate
from app.schemas.workflows import WorkflowActionResponse
from app.services.message_ingestion_service import ingest_channel_webhook, ingest_telegram_webhook
from app.services.security_gateway_service import security_gateway_service
from app.services.settings_service import get_channel_integration_runtime_settings
from app.services.webhook_guard_service import (
    enforce_webhook_payload_size,
    enforce_webhook_rate_limit,
    sanitize_webhook_payload,
)
from app.services.workflow_service import trigger_workflow_webhook

router = APIRouter()
DEFAULT_WEBHOOK_SECRET_HEADER = "X-WorkBot-Webhook-Secret"
DEFAULT_WEBHOOK_SECRET_QUERY_PARAM = "token"
TELEGRAM_WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _channel_secret_error_label(channel: ChannelType) -> str:
    return {
        ChannelType.WECOM: "WeCom",
        ChannelType.FEISHU: "Feishu",
        ChannelType.DINGTALK: "DingTalk",
    }[channel]


def _configured_channel_secret(channel: ChannelType) -> tuple[str | None, str, str]:
    settings = get_channel_integration_runtime_settings()
    if channel == ChannelType.WECOM:
        provider = settings["wecom"]
        return (
            provider.get("webhook_secret"),
            str(provider.get("webhook_secret_header") or DEFAULT_WEBHOOK_SECRET_HEADER),
            str(provider.get("webhook_secret_query_param") or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM),
        )
    if channel == ChannelType.FEISHU:
        provider = settings["feishu"]
        return (
            provider.get("webhook_secret"),
            str(provider.get("webhook_secret_header") or DEFAULT_WEBHOOK_SECRET_HEADER),
            str(provider.get("webhook_secret_query_param") or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM),
        )
    if channel == ChannelType.DINGTALK:
        provider = settings["dingtalk"]
        return (
            provider.get("webhook_secret"),
            str(provider.get("webhook_secret_header") or DEFAULT_WEBHOOK_SECRET_HEADER),
            str(provider.get("webhook_secret_query_param") or DEFAULT_WEBHOOK_SECRET_QUERY_PARAM),
        )
    return None, DEFAULT_WEBHOOK_SECRET_HEADER, DEFAULT_WEBHOOK_SECRET_QUERY_PARAM


def _channel_enabled(channel: ChannelType) -> bool:
    settings = get_channel_integration_runtime_settings()
    if channel == ChannelType.TELEGRAM:
        return bool(settings["telegram"].get("enabled", True))
    if channel == ChannelType.WECOM:
        return bool(settings["wecom"].get("enabled", True))
    if channel == ChannelType.FEISHU:
        return bool(settings["feishu"].get("enabled", True))
    if channel == ChannelType.DINGTALK:
        return bool(settings["dingtalk"].get("enabled", True))
    return True


def _validate_channel_secret(
    *,
    channel: ChannelType,
    request: Request,
) -> None:
    configured_secret, header_name, query_param = _configured_channel_secret(channel)
    if not configured_secret:
        return

    header_token = request.headers.get(header_name)
    query_token = request.query_params.get(query_param)
    if configured_secret in {header_token, query_token}:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Invalid {_channel_secret_error_label(channel)} webhook secret",
    )


def _ingest_channel_webhook_route(
    *,
    channel: ChannelType,
    request: Request,
    payload: dict[str, Any],
) -> IngestMessageResponse:
    if not _channel_enabled(channel):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{channel.value} channel integration is disabled",
        )

    route_key = f"channel:{channel.value}"
    enforce_webhook_rate_limit(request=request, route_key=route_key)
    enforce_webhook_payload_size(
        request=request,
        route_key=route_key,
        payload=payload,
    )
    _validate_channel_secret(channel=channel, request=request)

    try:
        result = ingest_channel_webhook(channel.value, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return IngestMessageResponse(**result)


def _workflow_webhook_user_key(request: Request, trigger_path: str) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        client_host = forwarded_for.split(",", maxsplit=1)[0].strip() or "unknown"
    elif request.client is not None and request.client.host:
        client_host = str(request.client.host)
    else:
        client_host = "unknown"
    normalized_path = str(trigger_path or "").strip("/") or "root"
    return f"workflow_webhook:{normalized_path}:{client_host}"


def _workflow_webhook_security_text(trigger_path: str, payload: dict[str, Any] | None) -> str:
    summarized_payload = {
        "trigger_path": f"/{str(trigger_path or '').strip('/')}",
        "payload": sanitize_webhook_payload(payload or {}),
    }
    return json.dumps(summarized_payload, ensure_ascii=False, sort_keys=True)


@router.post("/telegram", response_model=IngestMessageResponse)
def telegram_webhook_route(
    request: Request,
    payload: TelegramWebhookUpdate,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> IngestMessageResponse:
    if not _channel_enabled(ChannelType.TELEGRAM):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram channel integration is disabled",
        )

    route_key = "channel:telegram"
    enforce_webhook_rate_limit(request=request, route_key=route_key)
    enforce_webhook_payload_size(
        request=request,
        route_key=route_key,
        payload=payload.model_dump(by_alias=True),
    )
    configured_secret = get_channel_integration_runtime_settings()["telegram"].get("webhook_secret")
    if configured_secret and x_telegram_bot_api_secret_token != configured_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram webhook secret",
        )

    try:
        result = ingest_telegram_webhook(payload.model_dump(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return IngestMessageResponse(**result)


@router.post("/wecom", response_model=IngestMessageResponse)
def wecom_webhook_route(request: Request, payload: dict[str, Any]) -> IngestMessageResponse:
    return _ingest_channel_webhook_route(
        channel=ChannelType.WECOM,
        request=request,
        payload=payload,
    )


@router.post("/feishu", response_model=IngestMessageResponse)
def feishu_webhook_route(request: Request, payload: dict[str, Any]) -> IngestMessageResponse:
    return _ingest_channel_webhook_route(
        channel=ChannelType.FEISHU,
        request=request,
        payload=payload,
    )


@router.post("/dingtalk", response_model=IngestMessageResponse)
def dingtalk_webhook_route(request: Request, payload: dict[str, Any]) -> IngestMessageResponse:
    return _ingest_channel_webhook_route(
        channel=ChannelType.DINGTALK,
        request=request,
        payload=payload,
    )


@router.post("/workflows/{trigger_path:path}", response_model=WorkflowActionResponse)
def workflow_webhook_route(
    request: Request,
    trigger_path: str,
    payload: dict[str, Any] | None = None,
) -> WorkflowActionResponse:
    route_key = "workflow"
    normalized_payload = payload or {}
    enforce_webhook_rate_limit(request=request, route_key=route_key)
    enforce_webhook_payload_size(
        request=request,
        route_key=route_key,
        payload=normalized_payload,
    )
    security_gateway_service.inspect_text_entrypoint(
        text=_workflow_webhook_security_text(trigger_path, normalized_payload),
        user_key=_workflow_webhook_user_key(request, trigger_path),
        auth_scope="webhook:workflow",
    )
    return WorkflowActionResponse(**trigger_workflow_webhook(trigger_path, normalized_payload))
