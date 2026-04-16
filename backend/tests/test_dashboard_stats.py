from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.persistence_service import persistence_service
from app.services.store import store


client = TestClient(app)


def test_dashboard_stats_are_built_from_runtime_entities_instead_of_static_samples(
    auth_headers,
) -> None:
    store.dashboard_stats = [
        {
            "key": "active_agents",
            "title": "不应再使用",
            "value": 999,
            "description": "静态样例",
            "trend_value": 999,
            "trend_positive": False,
        }
    ]
    store.chart_data = [{"time": "00:00", "requests": 999, "tokens": 999}]
    store.agents = [
        {
            "id": "agent-1",
            "name": "意图识别 Agent",
            "type": "intent",
            "status": "running",
            "enabled": True,
            "tasks_completed": 10,
            "avg_response_time": "45ms",
        },
        {
            "id": "agent-2",
            "name": "搜索 Agent",
            "type": "search",
            "status": "waiting",
            "enabled": True,
            "tasks_completed": 8,
            "avg_response_time": "320ms",
        },
        {
            "id": "agent-3",
            "name": "写作 Agent",
            "type": "write",
            "status": "idle",
            "enabled": True,
            "tasks_completed": 5,
            "avg_response_time": "1.2s",
        },
    ]
    store.workflows = [
        {"id": "workflow-1", "status": "active"},
        {"id": "workflow-2", "status": "draft"},
    ]
    store.tasks = [
        {
            "id": "task-1",
            "status": "completed",
            "tokens": 120,
            "created_at": "2026-04-03T08:10:00+00:00",
        },
        {
            "id": "task-2",
            "status": "running",
            "tokens": 80,
            "created_at": "2026-04-03T10:15:00+00:00",
        },
        {
            "id": "task-3",
            "status": "pending",
            "tokens": 40,
            "created_at": "2026-04-03T11:40:00+00:00",
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-1",
            "task_id": "task-1",
            "status": "completed",
            "created_at": "2026-04-03T08:10:00+00:00",
        },
        {
            "id": "run-2",
            "task_id": "task-2",
            "status": "running",
            "created_at": "2026-04-03T10:15:00+00:00",
        },
        {
            "id": "run-3",
            "task_id": "task-3",
            "status": "pending",
            "created_at": "2026-04-03T11:40:00+00:00",
        },
    ]
    store.realtime_logs = [
        {
            "id": "log-1",
            "timestamp": "11:40:00",
            "type": "info",
            "agent": "Dispatcher Agent",
            "message": "工作流已排队等待执行",
        }
    ]

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    stats_by_key = {item["key"]: item for item in body["stats"]}

    assert stats_by_key["active_agents"]["value"] == 2
    assert stats_by_key["workflows"]["value"] == 2
    assert stats_by_key["pending_tasks"]["value"] == 2
    assert stats_by_key["today_runs"]["value"] == 3
    assert stats_by_key["run_tokens"]["value"] == 240
    assert stats_by_key["active_agents"]["title"] != "不应再使用"
    assert len(body["chartData"]) == 7
    assert sum(point["requests"] for point in body["chartData"]) == 3
    assert sum(point["tokens"] for point in body["chartData"]) == 240
    assert body["costSummary"]["runCount"] == 3
    assert body["costSummary"]["totalTokens"] == 240
    assert body["tentacleMetrics"][0]["calls"] >= 0
    assert body["agentStatuses"][0]["id"] == "agent-1"
    assert body["realtimeLogs"][0]["id"] == "log-1"


def test_dashboard_stats_fall_back_to_tasks_when_workflow_runs_are_missing(
    auth_headers,
) -> None:
    store.agents = []
    store.workflows = []
    store.workflow_runs = []
    store.tasks = [
        {
            "id": "task-a",
            "status": "completed",
            "tokens": 30,
            "created_at": "2026-04-03T09:00:00+00:00",
        },
        {
            "id": "task-b",
            "status": "failed",
            "tokens": 15,
            "created_at": "2026-04-03T13:00:00+00:00",
        },
    ]
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    stats_by_key = {item["key"]: item for item in body["stats"]}

    assert stats_by_key["today_runs"]["value"] == 2
    assert sum(point["requests"] for point in body["chartData"]) == 2
    assert sum(point["tokens"] for point in body["chartData"]) == 45


