from datetime import datetime

from fastapi import HTTPException, status

from app.services.persistence_service import persistence_service
from app.services.store import store
from app.services.workflow_execution_service import (
    infer_task_intent,
    restart_workflow_run_for_task,
    schedule_retry_follow_up,
    sync_workflow_run_from_task,
    tick_workflow_run,
)


def _now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


FAILURE_STAGE_LABELS = {
    "route": "路由",
    "dispatch": "调度",
    "execution": "执行",
    "outbound": "回传",
}

DISPATCH_STATE_LABELS = {
    "queued": "等待调度",
    "dispatching": "调度中",
    "dispatched": "已派发",
    "agent_queued": "等待 Agent 执行",
    "executing": "执行中",
    "completed": "执行完成",
    "failed": "执行失败",
    "execution_timeout": "执行超时",
    "agent_execution_failed": "Agent 执行失败",
}


def _normalize_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _task_dispatch_context(run: dict | None) -> dict:
    dispatch_context = (run or {}).get("dispatch_context")
    return dispatch_context if isinstance(dispatch_context, dict) else {}


def _dispatch_context_value(dispatch_context: dict, *keys: str) -> str | None:
    for key in keys:
        value = _normalize_text(dispatch_context.get(key))
        if value is not None:
            return value
    return None


def _safe_load_task_steps(task_id: str) -> list[dict]:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        store.task_steps[task_id] = store.clone(database_steps)
        return store.clone(database_steps)
    if getattr(persistence_service, "enabled", False):
        return store.clone(store.task_steps.get(task_id, []))
    return store.clone(store.task_steps.get(task_id, []))


