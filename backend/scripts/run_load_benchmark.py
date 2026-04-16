from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
import sys
import time
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.nats_event_bus import nats_event_bus
from app.services.memory_service import memory_service
from scripts.package_t_common import (
    REPORTS_ROOT,
    Sample,
    build_test_client,
    render_markdown_report,
    summarize_samples,
    timed_sample,
    write_json_report,
)


def _message_payload(index: int) -> dict[str, Any]:
    return {
        "channel": "telegram",
        "platformUserId": f"load-user-{index % 10}",
        "chatId": f"load-chat-{index % 5}",
        "text": f"压测消息 {index}：请记录今天的工作进展并保持中文输出。",
        "receivedAt": datetime.now(UTC).isoformat(),
        "authScope": "messages:ingest",
        "metadata": {"benchmark": True, "sequence": index},
    }


def run_concurrent_message_benchmark(*, total_requests: int, concurrency: int) -> dict[str, Any]:
    client = build_test_client()
    original_initialize = nats_event_bus.initialize
    original_long_term_store = memory_service._long_term_store

    def invoke(index: int) -> Sample:
        with timed_sample() as span:
            try:
                response = client.post("/api/messages/ingest", json=_message_payload(index))
                pass
            except Exception as exc:  # pragma: no cover
                error = str(exc)
                status_code = 0
                ok = False
            else:
                error = None if response.status_code < 400 else response.text[:160]
                status_code = response.status_code
                ok = response.status_code < 400
        return Sample(ok=ok, status_code=status_code, latency_ms=span["latency_ms"], error=error)

    samples: list[Sample] = []
    nats_event_bus.initialize = lambda: False  # type: ignore[assignment]
    memory_service._long_term_store = None
    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [pool.submit(invoke, index) for index in range(total_requests)]
            for future in as_completed(futures):
                samples.append(future.result())
    finally:
        nats_event_bus.initialize = original_initialize  # type: ignore[assignment]
        memory_service._long_term_store = original_long_term_store

    return {
        "scenario": "concurrent_messages",
        "total_requests": total_requests,
        "concurrency": concurrency,
        "summary": summarize_samples(samples),
    }


def run_timeout_retry_benchmark(
    *,
    total_requests: int,
    concurrency: int,
    forced_timeout_ms: float,
    retries: int,
) -> dict[str, Any]:
    samples: list[Sample] = []
    client = build_test_client()
    original_initialize = nats_event_bus.initialize
    original_long_term_store = memory_service._long_term_store

    def invoke(index: int) -> Sample:
        status_code = 0
        error: str | None = None
        started_at = time.perf_counter()
        for attempt in range(retries + 1):
            try:
                response = client.post("/api/messages/ingest", json=_message_payload(index))
                status_code = response.status_code
                latency_ms = (time.perf_counter() - started_at) * 1000
                if latency_ms > forced_timeout_ms and attempt < retries:
                    error = f"client_timeout_retry_{attempt + 1}"
                    continue
                ok = response.status_code < 400 and latency_ms <= forced_timeout_ms
                return Sample(ok=ok, status_code=status_code, latency_ms=latency_ms, error=error)
            except Exception as exc:  # pragma: no cover
                status_code = 0
                error = str(exc)
        latency_ms = (time.perf_counter() - started_at) * 1000
        return Sample(ok=False, status_code=status_code, latency_ms=latency_ms, error=error)

    nats_event_bus.initialize = lambda: False  # type: ignore[assignment]
    memory_service._long_term_store = None
    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [pool.submit(invoke, index) for index in range(total_requests)]
            for future in as_completed(futures):
                samples.append(future.result())
    finally:
        nats_event_bus.initialize = original_initialize  # type: ignore[assignment]
        memory_service._long_term_store = original_long_term_store

    return {
        "scenario": "timeout_retry",
        "total_requests": total_requests,
        "concurrency": concurrency,
        "forced_timeout_ms": forced_timeout_ms,
        "retries": retries,
        "summary": summarize_samples(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Package T load benchmarks.")
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--forced-timeout-ms", type=float, default=80.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument(
        "--report-prefix",
        default="package_t_load",
        help="Output report prefix under backend/docs/",
    )
    args = parser.parse_args()

    concurrent_result = run_concurrent_message_benchmark(
        total_requests=max(1, args.requests),
        concurrency=max(1, args.concurrency),
    )
    timeout_result = run_timeout_retry_benchmark(
        total_requests=max(1, args.requests),
        concurrency=max(1, args.concurrency),
        forced_timeout_ms=max(1.0, args.forced_timeout_ms),
        retries=max(0, args.retries),
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_ROOT / f"{args.report_prefix}_{timestamp}.json"
    md_path = REPORTS_ROOT / f"{args.report_prefix}_{timestamp}.md"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "benchmarks": [concurrent_result, timeout_result],
    }
    write_json_report(json_path, payload)
    md_path.write_text(
        render_markdown_report(
            "Package T Load Benchmark",
            [
                ("Concurrent Messages", concurrent_result),
                ("Timeout And Retry", timeout_result),
            ],
        ),
        encoding="utf-8",
    )
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