def test_dashboard_stats_expose_cost_distribution_and_tentacle_metrics(auth_headers) -> None:
    store.agents = [
        {
            "id": "agent-search",
            "name": "搜索 Agent",
            "type": "search",
            "status": "idle",
            "enabled": True,
            "tasks_completed": 2,
            "tasks_total": 3,
            "tokens_used": 90,
            "success_rate": 66.7,
            "avg_response_time": "320ms",
        }
    ]
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-cost-1",
            "status": "completed",
            "tokens": 90,
            "created_at": "2026-04-03T09:00:00+00:00",
            "completed_at": "2026-04-03T09:01:20+00:00",
            "agent": "搜索 Agent",
        },
        {
            "id": "task-cost-2",
            "status": "failed",
            "tokens": 30,
            "created_at": "2026-04-03T10:00:00+00:00",
            "completed_at": "2026-04-03T10:00:20+00:00",
            "agent": "搜索 Agent",
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-cost-1",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-cost-1",
            "trigger": "message",
            "intent": "search",
            "status": "completed",
            "created_at": "2026-04-03T09:00:00+00:00",
            "updated_at": "2026-04-03T09:01:20+00:00",
            "started_at": "2026-04-03T09:00:00+00:00",
            "completed_at": "2026-04-03T09:01:20+00:00",
            "dispatch_context": {
                "execution_agent": "搜索 Agent",
                "execution_agent_id": "agent-search",
                "run_metrics": {
                    "tokens_total": 90,
                    "duration_ms": 80_000,
                    "step_count": 3,
                    "execution_agent": "搜索 Agent",
                    "execution_agent_id": "agent-search",
                },
            },
        },
        {
            "id": "run-cost-2",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-cost-2",
            "trigger": "message",
            "intent": "search",
            "status": "failed",
            "created_at": "2026-04-03T10:00:00+00:00",
            "updated_at": "2026-04-03T10:00:20+00:00",
            "started_at": "2026-04-03T10:00:00+00:00",
            "completed_at": "2026-04-03T10:00:20+00:00",
            "dispatch_context": {
                "execution_agent": "搜索 Agent",
                "execution_agent_id": "agent-search",
                "run_metrics": {
                    "tokens_total": 30,
                    "duration_ms": 20_000,
                    "step_count": 2,
                    "execution_agent": "搜索 Agent",
                    "execution_agent_id": "agent-search",
                },
            },
        },
    ]
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["costSummary"]["runCount"] == 2
    assert body["costSummary"]["totalTokens"] == 120
    assert body["costSummary"]["totalDurationMs"] == 100000
    assert body["costDistribution"][0]["label"] == "搜索 Agent"
    assert body["costDistribution"][0]["tokens"] == 120
    assert body["tentacleMetrics"][0]["name"] == "搜索 Agent"
    assert body["tentacleMetrics"][0]["calls"] == 3
    assert body["tentacleMetrics"][0]["successCalls"] == 2


