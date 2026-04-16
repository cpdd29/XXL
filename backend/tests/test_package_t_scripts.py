from __future__ import annotations

from pathlib import Path

from scripts.package_t_common import Sample, render_markdown_report, summarize_samples
from scripts.run_fault_drills import (
    run_database_slow_query_drill,
    run_external_offline_drill,
    run_nats_block_drill,
    run_security_pressure_drill,
)
from scripts.run_load_benchmark import (
    run_concurrent_message_benchmark,
    run_timeout_retry_benchmark,
)


def test_summarize_samples_computes_basic_latency_shape() -> None:
    summary = summarize_samples(
        [
            Sample(ok=True, status_code=200, latency_ms=10),
            Sample(ok=False, status_code=429, latency_ms=50, error="rate_limit"),
            Sample(ok=True, status_code=200, latency_ms=20),
        ]
    )
    assert summary["requests"] == 3
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["latency"]["p95_ms"] >= summary["latency"]["min_ms"]
    assert summary["errors"]["rate_limit"] == 1


def test_render_markdown_report_contains_json_block() -> None:
    rendered = render_markdown_report("Package T", [("Section", {"ok": True})])
    assert "# Package T" in rendered
    assert "```json" in rendered
    assert '"ok": true' in rendered


def test_load_benchmark_scripts_return_structured_payloads() -> None:
    concurrent = run_concurrent_message_benchmark(total_requests=4, concurrency=2)
    timeout_retry = run_timeout_retry_benchmark(
        total_requests=4,
        concurrency=2,
        forced_timeout_ms=0.01,
        retries=1,
    )
    assert concurrent["summary"]["requests"] == 4
    assert timeout_retry["summary"]["requests"] == 4


def test_fault_drill_scripts_return_structured_payloads() -> None:
    external = run_external_offline_drill()
    nats = run_nats_block_drill()
    database = run_database_slow_query_drill(delay_seconds=0.01)
    security = run_security_pressure_drill(total_requests=8)

    assert external["scenario"] == "external_offline"
    assert nats["scenario"] == "nats_block"
    assert database["scenario"] == "database_slow_query"
    assert security["scenario"] == "security_high_pressure"
    assert security["allowed"] + security["blocked_429"] == 8
