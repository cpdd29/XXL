from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services import workflow_execution_service
from app.services.store import store


client = TestClient(app)


def _build_agent(
    *,
    agent_id: str,
    agent_type: str,
    status_text: str = "running",
    enabled: bool = True,
    config_snapshot: dict | None = None,
) -> dict:
    return {
        "id": agent_id,
        "name": f"{agent_id}-name",
        "description": f"{agent_id}-description",
        "type": agent_type,
        "status": status_text,
        "enabled": enabled,
        "tasks_completed": 10,
        "tasks_total": 10,
        "avg_response_time": "10ms",
        "tokens_used": 100,
        "tokens_limit": 1000,
        "success_rate": 99.0,
        "last_active": "刚刚",
        "config_snapshot": config_snapshot,
    }


def test_agent_heartbeat_route_updates_runtime_status_and_metrics(auth_headers) -> None:
    response = client.post(
        "/api/agents/3/heartbeat",
        headers=auth_headers,
        json={
            "status": "running",
            "intervalSeconds": 6,
            "timeoutSeconds": 30,
            "source": "agent-worker-3",
            "load": 0.42,
            "queueDepth": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent"]["runtimeStatus"] == "online"
    assert payload["agent"]["routable"] is True
    assert payload["agent"]["runtimeMetrics"]["source"] == "agent-worker-3"
    assert payload["agent"]["runtimeMetrics"]["load"] == 0.42
    assert payload["agent"]["runtimeMetrics"]["queue_depth"] == 3

    status_response = client.get("/api/agents/3/status", headers=auth_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["runtimeStatus"] == "online"
    assert status_payload["lastHeartbeatAt"]


def test_agent_list_marks_stale_heartbeat_agent_offline(auth_headers) -> None:
    stale_at = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    store.agents.append(
        _build_agent(
            agent_id="agent-stale-heartbeat",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": stale_at,
                    "heartbeat_interval_seconds": 5,
                    "heartbeat_timeout_seconds": 30,
                }
            },
        )
    )

    response = client.get("/api/agents", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    stale_agent = next(item for item in payload["items"] if item["id"] == "agent-stale-heartbeat")
    assert stale_agent["runtimeStatus"] == "offline"
    assert stale_agent["routable"] is False


def test_resolve_direct_execution_agent_prefers_healthy_status() -> None:
    now = datetime.now(UTC)
    store.agents = [
        _build_agent(
            agent_id="search-degraded",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": (now - timedelta(seconds=40)).isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        ),
        _build_agent(
            agent_id="search-online",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": now.isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        ),
    ]

    selected = workflow_execution_service.resolve_direct_execution_agent("search")
    assert selected is not None
    assert selected["id"] == "search-online"


def test_resolve_direct_execution_agent_falls_back_to_degraded() -> None:
    now = datetime.now(UTC)
    store.agents = [
        _build_agent(
            agent_id="search-degraded-only",
            agent_type="search",
            config_snapshot={
                "runtime": {
                    "last_heartbeat_at": (now - timedelta(seconds=40)).isoformat(),
                    "heartbeat_interval_seconds": 10,
                    "heartbeat_timeout_seconds": 60,
                }
            },
        )
    ]

    selected = workflow_execution_service.resolve_direct_execution_agent("search")
    assert selected is not None
    assert selected["id"] == "search-degraded-only"
