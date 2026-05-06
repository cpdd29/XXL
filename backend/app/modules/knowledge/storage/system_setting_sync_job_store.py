from __future__ import annotations

from app.modules.knowledge.schemas import KnowledgeSyncJob
from app.modules.knowledge.storage.system_setting_store_utils import (
    clone_metadata,
    normalize_text,
    read_json_list_setting,
    write_json_list_setting,
)


KNOWLEDGE_SYNC_JOBS_SETTING_KEY = "knowledge_sync_jobs"


def _coerce_sync_job(payload: object) -> KnowledgeSyncJob | None:
    if not isinstance(payload, dict):
        return None
    sync_job_id = normalize_text(payload.get("sync_job_id") or payload.get("syncJobId"))
    vault_id = normalize_text(payload.get("vault_id") or payload.get("vaultId"))
    if not sync_job_id or not vault_id:
        return None
    try:
        return KnowledgeSyncJob(
            sync_job_id=sync_job_id,
            vault_id=vault_id,
            tenant_id=normalize_text(payload.get("tenant_id") or payload.get("tenantId")) or None,
            trigger_type=normalize_text(payload.get("trigger_type") or payload.get("triggerType") or "manual") or "manual",
            status=normalize_text(payload.get("status") or "running") or "running",
            scanned_files=max(int(payload.get("scanned_files") or payload.get("scannedFiles") or 0), 0),
            added_files=max(int(payload.get("added_files") or payload.get("addedFiles") or 0), 0),
            updated_files=max(int(payload.get("updated_files") or payload.get("updatedFiles") or 0), 0),
            deleted_files=max(int(payload.get("deleted_files") or payload.get("deletedFiles") or 0), 0),
            added_chunks=max(int(payload.get("added_chunks") or payload.get("addedChunks") or 0), 0),
            updated_chunks=max(int(payload.get("updated_chunks") or payload.get("updatedChunks") or 0), 0),
            deleted_chunks=max(int(payload.get("deleted_chunks") or payload.get("deletedChunks") or 0), 0),
            started_at=normalize_text(payload.get("started_at") or payload.get("startedAt")) or None,
            finished_at=normalize_text(payload.get("finished_at") or payload.get("finishedAt")) or None,
            error_message=normalize_text(payload.get("error_message") or payload.get("errorMessage")) or None,
            metadata=clone_metadata(payload.get("metadata")),
        )
    except Exception:
        return None


class SystemSettingKnowledgeSyncJobStore:
    """基于 system_settings 的知识同步任务存储。"""

    def list_sync_jobs(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeSyncJob]:
        normalized_vault_id = normalize_text(vault_id) or None
        normalized_tenant_id = normalize_text(tenant_id) or None
        normalized_status = normalize_text(status).lower() or None

        items: list[KnowledgeSyncJob] = []
        for payload in read_json_list_setting(KNOWLEDGE_SYNC_JOBS_SETTING_KEY):
            job = _coerce_sync_job(payload)
            if job is None:
                continue
            if normalized_vault_id and job.vault_id != normalized_vault_id:
                continue
            if normalized_tenant_id and job.tenant_id != normalized_tenant_id:
                continue
            if normalized_status and job.status != normalized_status:
                continue
            items.append(job)
        items.sort(key=lambda item: (item.started_at or "", item.sync_job_id), reverse=True)
        return items[offset : offset + max(limit, 0)]

    def count_sync_jobs(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
    ) -> int:
        return len(
            self.list_sync_jobs(
                vault_id=vault_id,
                tenant_id=tenant_id,
                status=status,
                limit=1000000,
                offset=0,
            )
        )

    def get_sync_job(self, sync_job_id: str) -> KnowledgeSyncJob | None:
        normalized_sync_job_id = normalize_text(sync_job_id)
        if not normalized_sync_job_id:
            return None
        for job in self.list_sync_jobs(limit=1000000, offset=0):
            if job.sync_job_id == normalized_sync_job_id:
                return job
        return None

    def save_sync_job(self, job: KnowledgeSyncJob) -> KnowledgeSyncJob:
        items = [
            item
            for item in read_json_list_setting(KNOWLEDGE_SYNC_JOBS_SETTING_KEY)
            if normalize_text(item.get("sync_job_id") or item.get("syncJobId")) != job.sync_job_id
        ]
        items.append(job.model_dump(mode="json", by_alias=False))
        write_json_list_setting(KNOWLEDGE_SYNC_JOBS_SETTING_KEY, items)
        return job


system_setting_knowledge_sync_job_store = SystemSettingKnowledgeSyncJobStore()
