from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.schemas import KnowledgeDocument


class KnowledgeDocumentStore(Protocol):
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
    ) -> list[KnowledgeDocument]:
        ...

    def count_documents(
        self,
        *,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        ...

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        ...

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        ...

    def mark_document_deleted(self, document_id: str) -> KnowledgeDocument | None:
        ...

    def delete_document(self, document_id: str) -> bool:
        ...

