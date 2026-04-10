from __future__ import annotations

from app.services import workflow_execution_service
from app.services.store import store


def _task(task_id: str, *, status: str = "running") -> dict:
    created_at = store.now_string()
    return {
        "id": task_id,
        "workflow_run_id": f"run-{task_id}",
        "title": "调度失败测试任务",
        "description": "验证调度失败收敛逻辑",
        "status": status,
        "priority": "high",
        "created_at": created_at,
        "completed_at": None,
        "agent": "搜索Agent",
        "tokens": 64,
        "duration": None,
        "result": {"kind": "search_report"},
    }


def _run(run_id: str, task_id: str, *, status: str = "running") -> dict:
    created_at = store.now_string()
    return {
        "id": run_id,
        "workflow_id": "workflow-1",
        "workflow_name": "客户服务工作流",
        "task_id": task_id,
        "trigger": "message",
        "intent": "search",
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "current_stage": "执行节点",
        "active_edges": [],
        "nodes": [],
        "logs": [],
        "memory_hits": 0,
        "warnings": [],
        "dispatch_failure_count": 0,
        "last_dispatch_error": None,
    }


def test_fail_workflow_run_due_dispatch_failure_marks_running_step_failed(monkeypatch) -> None:
    task_id = "task-dispatch-running"
    run_id = "run-task-dispatch-running"
    store.tasks.append(_task(task_id))
    store.workflow_runs.insert(0, _run(run_id, task_id))
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "执行节点",
            "status": "running",
            "agent": "搜索Agent",
            "started_at": store.now_string(),
            "finished_at": None,
            "message": "正在执行搜索",
            "tokens": 64,
        }
    ]

    published: list[tuple[str, str]] = []
    cancelled: list[str] = []
    persisted: list[bool] = []
    monkeypatch.setattr(
        workflow_execution_service,
        "_publish_run_event",
        lambda run, event_type: published.append((run["id"], event_type)),
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: cancelled.append(run_id),
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_persist_runtime_state",
        lambda: persisted.append(True),
    )

    payload = workflow_execution_service.fail_workflow_run_due_dispatch_failure(
        run_id,
        failure_message="调度推进连续失败，任务已终止",
    )
    task = next(item for item in store.tasks if item["id"] == task_id)

    assert payload["id"] == run_id
    assert payload["status"] == "failed"
    assert task["status"] == "failed"
    assert task["completed_at"] is not None
    assert task["duration"] == "调度失败"
    assert task["result"] is None
    assert store.task_steps[task_id][0]["status"] == "failed"
    assert store.task_steps[task_id][0]["finished_at"] is not None
    assert store.task_steps[task_id][0]["message"] == "调度推进连续失败，任务已终止"
    search_node = next(node for node in payload["nodes"] if node["label"] == "搜索 Agent")
    assert search_node["status"] == "error"
    assert search_node["latest_error"] == "调度推进连续失败，任务已终止"
    assert search_node["error_count"] == 1
    assert search_node["error_history"][0]["source"] == "task_step"
    assert search_node["error_history"][0]["step_title"] == "执行节点"
    assert cancelled == [run_id]
    assert published == [(run_id, "workflow_run.updated")]
    assert persisted == [True]


def test_fail_workflow_run_due_dispatch_failure_appends_failed_step_without_running_step(
    monkeypatch,
) -> None:
    task_id = "task-dispatch-no-running-step"
    run_id = "run-task-dispatch-no-running-step"
    store.tasks.append(_task(task_id))
    store.workflow_runs.insert(0, _run(run_id, task_id))
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "安全网关",
            "status": "completed",
            "agent": "安全网关",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": "已完成安全校验",
            "tokens": 12,
        }
    ]

    cancelled: list[str] = []
    monkeypatch.setattr(
        workflow_execution_service,
        "_publish_run_event",
        lambda run, event_type: None,
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: cancelled.append(run_id),
    )
    monkeypatch.setattr(
        workflow_execution_service,
        "_persist_runtime_state",
        lambda: None,
    )

    payload = workflow_execution_service.fail_workflow_run_due_dispatch_failure(
        run_id,
        failure_message="调度失败后补充终态步骤",
    )

    task = next(item for item in store.tasks if item["id"] == task_id)
    appended_step = store.task_steps[task_id][-1]

    assert payload["status"] == "failed"
    assert task["status"] == "failed"
    assert appended_step["title"] == "调度异常"
    assert appended_step["status"] == "failed"
    assert appended_step["agent"] == "Workflow Dispatcher"
    assert appended_step["message"] == "调度失败后补充终态步骤"
    assert appended_step["finished_at"] is not None
    assert cancelled == [run_id]


