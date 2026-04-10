from __future__ import annotations

from app.services.document_search_service import document_search_service


def test_search_hits_security_gateway_svg_with_mixed_zh_en_query() -> None:
    results = document_search_service.search(
        "请总结security gateway 第③层 prompt injection 双检策略",
        intent="search",
        limit=5,
    )

    assert results
    top = results[0]
    assert top["source_name"] == "security_gateway_pipeline.svg"
    assert "③ Prompt injection scan" in top["section"]
    assert top["excerpt"] == "Security gateway — 5-layer pipeline"


def test_search_recalls_markdown_and_svg_for_security_gateway_architecture_terms() -> None:
    results = document_search_service.search(
        "安全网关 第⑤层 append-only 防篡改 日志策略",
        intent="search",
        limit=5,
    )

    assert len(results) >= 2
    top_sources = {item["source_name"] for item in results[:3]}
    assert "开发指南补充.md" in top_sources
    assert "security_gateway_pipeline.svg" in top_sources
    assert any(
        item["source_name"] == "security_gateway_pipeline.svg" and "⑤ Audit & telemetry" in item["section"]
        for item in results
    )


def test_search_memory_distillation_query_prefers_memory_svg_stages_with_stable_shape() -> None:
    results = document_search_service.search(
        "memory distillation 里 Redis 和 ChromaDB 各在哪个阶段?",
        intent="search",
        limit=3,
    )

    assert len(results) == 3
    assert all(item["source_name"] == "memory_distillation_lifecycle.svg" for item in results)
    assert {item["section"] for item in results} == {"Short-term", "Mid-term", "Long-term"}
    for item in results:
        assert set(item.keys()) == {"source_name", "section", "content", "excerpt"}
        assert item["excerpt"] == "Memory distillation lifecycle"
        assert item["excerpt"] in item["content"]
