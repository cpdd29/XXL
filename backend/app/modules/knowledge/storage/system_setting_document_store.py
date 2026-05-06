from __future__ import annotations

from app.modules.knowledge.schemas import KnowledgeDocument
from app.modules.knowledge.storage.system_setting_store_utils import (
    clone_metadata,
    normalize_text,
    read_json_list_setting,
    write_json_list_setting,
)
from app.platform.persistence.runtime_store import store


KNOWLEDGE_DOCUMENTS_SETTING_KEY = "knowledge_documents"


def _coerce_document(payload: object) -> KnowledgeDocument | None:
    if not isinstance(payload, dict):
        return None
    document_id = normalize_text(payload.get("document_id") or payload.get("documentId"))
    vault_id = normalize_text(payload.get("vault_id") or payload.get("vaultId"))
    source_path = normalize_text(payload.get("source_path") or payload.get("sourcePath"))
    file_name = normalize_text(payload.get("file_name") or payload.get("fileName"))
    title = normalize_text(payload.get("title"))
    if not document_id or not vault_id or not source_path or not file_name or not title:
        return None
    try:
        return KnowledgeDocument(
            document_id=document_id,
            vault_id=vault_id,
            tenant_id=normalize_text(payload.get("tenant_id") or payload.get("tenantId")) or None,
            scope=normalize_text(payload.get("scope") or "tenant") or "tenant",
            source_path=source_path,
            file_name=file_name,
            title=title,
            category=normalize_text(payload.get("category")) or None,
            tags=[
                str(item).strip()
                for item in (payload.get("tags") or [])
                if str(item).strip()
            ],
            aliases=[
                str(item).strip()
                for item in (payload.get("aliases") or [])
                if str(item).strip()
            ],
            raw_markdown=str(payload.get("raw_markdown") or payload.get("rawMarkdown") or ""),
            normalized_text=str(payload.get("normalized_text") or payload.get("normalizedText") or ""),
            frontmatter=clone_metadata(payload.get("frontmatter")),
            links=[
                str(item).strip()
                for item in (payload.get("links") or [])
                if str(item).strip()
            ],
            checksum=normalize_text(payload.get("checksum")) or None,
            version=max(int(payload.get("version") or 1), 1),
            status=normalize_text(payload.get("status") or "active") or "active",
            created_at=normalize_text(payload.get("created_at") or payload.get("createdAt")) or None,
            updated_at=normalize_text(payload.get("updated_at") or payload.get("updatedAt")) or None,
            source_updated_at=normalize_text(payload.get("source_updated_at") or payload.get("sourceUpdatedAt")) or None,
        )
    except Exception:
        return None


class SystemSettingKnowledgeDocumentStore:
    """基于 system_settings 的知识文档存储。"""

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
        normalized_vault_id = normalize_text(vault_id) or None
        normalized_tenant_id = normalize_text(tenant_id) or None
        normalized_scope = normalize_text(scope).lower() or None
        normalized_status = normalize_text(status).lower() or None
        normalized_category = normalize_text(category).lower() or None
        normalized_search = normalize_text(search).lower() or None

        items: list[KnowledgeDocument] = []
        for payload in read_json_list_setting(KNOWLEDGE_DOCUMENTS_SETTING_KEY):
            document = _coerce_document(payload)
            if document is None:
                continue
            if normalized_vault_id and document.vault_id != normalized_vault_id:
                continue
            if normalized_tenant_id and document.tenant_id != normalized_tenant_id:
                continue
            if normalized_scope and document.scope != normalized_scope:
                continue
            if normalized_status and document.status != normalized_status:
                continue
            if normalized_category and (document.category or "").lower() != normalized_category:
                continue
            if normalized_search:
                haystack = " ".join(
                    [
                        document.title.lower(),
                        document.source_path.lower(),
                        document.normalized_text.lower(),
                    ]
                )
                if normalized_search not in haystack:
                    continue
            items.append(document)
        items.sort(key=lambda item: (item.vault_id.lower(), item.source_path.lower()))
        return items[offset : offset + max(limit, 0)]

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
        return len(
            self.list_documents(
                vault_id=vault_id,
                tenant_id=tenant_id,
                scope=scope,
                status=status,
                category=category,
                search=search,
                limit=1000000,
                offset=0,
            )
        )

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        normalized_document_id = normalize_text(document_id)
        if not normalized_document_id:
            return None
        for document in self.list_documents(limit=1000000, offset=0):
            if document.document_id == normalized_document_id:
                return document
        return None

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        items = [
            item
            for item in read_json_list_setting(KNOWLEDGE_DOCUMENTS_SETTING_KEY)
            if normalize_text(item.get("document_id") or item.get("documentId")) != document.document_id
        ]
        items.append(document.model_dump(mode="json", by_alias=False))
        write_json_list_setting(KNOWLEDGE_DOCUMENTS_SETTING_KEY, items)
        return document

    def mark_document_deleted(self, document_id: str) -> KnowledgeDocument | None:
        current = self.get_document(document_id)
        if current is None:
            return None
        deleted = current.model_copy(update={"status": "deleted", "updated_at": store.now_string()})
        return self.save_document(deleted)

    def delete_document(self, document_id: str) -> bool:
        normalized_document_id = normalize_text(document_id)
        if not normalized_document_id:
            return False
        original = read_json_list_setting(KNOWLEDGE_DOCUMENTS_SETTING_KEY)
        filtered = [
            item
            for item in original
            if normalize_text(item.get("document_id") or item.get("documentId")) != normalized_document_id
        ]
        if len(filtered) == len(original):
            return False
        write_json_list_setting(KNOWLEDGE_DOCUMENTS_SETTING_KEY, filtered)
        return True


system_setting_knowledge_document_store = SystemSettingKnowledgeDocumentStore()
