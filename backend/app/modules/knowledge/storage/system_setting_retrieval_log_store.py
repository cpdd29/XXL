from __future__ import annotations

from app.modules.knowledge.schemas import KnowledgeRetrievalLog
from app.modules.knowledge.storage.system_setting_store_utils import (
    clone_metadata,
    normalize_text,
    read_json_list_setting,
    write_json_list_setting,
)


KNOWLEDGE_RETRIEVAL_LOGS_SETTING_KEY = "knowledge_retrieval_logs"


def _coerce_retrieval_log(payload: object) -> KnowledgeRetrievalLog | None:
    if not isinstance(payload, dict):
        return None

    retrieval_log_id = normalize_text(payload.get("retrieval_log_id") or payload.get("retrievalLogId"))
    tenant_id = normalize_text(payload.get("tenant_id") or payload.get("tenantId"))
    query = normalize_text(payload.get("query"))
    if not retrieval_log_id or not tenant_id or not query:
        return None

    try:
        return KnowledgeRetrievalLog(
            retrieval_log_id=retrieval_log_id,
            tenant_id=tenant_id,
            query=query,
            scene=normalize_text(payload.get("scene") or "reception") or "reception",
            hit_count=max(int(payload.get("hit_count") or payload.get("hitCount") or 0), 0),
            tenant_hit_count=max(int(payload.get("tenant_hit_count") or payload.get("tenantHitCount") or 0), 0),
            shared_hit_count=max(int(payload.get("shared_hit_count") or payload.get("sharedHitCount") or 0), 0),
            top_document_ids=[
                str(item).strip()
                for item in (payload.get("top_document_ids") or payload.get("topDocumentIds") or [])
                if str(item).strip()
            ],
            top_chunk_ids=[
                str(item).strip()
                for item in (payload.get("top_chunk_ids") or payload.get("topChunkIds") or [])
                if str(item).strip()
            ],
            request_source=normalize_text(payload.get("request_source") or payload.get("requestSource")) or None,
            trace_id=normalize_text(payload.get("trace_id") or payload.get("traceId")) or None,
            created_at=normalize_text(payload.get("created_at") or payload.get("createdAt")) or None,
            metadata=clone_metadata(payload.get("metadata")),
        )
    except Exception:
        return None


class SystemSettingKnowledgeRetrievalLogStore:
    """基于 system_settings 的知识检索日志存储。"""

    def list_retrieval_logs(
        self,
        *,
        tenant_id: str | None = None,
        scene: str | None = None,
        request_source: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeRetrievalLog]:
        normalized_tenant_id = normalize_text(tenant_id) or None
        normalized_scene = normalize_text(scene).lower() or None
        normalized_request_source = normalize_text(request_source).lower() or None
        normalized_trace_id = normalize_text(trace_id) or None

        items: list[KnowledgeRetrievalLog] = []
        for payload in read_json_list_setting(KNOWLEDGE_RETRIEVAL_LOGS_SETTING_KEY):
            log = _coerce_retrieval_log(payload)
            if log is None:
                continue
            if normalized_tenant_id and log.tenant_id != normalized_tenant_id:
                continue
            if normalized_scene and log.scene != normalized_scene:
                continue
            if normalized_request_source and (log.request_source or "").lower() != normalized_request_source:
                continue
            if normalized_trace_id and log.trace_id != normalized_trace_id:
                continue
            items.append(log)
        items.sort(key=lambda item: ((item.created_at or ""), item.retrieval_log_id), reverse=True)
        return items[offset : offset + max(limit, 0)]

    def count_retrieval_logs(
        self,
        *,
        tenant_id: str | None = None,
        scene: str | None = None,
        request_source: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        return len(
            self.list_retrieval_logs(
                tenant_id=tenant_id,
                scene=scene,
                request_source=request_source,
                trace_id=trace_id,
                limit=1000000,
                offset=0,
            )
        )

    def append_retrieval_log(self, log: KnowledgeRetrievalLog) -> KnowledgeRetrievalLog:
        items = read_json_list_setting(KNOWLEDGE_RETRIEVAL_LOGS_SETTING_KEY)
        items.append(log.model_dump(mode="json", by_alias=False))
        write_json_list_setting(KNOWLEDGE_RETRIEVAL_LOGS_SETTING_KEY, items)
        return log


system_setting_knowledge_retrieval_log_store = SystemSettingKnowledgeRetrievalLogStore()