def test_dashboard_stats_expose_sla_summary_health_signals_and_alerts(auth_headers) -> None:
    store.agents = []
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-sla-1",
            "status": "completed",
            "tokens": 32,
            "created_at": "2026-04-03T09:00:00+00:00",
            "completed_at": "2026-04-03T09:00:30+00:00",
        },
        {
            "id": "task-sla-2",
            "status": "failed",
            "tokens": 24,
            "created_at": "2026-04-03T10:00:00+00:00",
            "completed_at": "2026-04-03T10:00:20+00:00",
        },
        {
            "id": "task-sla-3",
            "status": "completed",
            "tokens": 18,
            "created_at": "2026-04-03T11:00:00+00:00",
            "completed_at": "2026-04-03T11:00:25+00:00",
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-sla-1",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-sla-1",
            "trigger": "message",
            "intent": "search",
            "status": "completed",
            "created_at": "2026-04-03T09:00:00+00:00",
            "updated_at": "2026-04-03T09:00:30+00:00",
            "started_at": "2026-04-03T09:00:00+00:00",
            "completed_at": "2026-04-03T09:00:30+00:00",
            "dispatch_context": {
                "run_metrics": {"tokens_total": 32, "duration_ms": 30_000, "step_count": 3},
            },
        },
        {
            "id": "run-sla-2",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-sla-2",
            "trigger": "message",
            "intent": "search",
            "status": "failed",
            "created_at": "2026-04-03T10:00:00+00:00",
            "updated_at": "2026-04-03T10:00:20+00:00",
            "started_at": "2026-04-03T10:00:00+00:00",
            "completed_at": "2026-04-03T10:00:20+00:00",
            "dispatch_context": {
                "state": "execution_timeout",
                "failure_stage": "execution",
                "fallback_history": [
                    {
                        "id": "fallback-1",
                        "reason": "execution_timeout",
                        "failure_stage": "execution",
                    }
                ],
                "run_metrics": {"tokens_total": 24, "duration_ms": 20_000, "step_count": 2},
            },
        },
        {
            "id": "run-sla-3",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-sla-3",
            "trigger": "message",
            "intent": "write",
            "status": "completed",
            "created_at": "2026-04-03T11:00:00+00:00",
            "updated_at": "2026-04-03T11:00:25+00:00",
            "started_at": "2026-04-03T11:00:00+00:00",
            "completed_at": "2026-04-03T11:00:25+00:00",
            "dispatch_context": {
                "delivery_status": "failed",
                "failure_stage": "outbound",
                "run_metrics": {"tokens_total": 18, "duration_ms": 25_000, "step_count": 3},
            },
        },
    ]
    store.audit_logs = [
        {
            "id": "audit-sla-1",
            "timestamp": "2026-04-03T09:10:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "u1",
            "resource": "消息入口",
            "status": "error",
            "ip": "127.0.0.1",
            "details": "命中高风险注入",
            "metadata": {"prompt_injection_assessment": {"verdict": "block"}, "trace": {"layer": "prompt_injection"}},
        }
    ]
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["slaSummary"]["totalRuns"] == 3
    assert body["slaSummary"]["successRate"] == 66.7
    assert body["slaSummary"]["failureRate"] == 33.3
    assert body["slaSummary"]["timeoutRate"] == 33.3
    assert body["slaSummary"]["fallbackRate"] == 33.3
    assert body["slaSummary"]["deliveryFailureRate"] == 33.3
    assert body["slaSummary"]["healthStatus"] in {"degraded", "critical"}
    assert any(item["key"] == "timeout_rate" for item in body["healthSignals"])
    assert any(item["severity"] in {"warning", "critical"} for item in body["preparedAlerts"])


def test_dashboard_stats_expose_failure_breakdown(auth_headers) -> None:
    store.agents = []
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-dashboard-dispatch",
            "status": "failed",
            "tokens": 12,
            "created_at": "2026-04-03T09:00:00+00:00",
            "workflow_run_id": "run-dashboard-dispatch",
        },
        {
            "id": "task-dashboard-outbound",
            "status": "completed",
            "tokens": 16,
            "created_at": "2026-04-03T10:00:00+00:00",
            "workflow_run_id": "run-dashboard-outbound",
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-dashboard-dispatch",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-dashboard-dispatch",
            "trigger": "message",
            "status": "failed",
            "created_at": "2026-04-03T09:00:00+00:00",
            "updated_at": "2026-04-03T09:05:00+00:00",
            "started_at": "2026-04-03T09:00:00+00:00",
            "completed_at": "2026-04-03T09:05:00+00:00",
            "current_stage": "执行失败",
            "dispatch_context": {
                "state": "failed",
                "failure_stage": "dispatch",
                "failure_message": "dispatcher unavailable",
            },
        },
        {
            "id": "run-dashboard-outbound",
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": "task-dashboard-outbound",
            "trigger": "message",
            "status": "completed",
            "created_at": "2026-04-03T10:00:00+00:00",
            "updated_at": "2026-04-03T10:03:00+00:00",
            "started_at": "2026-04-03T10:00:00+00:00",
            "completed_at": "2026-04-03T10:03:00+00:00",
            "current_stage": "执行完成",
            "dispatch_context": {
                "state": "completed",
                "failure_stage": "outbound",
                "failure_message": "channel outbound failed",
                "delivery_status": "failed",
                "delivery_message": "channel outbound failed",
            },
        },
    ]
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    failure_breakdown = {item["stage"]: item["count"] for item in response.json()["failureBreakdown"]}
    assert failure_breakdown["dispatch"] == 1
    assert failure_breakdown["outbound"] == 1


def test_dashboard_stats_expose_brain_breakdown(auth_headers) -> None:
    store.agents = []
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-dashboard-chat",
            "status": "completed",
            "tokens": 10,
            "created_at": "2026-04-03T09:00:00+00:00",
            "route_decision": {"interaction_mode": "chat"},
            "manager_packet": {
                "response_contract": "clarify_first",
                "delivery_mode": "conversational",
                "task_shape": "single_step",
            },
        },
        {
            "id": "task-dashboard-structured",
            "status": "running",
            "tokens": 20,
            "created_at": "2026-04-03T10:00:00+00:00",
            "route_decision": {"interaction_mode": "task"},
            "manager_packet": {
                "delivery_mode": "structured_result",
                "task_shape": "multi_step",
            },
        },
    ]
    store.workflow_runs = []
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200


