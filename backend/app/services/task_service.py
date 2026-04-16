from datetime import datetime

from fastapi import HTTPException, status

from app.brain_core.task_view import task_view_service
from app.services.persistence_service import persistence_service
from app.services.store import store
from app.services.tenancy_service import attach_scope, matches_scope
from app.services.workflow_execution_service import (
    infer_task_intent,
    restart_workflow_run_for_task,
    schedule_retry_follow_up,
    sync_workflow_run_from_task,
    tick_workflow_run,
)


def _now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _find_task(task_id: str) -> dict:
    task = _read_task_mutable(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _safe_load_task_steps(task_id: str) -> list[dict]:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        store.task_steps[task_id] = store.clone(database_steps)
        return store.clone(database_steps)
    if getattr(persistence_service, "enabled", False):
        return store.clone(store.task_steps.get(task_id, []))
    return store.clone(store.task_steps.get(task_id, []))


def _find_task_mutable(task_id: str) -> dict:
    task = _read_task_mutable(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _find_cached_task(task_id: str) -> dict | None:
    for task in store.tasks:
        if task["id"] == task_id:
            return task
    return None


def _sync_cached_task(task_payload: dict) -> dict:
    task_id = str(task_payload.get("id") or "").strip()
    cached_task = _find_cached_task(task_id)
    payload = store.clone(task_payload)
    if cached_task is None:
        store.tasks.append(payload)
        return payload

    cached_task.clear()
    cached_task.update(payload)
    return cached_task


def _load_database_task(task_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_task = persistence_service.get_task(task_id)
    if database_task is not None:
        return database_task, True

    database_tasks = persistence_service.list_tasks()
    if database_tasks is None:
        return None, True

    for candidate in database_tasks:
        if str(candidate.get("id") or "").strip() == task_id:
            return candidate, True
    return None, True


def _load_database_run(run_id: str) -> tuple[dict | None, bool]:
    if not getattr(persistence_service, "enabled", False):
        return None, False

    database_run = persistence_service.get_workflow_run(run_id)
    if database_run is not None:
        return database_run, True

    database_runs = persistence_service.list_workflow_runs()
    if database_runs is None:
        return None, True

    for candidate in database_runs:
        if str(candidate.get("id") or "").strip() == run_id:
            return candidate, True
    return None, True


def _read_task_mutable(task_id: str) -> dict | None:
    database_task, database_authoritative = _load_database_task(task_id)
    if database_authoritative:
        if database_task is None:
            return None
        return _sync_cached_task(database_task)
    return _find_cached_task(task_id)


def _ensure_task_execution_context_loaded(task: dict) -> None:
    workflow_id = str(task.get("workflow_id") or "").strip()
    run_id = str(task.get("workflow_run_id") or "").strip()

    if workflow_id and all(str(workflow.get("id")) != workflow_id for workflow in store.workflows):
        database_workflow = persistence_service.get_workflow(workflow_id)
        if database_workflow is not None:
            store.workflows.append(store.clone(database_workflow))

    if run_id and all(str(run.get("id")) != run_id for run in store.workflow_runs):
        database_run = persistence_service.get_workflow_run(run_id)
        if database_run is not None:
            store.workflow_runs.insert(0, store.clone(database_run))


def _read_task(task_id: str) -> dict:
    task = _read_task_mutable(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return store.clone(task)


def _persist_task_execution_state(task: dict, *, include_steps: bool = True) -> None:
    task_steps = (
        store.task_steps.get(str(task.get("id") or ""), [])
        if include_steps
        else None
    )
    persist_execution_state = getattr(persistence_service, "persist_execution_state", None)
    if callable(persist_execution_state):
        if persist_execution_state(
            task=task,
            task_steps=task_steps,
        ):
            return
        if getattr(persistence_service, "enabled", False):
            return
    persistence_service.persist_runtime_state()


def _read_task_steps(task_id: str) -> list[dict]:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        if not database_steps:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task steps not found")
        return database_steps
    if getattr(persistence_service, "enabled", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task steps not found")
    if task_id not in store.task_steps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task steps not found")
    return store.clone(store.task_steps[task_id])


def _find_loaded_run(run_id: str | None) -> dict | None:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return None

    database_run, database_authoritative = _load_database_run(normalized_run_id)
    if database_authoritative:
        if database_run is None:
            return None
        payload = store.clone(database_run)
        for run in store.workflow_runs:
            if str(run.get("id")) == normalized_run_id:
                run.clear()
                run.update(payload)
                return run
        store.workflow_runs.insert(0, payload)
        return payload

    for run in store.workflow_runs:
        if str(run.get("id")) == normalized_run_id:
            return run
    return None


def _load_retry_intent_steps(task_id: str) -> list[dict]:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        store.task_steps[task_id] = store.clone(database_steps)
        return store.clone(store.task_steps[task_id])
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.task_steps.get(task_id, []))


def _apply_task_filters(
    items: list[dict],
    *,
    status_filter: str | None = None,
    search: str | None = None,
    priority_filter: str | None = None,
    agent_filter: str | None = None,
    channel_filter: str | None = None,
) -> list[dict]:
    filtered_items = items

    if status_filter:
        filtered_items = [task for task in filtered_items if task["status"] == status_filter]

    if search:
        keyword = search.lower()
        filtered_items = [
            task
            for task in filtered_items
            if keyword in task["title"].lower()
            or keyword in task["description"].lower()
            or keyword in str(task.get("agent") or "").lower()
            or keyword in str(task.get("channel") or "").lower()
        ]

    if priority_filter:
        normalized_priority = priority_filter.strip().lower()
        filtered_items = [
            task
            for task in filtered_items
            if str(task.get("priority") or "").strip().lower() == normalized_priority
        ]

    if agent_filter:
        normalized_agent = agent_filter.strip().lower()
        filtered_items = [
            task
            for task in filtered_items
            if str(task.get("agent") or "").strip().lower() == normalized_agent
        ]

    if channel_filter:
        normalized_channel = channel_filter.strip().lower()
        filtered_items = [
            task
            for task in filtered_items
            if str(task.get("channel") or "").strip().lower() == normalized_channel
        ]

    return filtered_items


def _build_retry_bootstrap_steps(task: dict, *, intent: str, started_at: str) -> list[dict]:
    return [
        {
            "id": f"{task['id']}-retry-1",
            "title": "任务重试",
            "status": "completed",
            "agent": "Task Center",
            "started_at": started_at,
            "finished_at": started_at,
            "message": f"已收到重试请求，准备按 {intent} 链路重新建立执行上下文",
            "tokens": 0,
        }
    ]


def list_tasks(
    status_filter: str | None = None,
    search: str | None = None,
    priority_filter: str | None = None,
    agent_filter: str | None = None,
    channel_filter: str | None = None,
    scope: dict[str, str] | None = None,
) -> dict:
    items = persistence_service.list_tasks(
        status_filter=status_filter,
        search=search,
        priority_filter=priority_filter,
        agent_filter=agent_filter,
        channel_filter=channel_filter,
    )
    if items is None:
        if getattr(persistence_service, "enabled", False):
            items = []
        else:
            items = _apply_task_filters(
                store.clone(store.tasks),
                status_filter=status_filter,
                search=search,
                priority_filter=priority_filter,
                agent_filter=agent_filter,
                channel_filter=channel_filter,
            )
    run_cache: dict[str, dict | None] = {}
    enriched_items: list[dict] = []
    for item in items:
        task_id = str(item.get("id") or "").strip()
        run_id = str(item.get("workflow_run_id") or "").strip()
        if run_id not in run_cache:
            run_cache[run_id] = _find_loaded_run(run_id) if run_id else None
        enriched = task_view_service.build_scoped_task_projection(
            item,
            run=run_cache[run_id],
            steps=_safe_load_task_steps(task_id),
            attach_scope_fn=attach_scope,
        )
        if scope is not None and not matches_scope(enriched, scope):
            continue
        enriched_items.append(enriched)
    return task_view_service.build_task_list_response(enriched_items)


def get_task(task_id: str, *, scope: dict[str, str] | None = None) -> dict:
    task = _read_task(task_id)
    run_id = str(task.get("workflow_run_id") or "").strip()
    payload = task_view_service.build_scoped_task_projection(
        task,
        run=_find_loaded_run(run_id) if run_id else None,
        steps=_safe_load_task_steps(task_id),
        attach_scope_fn=attach_scope,
    )
    if scope is not None and not matches_scope(payload, scope):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return payload


def get_task_steps(task_id: str) -> dict:
    items = _read_task_steps(task_id)
    return {"items": items, "total": len(items)}


def cancel_task(task_id: str) -> dict:
    task = _find_task_mutable(task_id)
    _ensure_task_execution_context_loaded(task)
    task["status"] = "cancelled"
    task["duration"] = task["duration"] or "--"
    task["completed_at"] = task.get("completed_at") or _now_display()
    try:
        sync_workflow_run_from_task(task)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND or exc.detail != "Workflow run not found":
            raise
        _persist_task_execution_state(task, include_steps=False)
    return {"ok": True, "message": f"Task {task_id} cancelled", "task": store.clone(task)}


def retry_task(task_id: str) -> dict:
    task = _find_task_mutable(task_id)
    _ensure_task_execution_context_loaded(task)
    retry_intent = infer_task_intent(
        task,
        run=_find_loaded_run(task.get("workflow_run_id")),
        steps=_load_retry_intent_steps(task_id),
    )
    started_at = _now_display()
    store.task_steps[task_id] = _build_retry_bootstrap_steps(
        task,
        intent=retry_intent,
        started_at=started_at,
    )
    run = restart_workflow_run_for_task(
        task,
        intent=retry_intent,
        trigger="task.retry",
    )
    tick_workflow_run(run["id"], auto_schedule=False)
    schedule_retry_follow_up(run["id"])

    return {
        "ok": True,
        "message": f"Task {task_id} restarted",
        "task": store.clone(task),
    }
