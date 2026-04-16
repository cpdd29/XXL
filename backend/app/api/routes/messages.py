from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.schemas.messages import IngestMessageResponse, IngestUnifiedMessageRequest, UnifiedMessage
from app.services.message_ingestion_service import ingest_unified_message
from app.services.store import store

router = APIRouter()


@router.post("/ingest", response_model=IngestMessageResponse)
def ingest_message_route(payload: dict[str, Any] = Body(...)) -> IngestMessageResponse:
    try:
        request_payload = IngestUnifiedMessageRequest.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    unified_message = UnifiedMessage(
        message_id=f"manual:{request_payload.channel.value}:{store.now_string()}",
        channel=request_payload.channel,
        platform_user_id=request_payload.platform_user_id,
        chat_id=request_payload.chat_id,
        text=request_payload.text,
        received_at=request_payload.received_at or store.now_string(),
        raw_payload=request_payload.raw_payload or request_payload.model_dump(mode="json"),
        metadata=request_payload.metadata,
        session_id=request_payload.session_id,
    )
    result = ingest_unified_message(
        unified_message,
        auth_scope=request_payload.auth_scope,
        entrypoint="api.messages.ingest",
        entrypoint_agent="Unified Message API",
    )
    return IngestMessageResponse(**result)
