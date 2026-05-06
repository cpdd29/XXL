from __future__ import annotations

from app.modules.knowledge.schemas import KnowledgeChunk
from app.modules.knowledge.storage.system_setting_store_utils import (
    normalize_text,
    read_json_list_setting,
    write_json_list_setting,
)


KNOWLEDGE_CHUNKS_SETTING_KEY = "knowledge_chunks"


def _coerce_chunk(payload: object) -> KnowledgeChunk | None:
    if not isinstance(payload, dict):
        return None
    chunk_id = normalize_text(payload.get("chunk_id") or payload.get("chunkId"))
    document_id = normalize_text(payload.get("document_id") or payload.get("documentId"))
    vault_id = normalize_text(payload.get("vault_id") or payload.get("vaultId"))
    title = normalize_text(payload.get("title"))
    content = str(payload.get("content") or "")
    source_path = normalize_text(payload.get("source_path") or payload.get("sourcePath"))
    if not chunk_id or not document_id or not vault_id or not title or not content or not source_path:
        return None
    try:
        return KnowledgeChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            vault_id=vault_id,
            tenant_id=normalize_text(payload.get("tenant_id") or payload.get("tenantId")) or None,
            scope=normalize_text(payload.get("scope") or "tenant") or "tenant",
            title=title,
            heading_path=normalize_text(payload.get("heading_path") or payload.get("headingPath")) or None,
            summary=normalize_text(payload.get("summary")) or None,
            content=content,
            tags=[
                str(item).strip()
                for item in (payload.get("tags") or [])
                if str(item).strip()
            ],
            source_path=source_path,
            chunk_index=max(int(payload.get("chunk_index") or payload.get("chunkIndex") or 0), 0),
            token_estimate=int(payload.get("token_estimate") or payload.get("tokenEstimate") or 0) or None,
            embedding_status=normalize_text(payload.get("embedding_status") or payload.get("embeddingStatus") or "pending") or "pending",
            created_at=normalize_text(payload.get("created_at") or payload.get("createdAt")) or None,
            updated_at=normalize_text(payload.get("updated_at") or payload.get("updatedAt")) or None,
        )
    except Exception:
        return None


class SystemSettingKnowledgeChunkStore:
    """基于 system_settings 的知识切片存储。"""

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
        normalized_document_id = normalize_text(document_id) or None
        normalized_vault_id = normalize_text(vault_id) or None
        normalized_tenant_id = normalize_text(tenant_id) or None
        normalized_scope = normalize_text(scope).lower() or None

        items: list[KnowledgeChunk] = []
        for payload in read_json_list_setting(KNOWLEDGE_CHUNKS_SETTING_KEY):
            chunk = _coerce_chunk(payload)
            if chunk is None:
                continue
            if normalized_document_id and chunk.document_id != normalized_document_id:
                continue
            if normalized_vault_id and chunk.vault_id != normalized_vault_id:
                continue
            if normalized_tenant_id and chunk.tenant_id != normalized_tenant_id:
                continue
            if normalized_scope and chunk.scope != normalized_scope:
                continue
            items.append(chunk)
        items.sort(key=lambda item: (item.document_id.lower(), item.chunk_index))
        return items[offset : offset + max(limit, 0)]

    def count_chunks(
        self,
        *,
        document_id: str | None = None,
        vault_id: str | None = None,
        tenant_id: str | None = None,
        scope: str | None = None,
    ) -> int:
        return len(
            self.list_chunks(
                document_id=document_id,
                vault_id=vault_id,
                tenant_id=tenant_id,
                scope=scope,
                limit=1000000,
                offset=0,
            )
        )

    def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        normalized_chunk_id = normalize_text(chunk_id)
        if not normalized_chunk_id:
            return None
        for chunk in self.list_chunks(limit=1000000, offset=0):
            if chunk.chunk_id == normalized_chunk_id:
                return chunk
        return None

    def replace_chunks_for_document(
        self,
        *,
        document_id: str,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        normalized_document_id = normalize_text(document_id)
        items = [
            item
            for item in read_json_list_setting(KNOWLEDGE_CHUNKS_SETTING_KEY)
            if normalize_text(item.get("document_id") or item.get("documentId")) != normalized_document_id
        ]
        items.extend(chunk.model_dump(mode="json", by_alias=False) for chunk in chunks)
        write_json_list_setting(KNOWLEDGE_CHUNKS_SETTING_KEY, items)
        return chunks

    def delete_chunks_for_document(self, document_id: str) -> int:
        normalized_document_id = normalize_text(document_id)
        original = read_json_list_setting(KNOWLEDGE_CHUNKS_SETTING_KEY)
        filtered = [
            item
            for item in original
            if normalize_text(item.get("document_id") or item.get("documentId")) != normalized_document_id
        ]
        deleted_count = len(original) - len(filtered)
        if deleted_count > 0:
            write_json_list_setting(KNOWLEDGE_CHUNKS_SETTING_KEY, filtered)
        return deleted_count


system_setting_knowledge_chunk_store = SystemSettingKnowledgeChunkStore()