def _normalize_failure_stage(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in FAILURE_STAGE_LABELS:
        return normalized
    return None


def _infer_failure_stage_from_step(step: dict | None) -> str | None:
    if not isinstance(step, dict):
        return None
    haystack = " ".join(
        str(step.get(key) or "").strip().lower()
        for key in ("title", "agent", "message")
    )
    if not haystack:
        return None
    if any(keyword in haystack for keyword in ("路由", "intent", "master bot")):
        return "route"
    if any(keyword in haystack for keyword in ("调度", "dispatcher")):
        return "dispatch"
    if any(keyword in haystack for keyword in ("回传", "发送结果", "输出")):
        return "outbound"
    if any(keyword in haystack for keyword in ("执行", "agent", "超时")):
        return "execution"
    return None


def _latest_failed_step(steps: list[dict] | None) -> dict | None:
    if not isinstance(steps, list):
        return None
    for step in reversed(steps):
        if str(step.get("status") or "").strip().lower() == "failed":
            return step
    return None


def _latest_active_step(steps: list[dict] | None) -> dict | None:
    if not isinstance(steps, list):
        return None
    for status_value in ("running", "pending"):
        for step in reversed(steps):
            if str(step.get("status") or "").strip().lower() == status_value:
                return step
    return None


def _derive_failure_stage(
    task: dict,
    *,
    run: dict | None,
    steps: list[dict],
    delivery_status: str | None,
) -> str | None:
    dispatch_context = _task_dispatch_context(run)
    explicit_failure_stage = _normalize_failure_stage(
        dispatch_context.get("failure_stage") or dispatch_context.get("failureStage")
    )
    if explicit_failure_stage is not None:
        return explicit_failure_stage

    dispatch_state = _dispatch_context_value(dispatch_context, "state", "dispatch_state", "dispatchState")
    if dispatch_state in {"execution_timeout", "agent_execution_failed"}:
        return "execution"

    if _normalize_text((run or {}).get("last_dispatch_error")) is not None:
        return "dispatch"

    failed_step = _latest_failed_step(steps)
    inferred_from_step = _infer_failure_stage_from_step(failed_step)
    if inferred_from_step is not None:
        return inferred_from_step

    if str(task.get("status") or "").strip().lower() == "completed" and delivery_status == "failed":
        return "outbound"
    return None


def _derive_failure_message(
    task: dict,
    *,
    run: dict | None,
    steps: list[dict],
    failure_stage: str | None,
    delivery_status: str | None,
    delivery_message: str | None,
) -> str | None:
    dispatch_context = _task_dispatch_context(run)
    explicit_message = _dispatch_context_value(dispatch_context, "failure_message", "failureMessage")
    if explicit_message is not None:
        return explicit_message

    dispatch_error = _normalize_text((run or {}).get("last_dispatch_error"))
    if dispatch_error is not None:
        return dispatch_error

    failed_step = _latest_failed_step(steps)
    if failed_step is not None:
        failed_step_message = _normalize_text(failed_step.get("message"))
        if failed_step_message is not None:
            return failed_step_message

    if str(task.get("status") or "").strip().lower() == "completed" and failure_stage == "outbound":
        return delivery_message if delivery_status == "failed" else None
    return None


def _derive_current_stage(task: dict, *, run: dict | None, steps: list[dict]) -> str:
    run_stage = _normalize_text((run or {}).get("current_stage"))
    if run_stage is not None:
        return run_stage

    active_step = _latest_active_step(steps)
    if active_step is not None:
        return _normalize_text(active_step.get("title")) or "执行中"

    failed_step = _latest_failed_step(steps)
    if failed_step is not None:
        return _normalize_text(failed_step.get("title")) or "执行失败"

    task_status = str(task.get("status") or "").strip().lower()
    if task_status == "completed":
        return "执行完成"
    if task_status == "failed":
        return "执行失败"
    if task_status == "cancelled":
        return "已取消"
    if task_status == "running":
        return "执行中"
    return "等待开始"


def _build_status_reason(
    task: dict,
    *,
    current_stage: str,
    dispatch_state: str | None,
    failure_stage: str | None,
    failure_message: str | None,
    delivery_status: str | None,
    delivery_message: str | None,
) -> str | None:
    task_status = str(task.get("status") or "").strip().lower()
    if task_status == "failed" and failure_stage is not None:
        stage_label = FAILURE_STAGE_LABELS.get(failure_stage, failure_stage)
        if failure_message is not None:
            return f"失败于{stage_label}阶段：{failure_message}"
        return f"失败于{stage_label}阶段"

    if delivery_status == "failed":
        return delivery_message or "结果已生成，但渠道回传失败"
    if delivery_status == "skipped":
        return delivery_message or "结果已生成，但当前未自动回传到外部渠道"

    if task_status in {"pending", "running"}:
        if current_stage:
            return f"当前阶段：{current_stage}"
        dispatch_label = DISPATCH_STATE_LABELS.get(str(dispatch_state or "").strip().lower())
        if dispatch_label is not None:
            return dispatch_label

    if task_status == "completed":
        if delivery_status == "sent":
            return "执行完成，结果已自动回传"
        return "执行完成"
    return None


def enrich_task_payload(
    task: dict,
    *,
    run: dict | None = None,
    steps: list[dict] | None = None,
) -> dict:
    payload = store.clone(task)
    route_decision = payload.get("route_decision") or payload.get("routeDecision")
    if isinstance(route_decision, dict):
        if "confirmation_status" in route_decision or "confirmationStatus" in route_decision:
            payload.setdefault(
                "confirmation_status",
                route_decision.get("confirmation_status", route_decision.get("confirmationStatus")),
            )
        if "approval_status" in route_decision or "approvalStatus" in route_decision:
            payload.setdefault(
                "approval_status",
                route_decision.get("approval_status", route_decision.get("approvalStatus")),
            )
        if "approval_required" in route_decision or "approvalRequired" in route_decision:
            payload.setdefault(
                "approval_required",
                route_decision.get("approval_required", route_decision.get("approvalRequired")),
            )
        if "audit_id" in route_decision or "auditId" in route_decision:
            payload.setdefault("audit_id", route_decision.get("audit_id", route_decision.get("auditId")))
        if "idempotency_key" in route_decision or "idempotencyKey" in route_decision:
            payload.setdefault(
                "idempotency_key",
                route_decision.get("idempotency_key", route_decision.get("idempotencyKey")),
            )
        if "execution_scope" in route_decision or "executionScope" in route_decision:
            payload.setdefault(
                "execution_scope",
                route_decision.get("execution_scope", route_decision.get("executionScope")),
            )
        if "schedule_plan" in route_decision or "schedulePlan" in route_decision:
            payload.setdefault("schedule_plan", route_decision.get("schedule_plan", route_decision.get("schedulePlan")))
    workflow_run = run if isinstance(run, dict) else _find_loaded_run(payload.get("workflow_run_id"))
    step_items = steps if isinstance(steps, list) else _safe_load_task_steps(str(payload.get("id") or ""))
    dispatch_context = _task_dispatch_context(workflow_run)
    dispatch_state = _dispatch_context_value(dispatch_context, "state", "dispatch_state", "dispatchState")
    delivery_status = _dispatch_context_value(
        dispatch_context,
        "delivery_status",
        "deliveryStatus",
    )
    delivery_message = _dispatch_context_value(
        dispatch_context,
        "delivery_message",
        "deliveryMessage",
    )
    failure_stage = _derive_failure_stage(
        payload,
        run=workflow_run,
        steps=step_items,
        delivery_status=delivery_status,
    )
    failure_message = _derive_failure_message(
        payload,
        run=workflow_run,
        steps=step_items,
        failure_stage=failure_stage,
        delivery_status=delivery_status,
        delivery_message=delivery_message,
    )
    current_stage = _derive_current_stage(payload, run=workflow_run, steps=step_items)
    payload["current_stage"] = current_stage
    payload["dispatch_state"] = dispatch_state
    payload["failure_stage"] = failure_stage
    payload["failure_message"] = failure_message
    payload["delivery_status"] = delivery_status
    payload["delivery_message"] = delivery_message
    payload["status_reason"] = _build_status_reason(
        payload,
        current_stage=current_stage,
        dispatch_state=dispatch_state,
        failure_stage=failure_stage,
        failure_message=failure_message,
        delivery_status=delivery_status,
        delivery_message=delivery_message,
    )
    return payload


def _find_task(task_id: str) -> dict:
    task = _read_task_mutable(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


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
        run_id = str(item.get("workflow_run_id") or "").strip()
        if run_id not in run_cache:
            run_cache[run_id] = _find_loaded_run(run_id) if run_id else None
        enriched_items.append(enrich_task_payload(item, run=run_cache[run_id]))
    return {"items": enriched_items, "total": len(enriched_items)}


def get_task(task_id: str) -> dict:
    return enrich_task_payload(_read_task(task_id))


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
