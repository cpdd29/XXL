from typing import Any, Literal

from pydantic import Field

from app.schemas.base import APIModel


EventJournalStatus = Literal["pending", "published", "failed_publish", "replayed"]


class EventJournalItem(APIModel):
    event_id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    subject: str
    event_name: str
    event_version: str
    message_type: str
    status: EventJournalStatus
    aggregate: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    routing: dict[str, Any] = Field(default_factory=dict)
    timing: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] | None = None
    target: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    publish_error: str | None = None
    replayed_from_event_id: str | None = None
    created_at: str
    updated_at: str


class EventJournalListResponse(APIModel):
    items: list[EventJournalItem]
    total: int


class EventDeadLetterItem(APIModel):
    id: str
    tenant_id: str | None = None
    project_id: str | None = None
    environment: str | None = None
    event_id: str
    subject: str
    event_name: str
    failure_stage: Literal["publish", "consume"]
    error: str
    attempt_count: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    resolved_at: str | None = None


class EventDeadLetterListResponse(APIModel):
    items: list[EventDeadLetterItem]
    total: int


class ReplayEventRequest(APIModel):
    reason: str | None = None


class ReplayEventResponse(APIModel):
    ok: bool
    message: str
    source_event: EventJournalItem
    replay_event: EventJournalItem
