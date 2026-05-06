from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


KnowledgeSyncTriggerType = Literal["manual", "scheduled"]
KnowledgeSyncJobStatus = Literal["running", "success", "failed", "partial", "cancelled"]


class KnowledgeSyncJob(APIModel):
    sync_job_id: str
    vault_id: str
    tenant_id: str | None = None
    trigger_type: KnowledgeSyncTriggerType = "manual"
    status: KnowledgeSyncJobStatus = "running"
    scanned_files: int = 0
    added_files: int = 0
    updated_files: int = 0
    deleted_files: int = 0
    added_chunks: int = 0
    updated_chunks: int = 0
    deleted_chunks: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateKnowledgeSyncJobRequest(APIModel):
    vault_id: str
    trigger_type: KnowledgeSyncTriggerType = "manual"
    force_full_scan: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSyncJobListResponse(APIModel):
    items: list[KnowledgeSyncJob] = Field(default_factory=list)
    total: int = 0
    updated_at: str | None = None


class KnowledgeSyncJobActionResponse(APIModel):
    ok: bool
    message: str
    job: KnowledgeSyncJob

