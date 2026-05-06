from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any
from uuid import uuid4

from app.modules.knowledge.adapters import obsidian_filesystem_adapter
from app.modules.knowledge.application.chunk_service import knowledge_chunk_service
from app.modules.knowledge.application.parser_service import knowledge_parser_service
from app.modules.knowledge.application.vault_registry_service import knowledge_vault_registry_service
from app.modules.knowledge.schemas import (
    CreateKnowledgeSyncJobRequest,
    KnowledgeDocument,
    KnowledgeSyncJob,
    KnowledgeSyncJobActionResponse,
    KnowledgeSyncJobListResponse,
)
from app.modules.knowledge.storage import (
    KnowledgeChunkStore,
    KnowledgeDocumentStore,
    KnowledgeSyncJobStore,
    KnowledgeVaultStore,
    system_setting_knowledge_chunk_store,
    system_setting_knowledge_document_store,
    system_setting_knowledge_sync_job_store,
    system_setting_knowledge_vault_store,
)
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log
from app.platform.observability.operational_log_service import append_realtime_event
from app.platform.persistence.runtime_store import store


def _now_string() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _stable_document_id(*, vault_id: str, source_path: str) -> str:
    payload = f"{vault_id}|{source_path}"
    return f"doc-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]}"


class KnowledgeSyncService:
    """知识仓同步编排服务骨架。"""

    def __init__(
        self,
        *,
        vault_store: KnowledgeVaultStore | None = None,
        document_store: KnowledgeDocumentStore | None = None,
        chunk_store: KnowledgeChunkStore | None = None,
        sync_job_store: KnowledgeSyncJobStore | None = None,
    ) -> None:
        self._vault_store = vault_store or system_setting_knowledge_vault_store
        self._document_store = document_store or system_setting_knowledge_document_store
        self._chunk_store = chunk_store or system_setting_knowledge_chunk_store
        self._sync_job_store = sync_job_store or system_setting_knowledge_sync_job_store

    def list_sync_jobs(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> KnowledgeSyncJobListResponse:
        """列出知识同步任务。"""
        items = self._sync_job_store.list_sync_jobs(
            vault_id=vault_id,
            tenant_id=tenant_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        total = self._sync_job_store.count_sync_jobs(
            vault_id=vault_id,
            tenant_id=tenant_id,
            status=status,
        )
        return KnowledgeSyncJobListResponse(items=items, total=total, updated_at=store.now_string())

    def get_sync_job(self, sync_job_id: str) -> KnowledgeSyncJob | None:
        """读取单个知识同步任务。"""
        return self._sync_job_store.get_sync_job(sync_job_id)

    def create_sync_job(self, payload: CreateKnowledgeSyncJobRequest) -> KnowledgeSyncJobActionResponse:
        """创建知识同步任务记录。"""
        vault = self._vault_store.get_vault(payload.vault_id)
        if vault is None:
            raise KeyError(f"Knowledge vault '{payload.vault_id}' not found")

        job = KnowledgeSyncJob(
            sync_job_id=f"sync-{uuid4().hex[:12]}",
            vault_id=vault.vault_id,
            tenant_id=vault.tenant_id,
            trigger_type=payload.trigger_type,
            status="running",
            started_at=_now_string(),
            metadata={
                **dict(payload.metadata or {}),
                "force_full_scan": bool(payload.force_full_scan),
                "vault_name": vault.vault_name,
                "vault_path": vault.local_path,
            },
        )
        saved = self._sync_job_store.save_sync_job(job)
        knowledge_vault_registry_service.mark_sync_status(
            vault_id=vault.vault_id,
            status="running",
            last_sync_at=saved.started_at,
        )
        append_realtime_event(
            agent="Knowledge Sync",
            message=f"知识仓开始同步：{vault.vault_name}",
            type_="info",
            source="knowledge_sync",
            trace_id=_normalize_text(saved.metadata.get("trace_id")),
            metadata={
                "event": "knowledge_sync_started",
                "vault_id": vault.vault_id,
                "vault_name": vault.vault_name,
                "tenant_id": vault.tenant_id,
                "tenant_name": vault.tenant_name,
                "trigger_type": saved.trigger_type,
                "sync_job_id": saved.sync_job_id,
            },
        )
        return KnowledgeSyncJobActionResponse(ok=True, message="知识同步任务已创建", job=saved)

    def run_sync_job(self, sync_job_id: str) -> KnowledgeSyncJobActionResponse:
        """执行已创建的知识同步任务。"""
        job = self._sync_job_store.get_sync_job(sync_job_id)
        if job is None:
            raise KeyError(f"Knowledge sync job '{sync_job_id}' not found")

        vault = self._vault_store.get_vault(job.vault_id)
        if vault is None:
            raise KeyError(f"Knowledge vault '{job.vault_id}' not found")

        running_job = job.model_copy(
            update={
                "status": "running",
                "started_at": job.started_at or _now_string(),
                "finished_at": None,
                "error_message": None,
            }
        )
        self._sync_job_store.save_sync_job(running_job)

        try:
            existing_documents = self._document_store.list_documents(
                vault_id=vault.vault_id,
                limit=1000000,
                offset=0,
            )
            existing_by_path = {item.source_path: item for item in existing_documents}
            active_paths: set[str] = set()

            scan_result = obsidian_filesystem_adapter.scan_vault(vault.local_path)
            stats = {
                "scanned_files": scan_result.file_count,
                "added_files": 0,
                "updated_files": 0,
                "deleted_files": 0,
                "added_chunks": 0,
                "updated_chunks": 0,
                "deleted_chunks": 0,
            }

            for item in scan_result.items:
                active_paths.add(item.relative_path)
                existing = existing_by_path.get(item.relative_path)
                existing_checksum = _normalize_text(existing.checksum) if existing is not None else None
                changed = existing is None or existing_checksum != item.checksum or existing.status != "active"
                if not changed:
                    continue

                document = knowledge_parser_service.build_document(
                    document_id=existing.document_id if existing is not None else _stable_document_id(
                        vault_id=vault.vault_id,
                        source_path=item.relative_path,
                    ),
                    vault_id=vault.vault_id,
                    tenant_id=vault.tenant_id,
                    scope=vault.vault_type,
                    source_path=item.relative_path,
                    file_name=item.file_name,
                    raw_markdown=item.raw_markdown,
                    checksum=item.checksum,
                    source_updated_at=item.updated_at,
                )
                if existing is not None:
                    document = self._merge_existing_document(existing=existing, current=document)

                self._document_store.save_document(document)
                chunks = knowledge_chunk_service.build_chunks(document=document)
                previous_chunk_count = self._chunk_store.count_chunks(document_id=document.document_id)
                self._chunk_store.replace_chunks_for_document(document_id=document.document_id, chunks=chunks)
                if existing is None:
                    stats["added_files"] += 1
                    stats["added_chunks"] += len(chunks)
                else:
                    stats["updated_files"] += 1
                    stats["updated_chunks"] += max(len(chunks), previous_chunk_count)

            for existing in existing_documents:
                if existing.source_path in active_paths:
                    continue
                self._document_store.mark_document_deleted(existing.document_id)
                deleted_chunks = self._chunk_store.delete_chunks_for_document(existing.document_id)
                stats["deleted_files"] += 1
                stats["deleted_chunks"] += deleted_chunks

            finished_job = running_job.model_copy(
                update={
                    **stats,
                    "status": "success",
                    "finished_at": _now_string(),
                    "metadata": {
                        **dict(running_job.metadata or {}),
                        "scan_file_count": scan_result.file_count,
                    },
                }
            )
            saved = self._sync_job_store.save_sync_job(finished_job)
            knowledge_vault_registry_service.mark_sync_status(
                vault_id=vault.vault_id,
                status="success",
                last_sync_at=saved.finished_at,
            )
            self._append_sync_audit(
                action="knowledge.vault.sync.completed",
                vault=vault,
                job=saved,
                details=f"知识仓同步完成：{vault.vault_name}",
            )
            self._append_sync_realtime_event(
                vault=vault,
                job=saved,
                message=f"知识仓同步完成：{vault.vault_name}",
                type_="success",
                event="knowledge_sync_completed",
            )
            return KnowledgeSyncJobActionResponse(ok=True, message="知识仓同步完成", job=saved)
        except Exception as exc:
            failed_job = running_job.model_copy(
                update={
                    "status": "failed",
                    "finished_at": _now_string(),
                    "error_message": str(exc),
                }
            )
            saved = self._sync_job_store.save_sync_job(failed_job)
            knowledge_vault_registry_service.mark_sync_status(
                vault_id=vault.vault_id,
                status="failed",
                last_sync_at=saved.finished_at,
            )
            self._append_sync_audit(
                action="knowledge.vault.sync.failed",
                vault=vault,
                job=saved,
                details=f"知识仓同步失败：{vault.vault_name}",
            )
            self._append_sync_realtime_event(
                vault=vault,
                job=saved,
                message=f"知识仓同步失败：{vault.vault_name}",
                type_="error",
                event="knowledge_sync_failed",
            )
            return KnowledgeSyncJobActionResponse(ok=False, message="知识仓同步失败", job=saved)

    def sync_vault(
        self,
        *,
        vault_id: str,
        trigger_type: str = "manual",
        force_full_scan: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeSyncJobActionResponse:
        """为指定知识仓创建并执行一次同步。"""
        created = self.create_sync_job(
            CreateKnowledgeSyncJobRequest(
                vault_id=vault_id,
                trigger_type=trigger_type,
                force_full_scan=force_full_scan,
                metadata=dict(metadata or {}),
            )
        )
        return self.run_sync_job(created.job.sync_job_id)

    def _merge_existing_document(
        self,
        *,
        existing: KnowledgeDocument,
        current: KnowledgeDocument,
    ) -> KnowledgeDocument:
        changed = (
            existing.checksum != current.checksum
            or existing.normalized_text != current.normalized_text
            or existing.title != current.title
            or existing.tags != current.tags
            or existing.aliases != current.aliases
            or existing.category != current.category
        )
        return current.model_copy(
            update={
                "created_at": existing.created_at or current.created_at,
                "updated_at": _now_string(),
                "version": existing.version + (1 if changed else 0),
            }
        )

    def _append_sync_audit(
        self,
        *,
        action: str,
        vault,
        job: KnowledgeSyncJob,
        details: str,
    ) -> None:
        append_control_plane_audit_log(
            action=action,
            user=_normalize_text((job.metadata or {}).get("operator_user")) or "system",
            resource=f"knowledge.vault.{vault.vault_id}",
            details=details,
            metadata={
                "vault_id": vault.vault_id,
                "vault_name": vault.vault_name,
                "tenant_id": vault.tenant_id,
                "tenant_name": vault.tenant_name,
                "trigger_type": job.trigger_type,
                "sync_job_id": job.sync_job_id,
                "status": job.status,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "scanned_files": job.scanned_files,
                "added_files": job.added_files,
                "updated_files": job.updated_files,
                "deleted_files": job.deleted_files,
                "added_chunks": job.added_chunks,
                "updated_chunks": job.updated_chunks,
                "deleted_chunks": job.deleted_chunks,
                "error_message": job.error_message,
            },
        )

    def _append_sync_realtime_event(
        self,
        *,
        vault,
        job: KnowledgeSyncJob,
        message: str,
        type_: str,
        event: str,
    ) -> None:
        append_realtime_event(
            agent="Knowledge Sync",
            message=message,
            type_=type_,
            source="knowledge_sync",
            trace_id=_normalize_text((job.metadata or {}).get("trace_id")) or None,
            metadata={
                "event": event,
                "vault_id": vault.vault_id,
                "vault_name": vault.vault_name,
                "tenant_id": vault.tenant_id,
                "tenant_name": vault.tenant_name,
                "trigger_type": job.trigger_type,
                "sync_job_id": job.sync_job_id,
                "status": job.status,
                "error_message": job.error_message,
            },
        )


knowledge_sync_service = KnowledgeSyncService()
