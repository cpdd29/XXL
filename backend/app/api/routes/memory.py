from fastapi import APIRouter, Depends, Header, Query

from app.core.authz import require_authenticated_user, require_permission
from app.schemas.memory import (
    DistillMemoryRequest,
    DistillMemoryResponse,
    IngestMemoryMessageRequest,
    IngestMemoryMessageResponse,
    MemoryAuditResponse,
    MemoryLifecycleResponse,
    MemoryLayersResponse,
    MemoryMessagesResponse,
    MemoryRetrieveResponse,
    ReviewMemoryRequest,
    ReviewMemoryResponse,
)
from app.services.memory_service import memory_service
from app.services.tenancy_service import resolve_scope

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.post(
    "/messages",
    response_model=IngestMemoryMessageResponse,
    dependencies=[Depends(require_permission("memory:write"))],
)
def ingest_memory_message_route(
    payload: IngestMemoryMessageRequest,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> IngestMemoryMessageResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return IngestMemoryMessageResponse(
        **memory_service.ingest_message(
            user_id=payload.user_id,
            session_id=payload.session_id,
            role=payload.role,
            content=payload.content,
            detected_lang=payload.detected_lang,
            scope=scope,
            write_source=payload.write_source,
            trust_level=payload.trust_level,
            memory_scope=payload.memory_scope,
        )
    )


@router.get(
    "/{user_id}/layers",
    response_model=MemoryLayersResponse,
    dependencies=[Depends(require_permission("memory:read"))],
)
def get_memory_layers_route(
    user_id: str,
    memory_scope: str | None = Query(default=None, alias="memoryScope"),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> MemoryLayersResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return MemoryLayersResponse(**memory_service.get_layers(user_id, scope=scope, memory_scope=memory_scope))


@router.get(
    "/{user_id}/messages",
    response_model=MemoryMessagesResponse,
    dependencies=[Depends(require_permission("memory:read"))],
)
def list_memory_messages_route(
    user_id: str,
    session_id: str | None = Query(default=None, alias="sessionId"),
    memory_scope: str | None = Query(default=None, alias="memoryScope"),
    limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> MemoryMessagesResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return MemoryMessagesResponse(
        **memory_service.list_messages(
            user_id,
            session_id=session_id,
            limit=limit,
            scope=scope,
            memory_scope=memory_scope,
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
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> DistillMemoryResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return DistillMemoryResponse(
        **memory_service.distill(
            user_id=user_id,
            trigger=payload.trigger,
            session_id=payload.session_id,
            scope=scope,
            write_source=payload.write_source,
            trust_level=payload.trust_level,
            memory_scope=payload.memory_scope,
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
    include_untrusted: bool = Query(default=False, alias="includeUntrusted"),
    memory_scope: str | None = Query(default=None, alias="memoryScope"),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> MemoryRetrieveResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return MemoryRetrieveResponse(
        **memory_service.retrieve(
            user_id=user_id,
            query=query,
            limit=limit,
            scope=scope,
            include_untrusted=include_untrusted,
            memory_scope=memory_scope,
        )
    )


@router.get(
    "/{user_id}/audit",
    response_model=MemoryAuditResponse,
    dependencies=[Depends(require_permission("memory:read"))],
)
def memory_audit_route(
    user_id: str,
    include_inactive: bool = Query(default=True, alias="includeInactive"),
    memory_scope: str | None = Query(default=None, alias="memoryScope"),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> MemoryAuditResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return MemoryAuditResponse(
        **memory_service.audit_memories(
            user_id=user_id,
            scope=scope,
            include_inactive=include_inactive,
            memory_scope=memory_scope,
        )
    )


@router.post(
    "/{user_id}/long-term/{memory_id}/review",
    response_model=ReviewMemoryResponse,
    dependencies=[Depends(require_permission("memory:write"))],
)
def review_memory_route(
    user_id: str,
    memory_id: str,
    payload: ReviewMemoryRequest,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> ReviewMemoryResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return ReviewMemoryResponse(
        **memory_service.review_memory(
            user_id=user_id,
            memory_id=memory_id,
            action=payload.action,
            note=payload.note,
            corrected_memory_text=payload.corrected_memory_text,
            corrected_summary=payload.corrected_summary,
            reviewed_by=str(current_user.get("email") or current_user.get("id") or "system"),
            scope=scope,
        )
    )


@router.post(
    "/{user_id}/lifecycle/apply",
    response_model=MemoryLifecycleResponse,
    dependencies=[Depends(require_permission("memory:write"))],
)
def apply_memory_lifecycle_route(
    user_id: str,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict = Depends(require_authenticated_user),
) -> MemoryLifecycleResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return MemoryLifecycleResponse(**memory_service.apply_lifecycle(user_id=user_id, scope=scope))
