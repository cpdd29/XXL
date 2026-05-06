from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


KnowledgeScope = Literal["shared", "tenant"]
KnowledgeDocumentStatus = Literal["active", "archived", "deleted"]
KnowledgeChunkEmbeddingStatus = Literal["pending", "ready", "failed", "skipped"]


class KnowledgeDocument(APIModel):
    document_id: str
    vault_id: str
    tenant_id: str | None = None
    scope: KnowledgeScope = "tenant"
    source_path: str
    file_name: str
    title: str
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    raw_markdown: str = ""
    normalized_text: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)
    checksum: str | None = None
    version: int = 1
    status: KnowledgeDocumentStatus = "active"
    created_at: str | None = None
    updated_at: str | None = None
    source_updated_at: str | None = None


class KnowledgeChunk(APIModel):
    chunk_id: str
    document_id: str
    vault_id: str
    tenant_id: str | None = None
    scope: KnowledgeScope = "tenant"
    title: str
    heading_path: str | None = None
    summary: str | None = None
    content: str
    tags: list[str] = Field(default_factory=list)
    source_path: str
    chunk_index: int = 0
    token_estimate: int | None = None
    embedding_status: KnowledgeChunkEmbeddingStatus = "pending"
    created_at: str | None = None
    updated_at: str | None = None


class KnowledgeDocumentListResponse(APIModel):
    items: list[KnowledgeDocument] = Field(default_factory=list)
    total: int = 0
    updated_at: str | None = None


class KnowledgeChunkListResponse(APIModel):
    items: list[KnowledgeChunk] = Field(default_factory=list)
    total: int = 0
    updated_at: str | None = None


class KnowledgeDocumentDetailResponse(APIModel):
    document: KnowledgeDocument
    chunks: list[KnowledgeChunk] = Field(default_factory=list)

