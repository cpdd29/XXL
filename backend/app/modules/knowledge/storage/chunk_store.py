from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.schemas import KnowledgeChunk


class KnowledgeChunkStore(Protocol):
    def list_chunks(
        self,
        *,
        document_id: str | None = None,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        scope: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[KnowledgeChunk]:
        ...

    def count_chunks(
        self,
        *,
        document_id: str | None = None,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        scope: str | None = None,
    ) -> int:
        ...

    def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        ...

    def replace_chunks_for_document(
        self,
        *,
        document_id: str,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        ...

    def delete_chunks_for_document(self, document_id: str) -> int:
        ...

