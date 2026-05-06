from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


KnowledgeScene = Literal["reception", "dispatch", "general"]
KnowledgeHitScope = Literal["shared", "tenant"]


class KnowledgeRetrievalRequest(APIModel):
    tenant_id: str
    query: str
    scene: KnowledgeScene = "reception"
    top_k_tenant: int = 3
    top_k_shared: int = 2
    tags_filter: list[str] = Field(default_factory=list)
    category_filter: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeHitMetadata(APIModel):
    document_id: str | None = None
    chunk_id: str | None = None
    vault_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_path: str | None = None
    updated_at: str | None = None


class KnowledgeHit(APIModel):
    title: str
    summary: str
    source: str | None = None
    scope: KnowledgeHitScope = "tenant"
    tenant_id: str | None = None
    score: float | None = None
    metadata: KnowledgeHitMetadata = Field(default_factory=KnowledgeHitMetadata)


class KnowledgeRetrievalResponse(APIModel):
    items: list[KnowledgeHit] = Field(default_factory=list)
    total: int = 0
    tenant_hits: int = 0
    shared_hits: int = 0
    query: str
    scene: KnowledgeScene = "reception"
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeRetrievalLog(APIModel):
    retrieval_log_id: str
    tenant_id: str
    query: str
    scene: KnowledgeScene = "reception"
    hit_count: int = 0
    tenant_hit_count: int = 0
    shared_hit_count: int = 0
    top_document_ids: list[str] = Field(default_factory=list)
    top_chunk_ids: list[str] = Field(default_factory=list)
    request_source: str | None = None
    trace_id: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeRetrievalLogListResponse(APIModel):
    items: list[KnowledgeRetrievalLog] = Field(default_factory=list)
    total: int = 0
    updated_at: str | None = None
