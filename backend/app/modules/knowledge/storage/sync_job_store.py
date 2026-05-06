from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.schemas import KnowledgeSyncJob


class KnowledgeSyncJobStore(Protocol):
    def list_sync_jobs(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeSyncJob]:
        ...

    def count_sync_jobs(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
    ) -> int:
        ...

    def get_sync_job(self, sync_job_id: str) -> KnowledgeSyncJob | None:
        ...

    def save_sync_job(self, job: KnowledgeSyncJob) -> KnowledgeSyncJob:
        ...

