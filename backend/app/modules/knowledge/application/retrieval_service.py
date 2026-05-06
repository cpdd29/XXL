from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from app.modules.knowledge.schemas import (
    KnowledgeHit,
    KnowledgeHitMetadata,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
)
from app.modules.knowledge.storage import (
    KnowledgeChunkStore,
    KnowledgeDocumentStore,
    KnowledgeVaultStore,
    system_setting_knowledge_chunk_store,
    system_setting_knowledge_document_store,
    system_setting_knowledge_vault_store,
)


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")
RECEPTION_PRIORITY_TAGS = {"接待优先", "reception", "faq", "客服"}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _parse_datetime(value: object) -> datetime | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value).lower()
    if not normalized:
        return []
    items: list[str] = []
    seen: set[str] = set()
    for token in TOKEN_PATTERN.findall(normalized):
        candidate = token.strip().lower()
        if len(candidate) <= 1:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        items.append(candidate)
    return items


def _contains_any(haystack: str, tokens: list[str]) -> bool:
    return any(token in haystack for token in tokens)


class KnowledgeRetrievalService:
    """知识检索服务骨架。"""

    def __init__(
        self,
        *,
        document_store: KnowledgeDocumentStore | None = None,
        chunk_store: KnowledgeChunkStore | None = None,
        vault_store: KnowledgeVaultStore | None = None,
    ) -> None:
        self._document_store = document_store or system_setting_knowledge_document_store
        self._chunk_store = chunk_store or system_setting_knowledge_chunk_store
        self._vault_store = vault_store or system_setting_knowledge_vault_store

    def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResponse:
        """执行两段检索：先租户专用，再通用知识。"""
        query = _normalize_text(request.query)
        tenant_id = _normalize_text(request.tenant_id)
        if not tenant_id or not query:
            return KnowledgeRetrievalResponse(
                items=[],
                total=0,
                tenant_hits=0,
                shared_hits=0,
                query=query,
                scene=request.scene,
            )

        effective_tenant_vault_ids, effective_shared_vault_ids = self._resolve_effective_vault_ids(tenant_id)
        if not effective_tenant_vault_ids and not effective_shared_vault_ids:
            return KnowledgeRetrievalResponse(
                items=[],
                total=0,
                tenant_hits=0,
                shared_hits=0,
                query=query,
                scene=request.scene,
                metadata={
                    "effective_tenant_vault_ids": [],
                    "effective_shared_vault_ids": [],
                    "effective_vault_count": 0,
                },
            )

        documents = self._document_store.list_documents(
            tenant_id=tenant_id,
            status="active",
            limit=1000000,
            offset=0,
        )
        shared_documents = self._document_store.list_documents(
            scope="shared",
            status="active",
            limit=1000000,
            offset=0,
        )
        document_index = {
            item.document_id: item
            for item in [*documents, *shared_documents]
            if item.status == "active"
            and (
                (item.scope == "tenant" and item.vault_id in effective_tenant_vault_ids)
                or (item.scope == "shared" and item.vault_id in effective_shared_vault_ids)
            )
        }

        tenant_hits = self._retrieve_scope_hits(
            query=query,
            scene=request.scene,
            scope="tenant",
            tenant_id=tenant_id,
            limit=max(request.top_k_tenant, 0),
            tags_filter=request.tags_filter,
            category_filter=request.category_filter,
            document_index=document_index,
            allowed_vault_ids=effective_tenant_vault_ids,
        )
        shared_hits = self._retrieve_scope_hits(
            query=query,
            scene=request.scene,
            scope="shared",
            tenant_id=None,
            limit=max(request.top_k_shared, 0),
            tags_filter=request.tags_filter,
            category_filter=request.category_filter,
            document_index=document_index,
            allowed_vault_ids=effective_shared_vault_ids,
        )
        items = [*tenant_hits, *shared_hits]
        return KnowledgeRetrievalResponse(
            items=items,
            total=len(items),
            tenant_hits=len(tenant_hits),
            shared_hits=len(shared_hits),
            query=query,
            scene=request.scene,
            metadata={
                "effective_tenant_vault_ids": sorted(effective_tenant_vault_ids),
                "effective_shared_vault_ids": sorted(effective_shared_vault_ids),
                "effective_vault_count": len(effective_tenant_vault_ids) + len(effective_shared_vault_ids),
                "candidate_tenant_documents": sum(
                    1 for item in document_index.values() if item.scope == "tenant"
                ),
                "candidate_shared_documents": sum(
                    1 for item in document_index.values() if item.scope == "shared"
                ),
            },
        )

    def retrieve_for_reception(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k_tenant: int = 3,
        top_k_shared: int = 2,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRetrievalResponse:
        """为接待层构造默认检索请求。"""
        return self.retrieve(
            KnowledgeRetrievalRequest(
                tenant_id=tenant_id,
                query=query,
                scene="reception",
                top_k_tenant=top_k_tenant,
                top_k_shared=top_k_shared,
                metadata=dict(metadata or {}),
            )
        )

    def _retrieve_scope_hits(
        self,
        *,
        query: str,
        scene: str,
        scope: str,
        tenant_id: str | None,
        limit: int,
        tags_filter: list[str],
        category_filter: str | None,
        document_index: dict[str, Any],
        allowed_vault_ids: set[str],
    ) -> list[KnowledgeHit]:
        if limit <= 0 or not allowed_vault_ids:
            return []

        chunks = self._chunk_store.list_chunks(
            tenant_id=tenant_id if scope == "tenant" else None,
            scope=scope,
            limit=1000000,
            offset=0,
        )
        best_by_document: dict[str, tuple[float, KnowledgeHit]] = {}
        for chunk in chunks:
            document = document_index.get(chunk.document_id)
            if document is None or document.status != "active":
                continue
            if document.vault_id not in allowed_vault_ids:
                continue
            if scope == "tenant" and document.tenant_id != tenant_id:
                continue
            if scope == "shared" and document.scope != "shared":
                continue
            if not self._matches_filters(
                document=document,
                chunk=chunk,
                tags_filter=tags_filter,
                category_filter=category_filter,
            ):
                continue
            score = self._score_chunk(query=query, scene=scene, document=document, chunk=chunk)
            if score <= 0:
                continue
            hit = KnowledgeHit(
                title=_normalize_text(chunk.title) or _normalize_text(document.title) or document.file_name,
                summary=_normalize_text(chunk.summary) or self._excerpt(chunk.content),
                source=_normalize_text(chunk.source_path) or _normalize_text(document.source_path) or None,
                scope=scope,
                tenant_id=document.tenant_id if scope == "tenant" else None,
                score=round(score, 4),
                metadata=KnowledgeHitMetadata(
                    document_id=document.document_id,
                    chunk_id=chunk.chunk_id,
                    vault_id=document.vault_id,
                    tags=list(dict.fromkeys([*document.tags, *chunk.tags])),
                    source_path=_normalize_text(chunk.source_path) or document.source_path,
                    updated_at=_normalize_text(document.source_updated_at or document.updated_at) or None,
                ),
            )
            previous = best_by_document.get(document.document_id)
            if previous is None or score > previous[0]:
                best_by_document[document.document_id] = (score, hit)

        ranked = sorted(
            best_by_document.values(),
            key=lambda item: (
                -item[0],
                -float(item[1].score or 0),
                _normalize_text(item[1].metadata.updated_at),
                item[1].title.lower(),
            ),
        )
        return [item[1] for item in ranked[:limit]]

    def _matches_filters(
        self,
        *,
        document: Any,
        chunk: Any,
        tags_filter: list[str],
        category_filter: str | None,
    ) -> bool:
        normalized_category = _normalize_text(category_filter).lower()
        if normalized_category and (_normalize_text(document.category).lower() != normalized_category):
            return False

        normalized_tags = {
            _normalize_text(item).lower()
            for item in [*document.tags, *chunk.tags]
            if _normalize_text(item)
        }
        requested_tags = {_normalize_text(item).lower() for item in tags_filter if _normalize_text(item)}
        if requested_tags and not (requested_tags & normalized_tags):
            return False
        return True

    def _score_chunk(self, *, query: str, scene: str, document: Any, chunk: Any) -> float:
        normalized_query = _normalize_text(query).lower()
        tokens = _tokenize(query)
        if not normalized_query:
            return 0.0

        title_text = _normalize_text(chunk.title or document.title).lower()
        heading_text = _normalize_text(chunk.heading_path).lower()
        alias_text = " ".join(_normalize_text(item).lower() for item in document.aliases)
        category_text = _normalize_text(document.category).lower()
        tags_text = " ".join(_normalize_text(item).lower() for item in [*document.tags, *chunk.tags])
        content_text = _normalize_text(chunk.content).lower()
        source_text = _normalize_text(chunk.source_path or document.source_path).lower()

        score = 0.0
        if normalized_query in title_text:
            score += 8.0
        if normalized_query in heading_text:
            score += 5.0
        if normalized_query in alias_text:
            score += 4.0
        if normalized_query in tags_text:
            score += 3.5
        if normalized_query in content_text:
            score += 3.0
        if normalized_query in source_text:
            score += 1.5

        for token in tokens:
            if token in title_text:
                score += 2.2
            if token in heading_text:
                score += 1.5
            if token in alias_text:
                score += 1.2
            if token in category_text:
                score += 1.2
            if token in tags_text:
                score += 1.1
            if token in content_text:
                score += 0.7
            if token in source_text:
                score += 0.5

        if scene == "reception" and _contains_any(tags_text, [item.lower() for item in RECEPTION_PRIORITY_TAGS]):
            score += 1.5
        if scene == "reception" and category_text in {"faq", "reception", "service"}:
            score += 1.0

        updated_at = _parse_datetime(document.source_updated_at or document.updated_at)
        if updated_at is not None:
            age_days = max((datetime.now(UTC) - updated_at).days, 0)
            if age_days <= 30:
                score += 0.4
            elif age_days <= 180:
                score += 0.2

        return score

    def _excerpt(self, content: str, limit: int = 140) -> str:
        normalized = " ".join(_normalize_text(content).split())
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rstrip() + "..."

    def _resolve_effective_vault_ids(self, tenant_id: str) -> tuple[set[str], set[str]]:
        tenant_vault_ids = {
            item.vault_id
            for item in self._vault_store.list_vaults(
                vault_type="tenant",
                tenant_id=tenant_id,
                enabled=True,
            )
            if _normalize_text(item.vault_id)
        }
        shared_vault_ids = {
            item.vault_id
            for item in self._vault_store.list_vaults(
                vault_type="shared",
                enabled=True,
            )
            if _normalize_text(item.vault_id)
        }
        return tenant_vault_ids, shared_vault_ids


knowledge_retrieval_service = KnowledgeRetrievalService()
