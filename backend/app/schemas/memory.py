from pydantic import Field

from app.schemas.base import APIModel


class MemoryMessage(APIModel):
    id: str
    user_id: str
    session_id: str
    role: str
    content: str
    detected_lang: str
    created_at: str


class MidTermSummary(APIModel):
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


class LongTermMemory(APIModel):
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


class MemoryMessagesResponse(APIModel):
    user_id: str
    session_id: str | None = None
    items: list[MemoryMessage]
    total: int


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


class MemoryRetrieveResponse(APIModel):
    items: list[MemoryRetrieveItem]
    total: int
    query_expanded_terms: list[str] = Field(default_factory=list)
