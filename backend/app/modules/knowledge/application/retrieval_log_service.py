from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.modules.knowledge.schemas import (
    KnowledgeRetrievalLog,
    KnowledgeRetrievalLogListResponse,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
)
from app.modules.knowledge.storage import (
    KnowledgeRetrievalLogStore,
    system_setting_knowledge_retrieval_log_store,
)
from app.platform.persistence.runtime_store import store


def _now_string() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


class KnowledgeRetrievalLogService:
    """知识检索日志服务骨架。"""

    def __init__(self, *, retrieval_log_store: KnowledgeRetrievalLogStore | None = None) -> None:
        self._retrieval_log_store = retrieval_log_store or system_setting_knowledge_retrieval_log_store

    def list_logs(
        self,
        *,
        tenant_id: str | None = None,
        scene: str | None = None,
        request_source: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> KnowledgeRetrievalLogListResponse:
        """列出知识检索日志。"""
        items = self._retrieval_log_store.list_retrieval_logs(
            tenant_id=tenant_id,
            scene=scene,
            request_source=request_source,
            trace_id=trace_id,
            limit=limit,
            offset=offset,
        )
        total = self._retrieval_log_store.count_retrieval_logs(
            tenant_id=tenant_id,
            scene=scene,
            request_source=request_source,
            trace_id=trace_id,
        )
        return KnowledgeRetrievalLogListResponse(items=items, total=total, updated_at=store.now_string())

    def build_log(
        self,
        *,
        request: KnowledgeRetrievalRequest,
        response: KnowledgeRetrievalResponse,
        request_source: str | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRetrievalLog:
        """根据一次检索请求与结果构造日志对象。"""
        top_document_ids: list[str] = []
        top_chunk_ids: list[str] = []
        top_vault_ids: list[str] = []
        hit_preview: list[dict[str, Any]] = []
        for item in response.items:
            document_id = _normalize_text(item.metadata.document_id)
            chunk_id = _normalize_text(item.metadata.chunk_id)
            vault_id = _normalize_text(getattr(item.metadata, "vault_id", None))
            if document_id and document_id not in top_document_ids:
                top_document_ids.append(document_id)
            if chunk_id and chunk_id not in top_chunk_ids:
                top_chunk_ids.append(chunk_id)
            if vault_id and vault_id not in top_vault_ids:
                top_vault_ids.append(vault_id)
            if len(hit_preview) < 3:
                hit_preview.append(
                    {
                        "title": _normalize_text(item.title) or "未命名知识片段",
                        "scope": _normalize_text(item.scope) or None,
                        "source": _normalize_text(item.source) or None,
                        "score": item.score,
                    }
                )

        return KnowledgeRetrievalLog(
            retrieval_log_id=f"retrieval-{uuid4().hex[:12]}",
            tenant_id=request.tenant_id,
            query=request.query,
            scene=request.scene,
            hit_count=response.total,
            tenant_hit_count=response.tenant_hits,
            shared_hit_count=response.shared_hits,
            top_document_ids=top_document_ids[:10],
            top_chunk_ids=top_chunk_ids[:10],
            request_source=_normalize_text(request_source or request.metadata.get("request_source")) or None,
            trace_id=_normalize_text(trace_id or request.metadata.get("trace_id")) or None,
            created_at=_now_string(),
            metadata={
                **dict(request.metadata or {}),
                **dict(response.metadata or {}),
                **dict(metadata or {}),
                "top_k_tenant": request.top_k_tenant,
                "top_k_shared": request.top_k_shared,
                "returned_hits": response.total,
                "top_vault_ids": top_vault_ids[:10],
                "hit_preview": hit_preview,
            },
        )

    def append_log(self, log: KnowledgeRetrievalLog) -> KnowledgeRetrievalLog:
        """追加知识检索日志。"""
        return self._retrieval_log_store.append_retrieval_log(log)


knowledge_retrieval_log_service = KnowledgeRetrievalLogService()
