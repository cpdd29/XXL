from __future__ import annotations

from app.modules.knowledge.schemas import (
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
)
from app.modules.knowledge.storage import (
    KnowledgeChunkStore,
    KnowledgeDocumentStore,
    system_setting_knowledge_chunk_store,
    system_setting_knowledge_document_store,
)
from app.platform.persistence.runtime_store import store


class KnowledgeDocumentQueryService:
    """知识文档查询服务。"""

    def __init__(
        self,
        *,
        document_store: KnowledgeDocumentStore | None = None,
        chunk_store: KnowledgeChunkStore | None = None,
    ) -> None:
        self._document_store = document_store or system_setting_knowledge_document_store
        self._chunk_store = chunk_store or system_setting_knowledge_chunk_store

    def list_documents(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        category: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> KnowledgeDocumentListResponse:
        items = self._document_store.list_documents(
            vault_id=vault_id,
            tenant_id=tenant_id,
            scope=scope,
            status=status,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = self._document_store.count_documents(
            vault_id=vault_id,
            tenant_id=tenant_id,
            scope=scope,
            status=status,
            category=category,
            search=search,
        )
        return KnowledgeDocumentListResponse(items=items, total=total, updated_at=store.now_string())

    def get_document_detail(self, document_id: str) -> KnowledgeDocumentDetailResponse | None:
        document = self._document_store.get_document(document_id)
        if document is None:
            return None
        chunks = self._chunk_store.list_chunks(
            document_id=document.document_id,
            limit=1000000,
            offset=0,
        )
        return KnowledgeDocumentDetailResponse(document=document, chunks=chunks)


knowledge_document_query_service = KnowledgeDocumentQueryService()
