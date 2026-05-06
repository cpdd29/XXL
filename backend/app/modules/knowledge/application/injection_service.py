from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.modules.agent_config.protocol_bindings.schemas import KnowledgeHit as HermesKnowledgeHit
from app.modules.knowledge.schemas import KnowledgeRetrievalResponse


MAX_METADATA_HITS = 5
MAX_PROTOCOL_HITS = 5
MAX_ITEM_SUMMARY_CHARS = 220
MAX_TOTAL_SUMMARY_CHARS = 1200
MIN_REMAINING_SUMMARY_CHARS = 40
SENSITIVE_TAGS = {
    "confidential",
    "internal",
    "pii",
    "secret",
    "sensitive",
    "内部",
    "受限",
    "敏感",
    "机密",
}
SENSITIVE_SUMMARY_PLACEHOLDER = "该知识片段因敏感标签已做摘要脱敏"


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _truncate_text(value: str, *, limit: int) -> str:
    normalized = _normalize_text(value)
    if limit <= 0:
        return ""
    if len(normalized) <= limit:
        return normalized
    if limit <= 3:
        return normalized[:limit]
    return normalized[: limit - 3].rstrip() + "..."


class KnowledgeInjectionService:
    """知识命中注入服务骨架。"""

    def build_metadata_hits(self, retrieval: KnowledgeRetrievalResponse) -> list[dict[str, Any]]:
        """将检索结果转换为接待链 metadata 可直接挂载的 knowledge_hits。"""
        items: list[dict[str, Any]] = []
        for item in self._govern_hits(retrieval, limit=MAX_METADATA_HITS):
            items.append(
                {
                    "title": item.title,
                    "summary": item.summary,
                    "source": item.source,
                    "metadata": {
                        "document_id": item.metadata.document_id,
                        "chunk_id": item.metadata.chunk_id,
                        "vault_id": item.metadata.vault_id,
                        "tags": list(item.metadata.tags),
                        "source_path": item.metadata.source_path,
                        "updated_at": item.metadata.updated_at,
                        "scope": item.scope,
                        "tenant_id": item.tenant_id,
                        "score": item.score,
                    },
                }
            )
        return items

    def build_protocol_hits(self, retrieval: KnowledgeRetrievalResponse) -> list[HermesKnowledgeHit]:
        """将检索结果转换为 Hermes 协议知识命中对象。"""
        items: list[HermesKnowledgeHit] = []
        for item in self._govern_hits(retrieval, limit=MAX_PROTOCOL_HITS):
            items.append(
                HermesKnowledgeHit(
                    title=item.title,
                    summary=item.summary,
                    source=item.source,
                    metadata={
                        "document_id": item.metadata.document_id,
                        "chunk_id": item.metadata.chunk_id,
                        "vault_id": item.metadata.vault_id,
                        "tags": list(item.metadata.tags),
                        "source_path": item.metadata.source_path,
                        "updated_at": item.metadata.updated_at,
                        "scope": item.scope,
                        "tenant_id": item.tenant_id,
                        "score": item.score,
                    },
                )
            )
        return items

    def inject_hits_into_metadata(
        self,
        *,
        metadata: dict[str, Any] | None,
        retrieval: KnowledgeRetrievalResponse,
    ) -> dict[str, Any]:
        """把 knowledge_hits 写回消息 metadata。"""
        payload = deepcopy(metadata) if isinstance(metadata, dict) else {}
        payload["knowledge_hits"] = self.build_metadata_hits(retrieval)
        payload["knowledge_retrieval"] = {
            "query": retrieval.query,
            "scene": retrieval.scene,
            "total": retrieval.total,
            "tenant_hits": retrieval.tenant_hits,
            "shared_hits": retrieval.shared_hits,
        }
        payload["knowledge_injection_governance"] = self.build_governance_summary(retrieval)
        return payload

    def build_governance_summary(self, retrieval: KnowledgeRetrievalResponse) -> dict[str, Any]:
        governed = self._govern_hits(retrieval, limit=MAX_METADATA_HITS)
        redacted = 0
        summary_chars = 0
        for item in governed:
            if item.summary == SENSITIVE_SUMMARY_PLACEHOLDER:
                redacted += 1
            summary_chars += len(_normalize_text(item.summary))
        return {
            "raw_total": retrieval.total,
            "delivered_total": len(governed),
            "dropped_total": max(retrieval.total - len(governed), 0),
            "redacted_total": redacted,
            "summary_char_budget": MAX_TOTAL_SUMMARY_CHARS,
            "summary_chars_used": summary_chars,
            "item_limit": MAX_METADATA_HITS,
        }

    def _govern_hits(
        self,
        retrieval: KnowledgeRetrievalResponse,
        *,
        limit: int,
    ):
        remaining_summary_chars = MAX_TOTAL_SUMMARY_CHARS
        governed_items = []
        for raw_item in retrieval.items:
            if len(governed_items) >= max(limit, 0):
                break

            summary = self._sanitize_summary(raw_item.summary, tags=raw_item.metadata.tags)
            summary_limit = min(MAX_ITEM_SUMMARY_CHARS, remaining_summary_chars)
            if summary != SENSITIVE_SUMMARY_PLACEHOLDER and summary_limit < MIN_REMAINING_SUMMARY_CHARS:
                break
            if summary != SENSITIVE_SUMMARY_PLACEHOLDER:
                summary = _truncate_text(summary, limit=summary_limit)
                remaining_summary_chars -= len(summary)
            title = _truncate_text(raw_item.title, limit=120) or "未命名知识片段"
            governed_items.append(
                raw_item.model_copy(
                    update={
                        "title": title,
                        "summary": summary or SENSITIVE_SUMMARY_PLACEHOLDER,
                    }
                )
            )
        return governed_items

    def _sanitize_summary(self, summary: str, *, tags: list[str]) -> str:
        normalized_tags = {_normalize_text(item).lower() for item in tags if _normalize_text(item)}
        if normalized_tags & SENSITIVE_TAGS:
            return SENSITIVE_SUMMARY_PLACEHOLDER
        return _normalize_text(summary)


knowledge_injection_service = KnowledgeInjectionService()
