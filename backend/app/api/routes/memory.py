from fastapi import APIRouter, Depends, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.memory import (
    DistillMemoryRequest,
    DistillMemoryResponse,
    IngestMemoryMessageRequest,
    IngestMemoryMessageResponse,
    MemoryLayersResponse,
    MemoryMessagesResponse,
    MemoryRetrieveResponse,
)
from app.services.memory_service import memory_service

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.post(
    "/messages",
    response_model=IngestMemoryMessageResponse,
    dependencies=[Depends(require_permission("memory:write"))],
)
def ingest_memory_message_route(
    payload: IngestMemoryMessageRequest,
) -> IngestMemoryMessageResponse:
    return IngestMemoryMessageResponse(
        **memory_service.ingest_message(
            user_id=payload.user_id,
            session_id=payload.session_id,
            role=payload.role,
            content=payload.content,
            detected_lang=payload.detected_lang,
        )
    )


@router.get(
    "/{user_id}/layers",
    response_model=MemoryLayersResponse,
    dependencies=[Depends(require_permission("memory:read"))],
)
def get_memory_layers_route(user_id: str) -> MemoryLayersResponse:
    return MemoryLayersResponse(**memory_service.get_layers(user_id))


@router.get(
    "/{user_id}/messages",
    response_model=MemoryMessagesResponse,
    dependencies=[Depends(require_permission("memory:read"))],
)
def list_memory_messages_route(
    user_id: str,
    session_id: str | None = Query(default=None, alias="sessionId"),
    limit: int = Query(default=20, ge=1, le=100),
) -> MemoryMessagesResponse:
    return MemoryMessagesResponse(
        **memory_service.list_messages(
            user_id,
            session_id=session_id,
            limit=limit,
        )
    )


@router.post(
    "/{user_id}/distill",
    response_model=DistillMemoryResponse,
    dependencies=[Depends(require_permission("memory:write"))],
)
def distill_user_memory_route(
    user_id: str,
    payload: DistillMemoryRequest,
) -> DistillMemoryResponse:
    return DistillMemoryResponse(
        **memory_service.distill(
            user_id=user_id,
            trigger=payload.trigger,
            session_id=payload.session_id,
        )
    )


@router.get(
    "/{user_id}/retrieve",
    response_model=MemoryRetrieveResponse,
    dependencies=[Depends(require_permission("memory:read"))],
)
def retrieve_memory_route(
    user_id: str,
    query: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
) -> MemoryRetrieveResponse:
    return MemoryRetrieveResponse(**memory_service.retrieve(user_id=user_id, query=query, limit=limit))
