from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.package_t_common import (
    REPORTS_ROOT,
    build_test_client,
    login_headers,
    render_markdown_report,
    write_json_report,
)

from app.core.nats_event_bus import nats_event_bus
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.external_skill_registry_service import external_skill_registry_service
from app.services.persistence_service import persistence_service
from app.services.security_gateway_service import security_gateway_service


def run_external_offline_drill() -> dict[str, Any]:
    client = build_test_client()
    headers = login_headers(client)
    now = datetime.now(UTC)
    external_agent_registry_service.register_agent(
        {
            "agent_id": "drill-offline-agent",
            "name": "Drill Offline Agent",
            "endpoint": "https://offline.agent.local",
            "runtime_status": "online",
            "enabled": True,
            "heartbeat_timeout_seconds": 10,
            "last_heartbeat_at": (now - timedelta(minutes=10)).isoformat(),
            "capabilities": ["search"],
        }
    )
    external_skill_registry_service.register_skill(
        {
            "skill_id": "drill-offline-skill",
            "name": "Drill Offline Skill",
            "description": "offline",
            "enabled": True,
            "health_status": "healthy",
            "timeout_seconds": 5,
            "heartbeat_timeout_seconds": 10,
            "last_heartbeat_at": (now - timedelta(minutes=10)).isoformat(),
            "abilities": [{"id": "offline", "name": "offline"}],
        }
    )
    external_agent_registry_service.prune_expired()
    external_skill_registry_service.prune_expired()
    response = client.get("/api/external-connections/health", headers=headers)
    body = response.json()
    return {
        "scenario": "external_offline",
        "status_code": response.status_code,
        "summary": body.get("summary", {}),
        "counts": body.get("counts", {}),
    }


def run_nats_block_drill() -> dict[str, Any]:
    from app.services.workflow_realtime_service import workflow_realtime_service

    published_events: list[tuple[str, dict[str, Any]]] = []
    original_publish_json = nats_event_bus.publish_json
    original_publish_event = workflow_realtime_service.publish_run_event

    def blocked_publish_json(subject: str, payload: dict) -> bool:
        _ = (subject, payload)
        raise RuntimeError("simulated_nats_block")

    def local_capture(run: dict, event_type: str) -> None:
        published_events.append((event_type, {"run_id": run.get("id"), "status": run.get("status")}))
        return original_publish_event(run, event_type)

    nats_event_bus.publish_json = blocked_publish_json  # type: ignore[assignment]
    workflow_realtime_service.publish_run_event = local_capture  # type: ignore[assignment]
    try:
        ok = False
        try:
            ok = nats_event_bus.publish_json("brain.workflow.run.updated", {"event_name": "test"})
        except Exception as exc:
            failure = str(exc)
        else:  # pragma: no cover
            failure = "no_failure"
        return {
            "scenario": "nats_block",
            "publish_ok": ok,
            "failure": failure,
            "expected_degradation": "fallback_to_in_process_bus",
            "captured_local_events": len(published_events),
        }
    finally:
        nats_event_bus.publish_json = original_publish_json  # type: ignore[assignment]
        workflow_realtime_service.publish_run_event = original_publish_event  # type: ignore[assignment]


def run_database_slow_query_drill(delay_seconds: float) -> dict[str, Any]:
    client = build_test_client()
    headers = login_headers(client)
    original_list_tasks = persistence_service.list_tasks

    def slow_list_tasks(*args, **kwargs):
        time.sleep(delay_seconds)
        return original_list_tasks(*args, **kwargs)

    persistence_service.list_tasks = slow_list_tasks  # type: ignore[assignment]
    started = time.perf_counter()
    try:
        response = client.get("/api/dashboard/stats", headers=headers)
    finally:
        persistence_service.list_tasks = original_list_tasks  # type: ignore[assignment]
    latency_ms = (time.perf_counter() - started) * 1000
    return {
        "scenario": "database_slow_query",
        "delay_seconds": delay_seconds,
        "status_code": response.status_code,
        "latency_ms": round(latency_ms, 2),
        "health_status": response.json().get("slaSummary", {}).get("healthStatus"),
    }


def run_security_pressure_drill(total_requests: int) -> dict[str, Any]:
    client = build_test_client()
    security_gateway_service.reset()
    blocked = 0
    allowed = 0
    for index in range(total_requests):
        response = client.post(
            "/api/messages/ingest",
            json={
                "channel": "telegram",
                "platformUserId": "security-pressure-user",
                "chatId": "security-pressure-chat",
                "text": f"安全压测消息 {index}",
                "receivedAt": datetime.now(UTC).isoformat(),
                "authScope": "messages:ingest",
            },
        )
        if response.status_code == 429:
            blocked += 1
        else:
            allowed += 1
    return {
        "scenario": "security_high_pressure",
        "total_requests": total_requests,
        "allowed": allowed,
        "blocked_429": blocked,
        "degradation_expected": blocked > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Package T fault drills.")
    parser.add_argument("--slow-query-delay", type=float, default=0.12)
    parser.add_argument("--security-requests", type=int, default=20)
    parser.add_argument("--report-prefix", default="package_t_faults")
    args = parser.parse_args()

    results = [
        run_external_offline_drill(),
        run_nats_block_drill(),
        run_database_slow_query_drill(delay_seconds=max(0.01, args.slow_query_delay)),
        run_security_pressure_drill(total_requests=max(1, args.security_requests)),
    ]
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_ROOT / f"{args.report_prefix}_{timestamp}.json"
    md_path = REPORTS_ROOT / f"{args.report_prefix}_{timestamp}.md"
    payload = {"generated_at": datetime.now(UTC).isoformat(), "drills": results}
    write_json_report(json_path, payload)
    md_path.write_text(
        render_markdown_report(
            "Package T Fault Drill",
            [(item["scenario"], item) for item in results],
        ),
        encoding="utf-8",
    )
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
