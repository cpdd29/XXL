from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status

from app.modules.organization.application.tenancy_service import resolve_scope
from app.platform.audit.event_journal_service import get_event, list_dead_letters, list_events, replay_event
from app.platform.audit.schemas.events import (
    EventDeadLetterListResponse,
    EventJournalItem,
    EventJournalListResponse,
    ReplayEventRequest,
    ReplayEventResponse,
)
from app.platform.auth.authz import require_authenticated_user, require_permission

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "",
    response_model=EventJournalListResponse,
    dependencies=[Depends(require_permission("events:read"))],
)
def list_events_route(
    subject: str | None = Query(default=None),
    message_type: str | None = Query(default=None, alias="messageType"),
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> EventJournalListResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return EventJournalListResponse(
        **list_events(subject=subject, message_type=message_type, limit=limit, scope=scope)
    )


@router.get(
    "/{event_id}",
    response_model=EventJournalItem,
    dependencies=[Depends(require_permission("events:read"))],
)
def get_event_route(
    event_id: str,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> EventJournalItem:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    event = get_event(event_id, scope=scope)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventJournalItem(**event)


@router.get(
    "/dead-letters",
    response_model=EventDeadLetterListResponse,
    dependencies=[Depends(require_permission("events:read"))],
)
def list_dead_letters_route(
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> EventDeadLetterListResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    return EventDeadLetterListResponse(**list_dead_letters(limit=limit, scope=scope))


@router.post(
    "/{event_id}/replay",
    response_model=ReplayEventResponse,
    dependencies=[Depends(require_permission("events:write"))],
)
def replay_event_route(
    event_id: str,
    payload: ReplayEventRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-WorkBot-Tenant-Id"),
    project_id: str | None = Header(default=None, alias="X-WorkBot-Project-Id"),
    environment: str | None = Header(default=None, alias="X-WorkBot-Environment"),
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ReplayEventResponse:
    scope = resolve_scope(
        current_user=current_user,
        tenant_id=tenant_id,
        project_id=project_id,
        environment=environment,
    )
    result = replay_event(
        event_id,
        actor=_operator_identity(current_user),
        reason=(payload or ReplayEventRequest()).reason,
        scope=scope,
    )
    return ReplayEventResponse(
        ok=True,
        message="Event replay accepted",
        source_event=EventJournalItem(**result["source_event"]),
        replay_event=EventJournalItem(**result["replay_event"]),
    )
