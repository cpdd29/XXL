from __future__ import annotations

from fastapi import APIRouter

from app.schemas.messages import IngestMessageResponse, IngestUnifiedMessageRequest, UnifiedMessage
from app.services.message_ingestion_service import ingest_unified_message
from app.services.store import store

router = APIRouter()


@router.post("/ingest", response_model=IngestMessageResponse)
def ingest_message_route(payload: IngestUnifiedMessageRequest) -> IngestMessageResponse:
    unified_message = UnifiedMessage(
        message_id=f"manual:{payload.channel.value}:{store.now_string()}",
        channel=payload.channel,
        platform_user_id=payload.platform_user_id,
        chat_id=payload.chat_id,
        text=payload.text,
        received_at=payload.received_at or store.now_string(),
        raw_payload=payload.raw_payload or payload.model_dump(mode="json"),
        metadata=payload.metadata,
        session_id=payload.session_id,
    )
    result = ingest_unified_message(
        unified_message,
        auth_scope=payload.auth_scope,
        entrypoint="api.messages.ingest",
        entrypoint_agent="Unified Message API",
    )
    return IngestMessageResponse(**result)
