from pydantic import Field

from app.schemas.base import APIModel


class MemoryGovernanceMixin(APIModel):
    tenant_id: str = "default"
    project_id: str = "default"
    environment: str = "development"
    memory_scope: str = "tenant"
    memory_layer_kind: str = "conversation"
    write_source: str = "brain_internal"
    trust_level: str = "trusted"
    memory_status: str = "active"
    review_status: str = "approved"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    expires_at: str | None = None
    archived_at: str | None = None
    deleted_at: str | None = None
    corrected_at: str | None = None
    retention_policy: str = "default"
    local_only_reasons: list[str] = Field(default_factory=list)
    local_only_filtered_count: int = 0


class MemoryMessage(MemoryGovernanceMixin):
    id: str
    user_id: str
    session_id: str
    role: str
    content: str
    detected_lang: str
    created_at: str


class MidTermSummary(MemoryGovernanceMixin):
    id: str
    user_id: str
    session_id: str
    trigger: str
    source_count: int
    summary: str
    entities: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    task_results: list[str] = Field(default_factory=list)
    created_at: str


class LongTermMemory(MemoryGovernanceMixin):
    id: str
    user_id: str
    source_mid_term_id: str
    memory_type: str = "session_summary"
    summary: str | None = None
    memory_text: str
    keywords: list[str] = Field(default_factory=list)
    created_at: str


class IngestMemoryMessageRequest(APIModel):
    user_id: str
    session_id: str = "default"
    role: str = "user"
    content: str
    detected_lang: str = "zh"
    write_source: str = "user_message"
    trust_level: str | None = None
    memory_scope: str = "tenant"


class IngestMemoryMessageResponse(APIModel):
    ok: bool
    message: str
    item: MemoryMessage
    short_term_count: int
    distill_recommended: bool
    auto_distilled_sessions: list[str] = Field(default_factory=list)
    auto_weekly_distilled: bool = False


class DistillMemoryRequest(APIModel):
    trigger: str = "daily"
    session_id: str | None = None
    write_source: str = "brain_internal"
    trust_level: str | None = None
    memory_scope: str = "tenant"


class DistillMemoryResponse(APIModel):
    ok: bool
    message: str
    created: bool
    mid_term: MidTermSummary | None = None
    long_term: LongTermMemory | None = None
    long_term_items: list[LongTermMemory] = Field(default_factory=list)
    short_term_remaining: int


class MemoryLayersResponse(APIModel):
    user_id: str
    short_term: list[MemoryMessage]
    mid_term: list[MidTermSummary]
    long_term: list[LongTermMemory]
    short_term_count: int
    mid_term_count: int
    long_term_count: int
    scope_breakdown: dict[str, int] = Field(default_factory=dict)


class MemoryMessagesResponse(APIModel):
    user_id: str
    session_id: str | None = None
    items: list[MemoryMessage]
    total: int
    scope_breakdown: dict[str, int] = Field(default_factory=dict)


class MemoryRetrieveItem(APIModel):
    memory_id: str
    source_mid_term_id: str
    memory_type: str = "session_summary"
    memory_text: str
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    score: float
    created_at: str
    lexical_score: float | None = None
    vector_score: float | None = None
    phrase_hit_count: int | None = None
    matched_terms: list[str] = Field(default_factory=list)
    rerank_score: float | None = None
    tenant_id: str = "default"
    project_id: str = "default"
    environment: str = "development"
    memory_scope: str = "tenant"
    memory_layer_kind: str = "conversation"
    write_source: str = "brain_internal"
    trust_level: str = "trusted"
    memory_status: str = "active"
    review_status: str = "approved"
    retention_policy: str = "default"
    local_only_reasons: list[str] = Field(default_factory=list)
    local_only_filtered_count: int = 0


class MemoryRetrieveResponse(APIModel):
    items: list[MemoryRetrieveItem]
    total: int
    query_expanded_terms: list[str] = Field(default_factory=list)
    scope_breakdown: dict[str, int] = Field(default_factory=dict)


class ReviewMemoryRequest(APIModel):
    action: str
    note: str | None = None
    corrected_memory_text: str | None = None
    corrected_summary: str | None = None


class ReviewMemoryResponse(APIModel):
    ok: bool
    message: str
    item: LongTermMemory


class MemoryAuditEntry(APIModel):
    layer: str
    id: str
    user_id: str
    session_id: str | None = None
    source_mid_term_id: str | None = None
    role: str | None = None
    memory_type: str | None = None
    summary: str | None = None
    content: str | None = None
    created_at: str
    tenant_id: str = "default"
    project_id: str = "default"
    environment: str = "development"
    memory_scope: str = "tenant"
    memory_layer_kind: str = "conversation"
    write_source: str = "brain_internal"
    trust_level: str = "trusted"
    memory_status: str = "active"
    review_status: str = "approved"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    expires_at: str | None = None
    archived_at: str | None = None
    deleted_at: str | None = None
    corrected_at: str | None = None
    retention_policy: str = "default"
    local_only_reasons: list[str] = Field(default_factory=list)
    local_only_filtered_count: int = 0


class MemoryAuditResponse(APIModel):
    user_id: str
    items: list[MemoryAuditEntry] = Field(default_factory=list)
    total: int
    scope_breakdown: dict[str, int] = Field(default_factory=dict)


class MemoryLifecycleResponse(APIModel):
    ok: bool
    archived_count: int = 0
    deleted_count: int = 0
    corrected_count: int = 0
