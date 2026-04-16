from __future__ import annotations

import json
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_ROOT = PROJECT_ROOT / "docs"


@dataclass(slots=True)
class Sample:
    ok: bool
    status_code: int
    latency_ms: float
    error: str | None = None


def build_test_client() -> TestClient:
    return TestClient(app)


def login_headers(client: TestClient) -> dict[str, str]:
    settings = get_settings()
    response = client.post(
        "/api/auth/login",
        json={
            "email": settings.demo_admin_email,
            "password": settings.demo_admin_password,
        },
    )
    response.raise_for_status()
    token = response.json()["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def summarize_samples(samples: list[Sample]) -> dict[str, Any]:
    latencies = [item.latency_ms for item in samples]
    success_count = sum(1 for item in samples if item.ok)
    failure_count = len(samples) - success_count
    error_buckets: dict[str, int] = {}
    for item in samples:
        if not item.error:
            continue
        error_buckets[item.error] = error_buckets.get(item.error, 0) + 1
    if latencies:
        sorted_latencies = sorted(latencies)
        p95_index = min(len(sorted_latencies) - 1, max(0, int(len(sorted_latencies) * 0.95) - 1))
        p99_index = min(len(sorted_latencies) - 1, max(0, int(len(sorted_latencies) * 0.99) - 1))
        latency_summary = {
            "avg_ms": round(statistics.mean(latencies), 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "p95_ms": round(sorted_latencies[p95_index], 2),
            "p99_ms": round(sorted_latencies[p99_index], 2),
        }
    else:
        latency_summary = {
            "avg_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }
    return {
        "requests": len(samples),
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round((success_count / len(samples)) * 100, 2) if samples else 0.0,
        "latency": latency_summary,
        "errors": error_buckets,
    }


def write_json_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_markdown_report(title: str, sections: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [f"# {title}", ""]
    for heading, payload in sections:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


@contextmanager
def timed_sample() -> Any:
    started_at = time.perf_counter()
    holder: dict[str, float] = {"started_at": started_at}
    yield holder
    holder["latency_ms"] = (time.perf_counter() - started_at) * 1000
