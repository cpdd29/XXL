from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.schemas import KnowledgeRetrievalLog


class KnowledgeRetrievalLogStore(Protocol):
    def list_retrieval_logs(
        self,
        *,
        tenant_id: str | None = None,
        scene: str | None = None,
        request_source: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeRetrievalLog]:
        ...

    def count_retrieval_logs(
        self,
        *,
        tenant_id: str | None = None,
        scene: str | None = None,
        request_source: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        ...

    def append_retrieval_log(self, log: KnowledgeRetrievalLog) -> KnowledgeRetrievalLog:
        ...