def test_dashboard_logs_support_layer_filter(auth_headers) -> None:
    store.audit_logs = [
        {
            "id": "audit-layer-1",
            "timestamp": "2026-04-12T10:00:00+00:00",
            "action": "安全网关拦截:prompt_injection",
            "user": "alice",
            "resource": "消息入口",
            "status": "error",
            "ip": "127.0.0.1",
            "details": "命中高风险注入",
            "metadata": {"trace": {"layer": "prompt_injection"}},
        },
        {
            "id": "audit-layer-2",
            "timestamp": "2026-04-12T10:05:00+00:00",
            "action": "敏感词检测",
            "user": "bob",
            "resource": "内容策略",
            "status": "warning",
            "ip": "127.0.0.2",
            "details": "已脱敏改写",
            "metadata": {"trace": {"layer": "content_policy_rewrite"}},
        },
    ]

    response = client.get("/api/dashboard/logs?layer=prompt_injection", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "audit-layer-1"


def test_dashboard_stats_expose_manager_queue(auth_headers) -> None:
    store.agents = []
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-manager-clarify",
            "status": "pending",
            "tokens": 8,
            "created_at": "2026-04-03T09:00:00+00:00",
            "title": "需要先澄清的接待任务",
            "manager_packet": {
                "manager_action": "clarify_before_execution",
                "next_owner": "项目经理 Agent",
                "response_contract": "clarify_first",
                "clarify_question": "你更想先推进哪个目标？",
                "delivery_mode": "conversational",
                "task_shape": "single_step",
            },
            "route_decision": {"interaction_mode": "chat"},
        },
        {
            "id": "task-manager-multi-step",
            "status": "running",
            "tokens": 18,
            "created_at": "2026-04-03T10:00:00+00:00",
            "title": "正在编排的多步任务",
            "manager_packet": {
                "manager_action": "handoff_to_execution",
                "next_owner": "搜索 Agent",
                "delivery_mode": "structured_result",
                "task_shape": "multi_step",
            },
            "route_decision": {"interaction_mode": "task"},
            "current_stage": "项目经理分发",
        },
    ]
    store.workflow_runs = []
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    manager_queue = response.json()["managerQueue"]
    assert len(manager_queue) == 2
    assert manager_queue[0]["taskId"] == "task-manager-clarify"
    assert manager_queue[0]["responseContract"] == "clarify_first"
    assert manager_queue[1]["taskShape"] == "multi_step"


