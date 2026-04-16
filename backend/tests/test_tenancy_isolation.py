from fastapi.testclient import TestClient

from app.core.event_protocol import build_event_envelope
from app.main import app
from app.services.event_journal_service import record_event_publish_attempt
from app.services.store import store


client = TestClient(app)


def _seed_scope_task(task_id: str, run_id: str, *, tenant_id: str, project_id: str, environment: str) -> None:
    store.tasks.append(
        {
            "id": task_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "environment": environment,
            "workflow_run_id": run_id,
            "workflow_id": "workflow-1",
            "title": f"Task {task_id}",
            "description": "scope test",
            "status": "running",
            "priority": "medium",
            "created_at": store.now_string(),
            "completed_at": None,
            "agent": "Master Bot Planner",
            "tokens": 0,
            "result": None,
        }
    )
    store.task_steps[task_id] = []
    store.workflow_runs.insert(
        0,
        {
            "id": run_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "environment": environment,
            "workflow_id": "workflow-1",
            "workflow_name": "客户服务工作流",
            "task_id": task_id,
            "trigger": "manual",
            "intent": "search",
            "status": "running",
            "created_at": store.now_string(),
            "updated_at": store.now_string(),
            "started_at": store.now_string(),
            "completed_at": None,
            "current_stage": "执行中",
            "active_edges": [],
            "nodes": [],
            "logs": [],
            "dispatch_context": {
                "state": "executing",
                "scope": {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "environment": environment,
                },
            },
        },
    )


def test_operator_can_filter_tasks_by_scope(auth_headers_factory) -> None:
    _seed_scope_task("task-tenant-alpha", "run-tenant-alpha", tenant_id="tenant-alpha", project_id="project-a", environment="prod")
    _seed_scope_task("task-tenant-beta", "run-tenant-beta", tenant_id="tenant-beta", project_id="project-b", environment="prod")

    response = client.get(
        "/api/tasks",
        headers={
            **auth_headers_factory(role="operator"),
            "X-WorkBot-Tenant-Id": "tenant-alpha",
            "X-WorkBot-Project-Id": "project-a",
            "X-WorkBot-Environment": "prod",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["tenantId"] == "tenant-alpha"
    assert payload["items"][0]["projectId"] == "project-a"


def test_viewer_cannot_cross_tenant_scope(auth_headers_factory) -> None:
    user_id = "viewer-scope-user"
    store.user_profiles[user_id] = {
        "id": user_id,
        "tenant_id": "tenant-alpha",
        "project_id": "project-a",
        "environment": "prod",
    }

    response = client.get(
        "/api/tasks",
        headers={
            **auth_headers_factory(role="viewer", user_id=user_id, email="viewer.scope@example.test"),
            "X-WorkBot-Tenant-Id": "tenant-beta",
            "X-WorkBot-Project-Id": "project-b",
            "X-WorkBot-Environment": "prod",
        },
    )

    assert response.status_code == 403
    assert "Cross-scope access denied" in response.json()["detail"]


def test_workflow_run_detail_hides_other_tenant_run_for_non_root(auth_headers_factory) -> None:
    _seed_scope_task("task-hidden-run", "run-hidden-run", tenant_id="tenant-beta", project_id="project-b", environment="prod")
    user_id = "viewer-run-user"
    store.user_profiles[user_id] = {
        "id": user_id,
        "tenant_id": "tenant-alpha",
        "project_id": "project-a",
        "environment": "prod",
    }

    response = client.get(
        "/api/workflows/runs/run-hidden-run",
        headers=auth_headers_factory(role="viewer", user_id=user_id, email="viewer.run@example.test"),
    )

    assert response.status_code == 404


def test_dashboard_logs_and_events_are_scope_filtered(auth_headers_factory) -> None:
    store.audit_logs.insert(
        0,
        {
            "id": "audit-tenant-alpha",
            "tenant_id": "tenant-alpha",
            "project_id": "project-a",
            "environment": "prod",
            "timestamp": store.now_string(),
            "action": "tenant alpha log",
            "user": "alpha@example.test",
            "resource": "scope.alpha",
            "status": "success",
            "ip": "-",
            "details": "alpha only",
        },
    )
    store.audit_logs.insert(
        0,
        {
            "id": "audit-tenant-beta",
            "tenant_id": "tenant-beta",
            "project_id": "project-b",
            "environment": "prod",
            "timestamp": store.now_string(),
            "action": "tenant beta log",
            "user": "beta@example.test",
            "resource": "scope.beta",
            "status": "success",
            "ip": "-",
            "details": "beta only",
        },
    )
    event = build_event_envelope(
        subject="brain.workflow.run.updated",
        event_name="brain.workflow.run.updated",
        aggregate={"type": "workflow_run", "id": "run-scope-alpha"},
        payload={"run_id": "run-scope-alpha"},
    )
    event["tenant_id"] = "tenant-alpha"
    event["project_id"] = "project-a"
    event["environment"] = "prod"
    record_event_publish_attempt(event["subject"], event)

    headers = {
        **auth_headers_factory(role="operator"),
        "X-WorkBot-Tenant-Id": "tenant-alpha",
        "X-WorkBot-Project-Id": "project-a",
        "X-WorkBot-Environment": "prod",
    }
    logs_response = client.get("/api/dashboard/logs", headers=headers)
    events_response = client.get("/api/events", headers=headers)

    assert logs_response.status_code == 200
    assert all(item["tenantId"] == "tenant-alpha" for item in logs_response.json()["items"])
    assert events_response.status_code == 200
    assert events_response.json()["total"] >= 1
    assert all(item["tenantId"] == "tenant-alpha" for item in events_response.json()["items"])