def test_fail_workflow_run_due_dispatch_failure_falls_back_when_workflow_is_missing(
    monkeypatch,
) -> None:
    task_id = "task-dispatch-missing-workflow"
    run_id = "run-task-dispatch-missing-workflow"
    store.tasks.append(_task(task_id))
    store.workflow_runs.insert(
        0,
        _run(run_id, task_id) | {"workflow_id": "workflow-missing", "workflow_name": "已删除工作流"},
    )
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "执行节点",
            "status": "running",
            "agent": "搜索Agent",
            "started_at": store.now_string(),
            "finished_at": None,
            "message": "工作流定义已删除，但任务仍在执行",
            "tokens": 64,
        }
    ]

    cancelled: list[str] = []
    monkeypatch.setattr(workflow_execution_service, "_publish_run_event", lambda run, event_type: None)
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: cancelled.append(run_id),
    )
    monkeypatch.setattr(workflow_execution_service, "_persist_runtime_state", lambda: None)

    payload = workflow_execution_service.fail_workflow_run_due_dispatch_failure(
        run_id,
        failure_message="工作流已删除，调度失败应直接终止",
    )

    assert payload["status"] == "failed"
    assert payload["current_stage"] == "执行失败"
    assert payload["nodes"] == []
    assert payload["active_edges"] == []
    assert any("工作流已删除" in log["message"] for log in payload["logs"])
    assert cancelled == [run_id]


def test_tick_workflow_run_returns_terminal_state_when_workflow_is_missing(
    monkeypatch,
) -> None:
    task_id = "task-terminal-missing-workflow"
    run_id = "run-task-terminal-missing-workflow"
    task = _task(task_id, status="cancelled")
    task["completed_at"] = store.now_string()
    task["duration"] = "--"
    store.tasks.append(task)
    store.workflow_runs.insert(
        0,
        _run(run_id, task_id, status="running") | {"workflow_id": "workflow-missing", "workflow_name": "已删除工作流"},
    )
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "执行节点",
            "status": "completed",
            "agent": "搜索Agent",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": "任务已经被取消",
            "tokens": 64,
        }
    ]

    cancelled: list[str] = []
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: cancelled.append(run_id),
    )
    monkeypatch.setattr(workflow_execution_service, "_persist_runtime_state", lambda: None)

    payload = workflow_execution_service.tick_workflow_run(run_id, auto_schedule=False)

    assert payload["status"] == "cancelled"
    assert payload["current_stage"] == "已取消"
    assert payload["nodes"] == []
    assert payload["active_edges"] == []
    assert any("已取消" in log["message"] for log in payload["logs"])
    assert cancelled == [run_id]


def test_fail_workflow_run_due_dispatch_failure_keeps_terminal_state_when_workflow_is_missing(
    monkeypatch,
) -> None:
    task_id = "task-terminal-dispatch-missing-workflow"
    run_id = "run-task-terminal-dispatch-missing-workflow"
    task = _task(task_id, status="cancelled")
    task["completed_at"] = store.now_string()
    task["duration"] = "--"
    store.tasks.append(task)
    store.workflow_runs.insert(
        0,
        _run(run_id, task_id, status="running") | {"workflow_id": "workflow-missing", "workflow_name": "已删除工作流"},
    )
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "执行节点",
            "status": "completed",
            "agent": "搜索Agent",
            "started_at": store.now_string(),
            "finished_at": store.now_string(),
            "message": "任务已被外部取消",
            "tokens": 64,
        }
    ]

    cancelled: list[str] = []
    monkeypatch.setattr(workflow_execution_service, "_publish_run_event", lambda run, event_type: None)
    monkeypatch.setattr(
        workflow_execution_service,
        "_cancel_scheduled_run",
        lambda run_id: cancelled.append(run_id),
    )
    monkeypatch.setattr(workflow_execution_service, "_persist_runtime_state", lambda: None)

    payload = workflow_execution_service.fail_workflow_run_due_dispatch_failure(
        run_id,
        failure_message="这条失败不应覆盖已经取消的任务",
    )

    assert payload["status"] == "cancelled"
    assert payload["current_stage"] == "已取消"
    assert payload["nodes"] == []
    assert payload["active_edges"] == []
    assert any("已取消" in log["message"] for log in payload["logs"])
    assert cancelled == [run_id]


def test_get_workflow_run_preserves_dispatch_warning_archive_on_selected_node() -> None:
    task_id = "task-dispatch-warning-archive"
    run_id = "run-task-dispatch-warning-archive"
    warning_message = "调度推进失败，已延后 2.0s 重试：tick failed"
    store.tasks.append(_task(task_id))
    store.workflow_runs.insert(
        0,
        _run(run_id, task_id)
        | {
            "logs": [
                {
                    "id": "dispatch-warning-1",
                    "timestamp": "10:00:00",
                    "occurred_at": store.now_string(),
                    "type": "warning",
                    "agent": "Workflow Dispatcher",
                    "source": "dispatcher",
                    "message": warning_message,
                }
            ],
            "warnings": [warning_message],
        },
    )
    store.task_steps[task_id] = [
        {
            "id": f"{task_id}-1",
            "title": "执行节点",
            "status": "running",
            "agent": "搜索Agent",
            "started_at": store.now_string(),
            "finished_at": None,
            "message": "正在执行搜索",
            "tokens": 64,
        }
    ]

    payload = workflow_execution_service.get_workflow_run(run_id)

    search_node = next(node for node in payload["nodes"] if node["label"] == "搜索 Agent")
    assert search_node["status"] == "running"
    assert search_node["error_count"] == 1
    assert search_node["latest_error"] == warning_message
    assert search_node["error_history"][0]["source"] == "dispatcher"
    assert search_node["error_history"][0]["severity"] == "warning"
    assert warning_message in [log["message"] for log in payload["logs"]]