def test_dashboard_stats_expose_reply_queue_grouped_by_session(auth_headers) -> None:
    store.agents = []
    store.workflows = [{"id": "workflow-1", "status": "active"}]
    store.tasks = [
        {
            "id": "task-reply-1",
            "status": "pending",
            "tokens": 8,
            "created_at": "2026-04-03T09:00:00+00:00",
            "title": "需要澄清的任务 A",
            "session_id": "telegram:chat-1",
            "user_key": "telegram:user-1",
            "current_stage": "项目经理分发",
            "manager_packet": {
                "response_contract": "clarify_first",
                "clarify_question": "你更想先推进哪个方向？",
                "next_owner": "项目经理 Agent",
            },
        },
        {
            "id": "task-reply-2",
            "status": "running",
            "tokens": 8,
            "created_at": "2026-04-03T09:10:00+00:00",
            "title": "同会话更新后的任务",
            "session_id": "telegram:chat-1",
            "user_key": "telegram:user-1",
            "current_stage": "等待用户回复",
            "manager_packet": {
                "response_contract": "clarify_first",
                "clarify_question": "你更想先推进哪个方向？",
                "next_owner": "项目经理 Agent",
            },
        },
        {
            "id": "task-reply-3",
            "status": "running",
            "tokens": 8,
            "created_at": "2026-04-03T10:00:00+00:00",
            "title": "另一会话澄清任务",
            "session_id": "telegram:chat-2",
            "user_key": "telegram:user-2",
            "current_stage": "等待用户回复",
            "manager_packet": {
                "response_contract": "clarify_first",
                "clarify_question": "你现在最关心时效还是质量？",
                "next_owner": "项目经理 Agent",
            },
        },
    ]
    store.workflow_runs = []
    store.realtime_logs = []

    response = client.get("/api/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    reply_queue = response.json()["replyQueue"]
    assert len(reply_queue) == 2
    assert reply_queue[0]["taskId"] == "task-reply-2"
    assert reply_queue[0]["channel"] == "telegram"
    assert reply_queue[0]["userLabel"] == "user-1"
    assert reply_queue[0]["sessionId"] == "telegram:chat-1"
    assert reply_queue[1]["taskId"] == "task-reply-3"


def test_dashboard_metrics_export_prometheus_text_contains_runtime_sla_and_alerts(
    auth_headers,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    store.agents = []
    store.workflows = [{"id": "workflow-metrics", "status": "active"}]
    store.tasks = [
        {
            "id": "task-metrics-1",
            "status": "completed",
            "tokens": 20,
            "created_at": (now - timedelta(minutes=5)).isoformat(),
        },
        {
            "id": "task-metrics-2",
            "status": "failed",
            "tokens": 10,
            "created_at": (now - timedelta(minutes=3)).isoformat(),
        },
    ]
    store.workflow_runs = [
        {
            "id": "run-metrics-stale",
            "workflow_id": "workflow-metrics",
            "workflow_name": "Metrics Workflow",
            "task_id": "task-metrics-1",
            "status": "pending",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "updated_at": now.isoformat(),
            "next_dispatch_at": (now + timedelta(minutes=1)).isoformat(),
            "dispatch_failure_count": 2,
            "dispatch_context": {"state": "execution_timeout"},
        },
        {
            "id": "run-metrics-dead",
            "workflow_id": "workflow-metrics",
            "workflow_name": "Metrics Workflow",
            "task_id": "task-metrics-2",
            "status": "failed",
            "created_at": (now - timedelta(minutes=3)).isoformat(),
            "updated_at": now.isoformat(),
            "dispatch_context": {
                "state": "failed",
                "delivery_status": "failed",
                "fallback_history": [{"id": "fallback-1", "reason": "runtime_error"}],
                "protocol": {"dead_letter": True},
            },
        },
    ]
    store.audit_logs = []
    store.realtime_logs = []

    monkeypatch.setattr(
        persistence_service,
        "list_workflow_dispatch_jobs",
        lambda: [
            {
                "run_id": "run-metrics-stale",
                "workflow_id": "workflow-metrics",
                "dispatcher_id": "dispatcher-1",
                "lease_expires_at": (now - timedelta(minutes=1)).isoformat(),
                "available_at": (now + timedelta(minutes=1)).isoformat(),
            }
        ],
    )
    monkeypatch.setattr(
        persistence_service,
        "list_workflow_execution_jobs",
        lambda: [
            {
                "run_id": "run-metrics-dead",
                "workflow_id": "workflow-metrics",
                "worker_id": "worker-1",
                "lease_expires_at": (now + timedelta(minutes=2)).isoformat(),
                "available_at": now.isoformat(),
            }
        ],
    )
    monkeypatch.setattr(
        persistence_service,
        "list_agent_execution_jobs",
        lambda: [
            {
                "run_id": "run-metrics-dead",
                "workflow_id": "workflow-metrics",
                "worker_id": "",
                "available_at": (now + timedelta(minutes=3)).isoformat(),
                "protocol": {"dead_letter": True},
            }
        ],
    )

    response = client.get("/api/dashboard/metrics", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert "workbot_runtime_queue_depth_total 3" in text
    assert 'workbot_runtime_queue_depth{queue="dispatch"} 1' in text
    assert "workbot_runtime_stale_claims_total 1" in text
    assert "workbot_runtime_dead_letters_total 1" in text
    assert "workbot_sla_success_rate 0" in text
    assert "workbot_sla_failure_rate 50" in text
    assert "workbot_alerts_prepared_total" in text
    assert "workbot_alerts_runtime_total" in text


def test_dashboard_metrics_accepts_metrics_scrape_token(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "metrics_scrape_token", "metrics-token-123")

    response = client.get(
        "/api/dashboard/metrics",
        headers={
            "x-test-no-auth": "1",
            "X-WorkBot-Metrics-Token": "metrics-token-123",
        },
    )

    assert response.status_code == 200
    assert "workbot_runtime_queue_depth_total" in response.text


def test_dashboard_metrics_rejects_invalid_metrics_scrape_token(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "metrics_scrape_token", "metrics-token-123")

    response = client.get(
        "/api/dashboard/metrics",
        headers={
            "x-test-no-auth": "1",
            "X-WorkBot-Metrics-Token": "wrong-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid metrics scrape token"
