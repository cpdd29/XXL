from __future__ import annotations

from fastapi import HTTPException, status

from app.services.persistence_service import persistence_service
from app.services.store import store
from app.services.task_service import enrich_task_payload
from app.services.workflow_execution_service import get_workflow_run

SEARCH_KEYWORDS = ("搜索", "文档", "知识库", "规格", "检索")
WRITE_KEYWORDS = ("写作", "回复", "邮件", "生成", "咨询", "账单")
NODE_AGENT_TYPES = {
    "trigger": None,
    "condition": None,
    "aggregate": None,
    "output": "output",
    "安全检测": "security",
    "意图识别": "intent",
    "搜索 Agent": "search",
    "写作 Agent": "write",
}


def _load_tasks() -> list[dict]:
    database_tasks = persistence_service.list_tasks()
    if database_tasks is not None:
        return database_tasks
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.tasks)


def _load_workflows() -> list[dict]:
    database_workflows = persistence_service.list_workflows()
    if database_workflows is not None:
        return database_workflows
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.workflows)


def _load_task_steps(task_id: str) -> list[dict]:
    database_steps = persistence_service.get_task_steps(task_id)
    if database_steps is not None:
        return database_steps
    if getattr(persistence_service, "enabled", False):
        return []
    return store.clone(store.task_steps.get(task_id, []))


def _get_selected_task(task_id: str | None) -> dict:
    tasks = _load_tasks()
    if task_id:
        for task in tasks:
            if task["id"] == task_id:
                return task
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    for task in tasks:
        if task["status"] == "running":
            return task

    if tasks:
        return tasks[0]

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No tasks available")


def _get_primary_workflow() -> dict:
    workflows = _load_workflows()
    if not workflows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflows[0]


def _get_workflow_by_id(workflow_id: str | None) -> dict:
    workflows = _load_workflows()
    if workflow_id:
        for workflow in workflows:
            if workflow["id"] == workflow_id:
                return workflow
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return _get_primary_workflow()


def _infer_branch(task: dict) -> str:
    combined = f"{task['title']} {task['description']} {task['agent']}"
    if any(keyword in combined for keyword in SEARCH_KEYWORDS):
        return "search"
    if any(keyword in combined for keyword in WRITE_KEYWORDS):
        return "write"
    return "write"


def _find_step(steps: list[dict], *keywords: str) -> dict | None:
    for step in steps:
        haystack = f"{step.get('title', '')} {step.get('agent', '')} {step.get('message', '')}"
        if any(keyword in haystack for keyword in keywords):
            return step
    return None


def _status_from_task_step(task_step: dict | None, fallback: str = "idle") -> str:
    if not task_step:
        return fallback
    raw_status = task_step.get("status")
    if raw_status == "completed":
        return "completed"
    if raw_status == "running":
        return "running"
    if raw_status == "failed":
        return "error"
    return fallback


def _build_nodes(workflow: dict, task: dict, steps: list[dict], branch: str) -> list[dict]:
    security_step = _find_step(steps, "安全")
    intent_step = _find_step(steps, "意图")
    search_step = _find_step(steps, "搜索", "检索")
    write_step = _find_step(steps, "写作", "回复")

    nodes: list[dict] = []

    for node in workflow["nodes"]:
        node_id = node["id"]
        label = node["label"]
        node_type = node["type"]
        node_state = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "status": "idle",
            "agent_type": NODE_AGENT_TYPES.get(label, NODE_AGENT_TYPES.get(node_type)),
            "tokens": 0,
            "message": None,
        }

        if node_type == "trigger":
            node_state["status"] = "completed"
            node_state["message"] = "收到新任务，等待 Dispatcher 分发"
        elif label == "安全检测":
            node_state["status"] = _status_from_task_step(
                security_step,
                "completed" if task["status"] != "pending" else "waiting",
            )
            node_state["tokens"] = security_step.get("tokens", 18) if security_step else 18
            node_state["message"] = (
                security_step.get("message")
                if security_step
                else "已完成输入安全检查"
            )
        elif label == "意图识别":
            if intent_step:
                node_state["status"] = _status_from_task_step(intent_step, "completed")
                node_state["tokens"] = intent_step.get("tokens", 64)
                node_state["message"] = intent_step.get("message")
            elif task["status"] == "pending":
                node_state["status"] = "waiting"
                node_state["message"] = "等待路由决策"
            else:
                branch_label = "知识检索" if branch == "search" else "内容生成"
                node_state["status"] = "completed"
                node_state["tokens"] = 64
                node_state["message"] = f"已识别为 {branch_label} 任务"
        elif node_type == "condition":
            if task["status"] == "pending":
                node_state["status"] = "idle"
                node_state["message"] = "等待分支判断"
            else:
                branch_label = "知识检索分支" if branch == "search" else "写作回复分支"
                node_state["status"] = "completed"
                node_state["message"] = f"已命中 {branch_label}"
        elif label == "搜索 Agent":
            if branch == "search":
                node_state["status"] = _status_from_task_step(
                    search_step,
                    "running" if task["status"] == "running" else "completed",
                )
                if task["status"] == "failed":
                    node_state["status"] = "error"
                if task["status"] == "cancelled":
                    node_state["status"] = "idle"
                node_state["tokens"] = search_step.get("tokens", task["tokens"]) if search_step else task["tokens"]
                node_state["message"] = (
                    search_step.get("message")
                    if search_step
                    else "正在检索知识库并整理候选资料"
                )
            else:
                node_state["status"] = "idle"
                node_state["message"] = "当前任务未走检索分支"
        elif label == "写作 Agent":
            if branch == "write":
                node_state["status"] = _status_from_task_step(
                    write_step,
                    "running" if task["status"] == "running" else "completed",
                )
                if task["status"] == "failed":
                    node_state["status"] = "error"
                if task["status"] == "cancelled":
                    node_state["status"] = "idle"
                node_state["tokens"] = write_step.get("tokens", task["tokens"]) if write_step else task["tokens"]
                node_state["message"] = (
                    write_step.get("message")
                    if write_step
                    else "正在生成最终回复草稿"
                )
            else:
                node_state["status"] = "idle"
                node_state["message"] = "当前任务未走写作分支"
        elif node_type == "aggregate":
            if task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "上下游结果已聚合完成"
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "上游节点失败，聚合已终止"
            elif task["status"] == "running":
                node_state["status"] = "waiting"
                node_state["message"] = "等待分支结果汇总"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待上游产出"
        elif node_type == "output":
            if task["status"] == "completed":
                node_state["status"] = "completed"
                node_state["message"] = "结果已发送到目标渠道"
            elif task["status"] == "failed":
                node_state["status"] = "error"
                node_state["message"] = "输出阶段因任务失败未执行"
            elif task["status"] == "running":
                node_state["status"] = "idle"
                node_state["message"] = "等待最终输出"
            else:
                node_state["status"] = "idle"
                node_state["message"] = "等待执行"

        nodes.append(node_state)

    return nodes


def _build_active_edges(task: dict, branch: str, nodes: list[dict]) -> list[str]:
    status_by_label = {node["label"]: node["status"] for node in nodes}
    active_edges = ["e1-2", "e1-3"]

    if status_by_label.get("安全检测") in {"completed", "running", "waiting", "error"}:
        active_edges.append("e2-4")
    if status_by_label.get("意图识别") in {"completed", "running", "waiting", "error"}:
        active_edges.append("e3-4")

    if branch == "search" and status_by_label.get("搜索 Agent") != "idle":
        active_edges.append("e4-5")
        if task["status"] in {"running", "completed", "failed"}:
            active_edges.append("e5-7")
    if branch == "write" and status_by_label.get("写作 Agent") != "idle":
        active_edges.append("e4-6")
        if task["status"] in {"running", "completed", "failed"}:
            active_edges.append("e6-7")

    if task["status"] in {"completed", "failed"}:
        active_edges.append("e7-8")

    return active_edges


def _time_only(value: str | None) -> str:
    if not value:
        return "--:--:--"
    if "T" in value:
        return value.split("T", maxsplit=1)[1][:8]
    if " " in value:
        return value.rsplit(" ", maxsplit=1)[-1][:8]
    return value[:8]


def _build_logs(task: dict, steps: list[dict], branch: str) -> list[dict]:
    logs = [
        {
            "id": f"{task['id']}-received",
            "timestamp": _time_only(task["created_at"]),
            "type": "info",
            "agent": "触发器",
            "message": f"收到任务「{task['title']}」，开始进入协作编排",
        }
    ]

    if task["status"] != "pending":
        logs.append(
            {
                "id": f"{task['id']}-route",
                "timestamp": _time_only(task["created_at"]),
                "type": "success",
                "agent": "意图识别Agent",
                "message": f"Dispatcher 已路由到 {'搜索' if branch == 'search' else '写作'} 分支",
            }
        )

    for step in steps:
        step_status = step.get("status", "completed")
        logs.append(
            {
                "id": step["id"],
                "timestamp": _time_only(step.get("finished_at") or step.get("started_at")),
                "type": (
                    "success"
                    if step_status == "completed"
                    else "info"
                    if step_status == "running"
                    else "error"
                ),
                "agent": step["agent"],
                "message": step.get("message", step["title"]),
            }
        )

    if task["status"] == "completed":
        logs.append(
            {
                "id": f"{task['id']}-done",
                "timestamp": _time_only(task.get("completed_at")),
                "type": "success",
                "agent": "输出Agent",
                "message": "任务执行完成，结果已返回到业务侧",
            }
        )
    elif task["status"] == "failed":
        logs.append(
            {
                "id": f"{task['id']}-failed",
                "timestamp": _time_only(task.get("completed_at") or task["created_at"]),
                "type": "error",
                "agent": task["agent"],
                "message": "任务执行失败，等待人工介入或重试",
            }
        )
    elif task["status"] == "pending":
        logs.append(
            {
                "id": f"{task['id']}-pending",
                "timestamp": _time_only(task["created_at"]),
                "type": "warning",
                "agent": "调度队列",
                "message": "任务仍在排队，等待可用 Agent 资源",
            }
        )

    return list(reversed(logs))


def _build_task_options() -> list[dict]:
    items = sorted(_load_tasks(), key=lambda task: task["created_at"], reverse=True)
    return [
        {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"],
            "priority": task["priority"],
            "agent": task["agent"],
        }
        for task in items[:6]
    ]


def _progress_from_nodes(nodes: list[dict]) -> int:
    weights = {
        "completed": 1.0,
        "running": 0.6,
        "waiting": 0.3,
        "error": 0.6,
        "idle": 0.0,
    }
    total = sum(weights.get(node["status"], 0) for node in nodes)
    return round(total / max(len(nodes), 1) * 100)


def _current_stage(task: dict, nodes: list[dict]) -> str:
    for node in nodes:
        if node["status"] == "running":
            return node["label"]

    if task["status"] == "completed":
        return "执行完成"
    if task["status"] == "failed":
        return "执行失败"
    if task["status"] == "pending":
        return "排队中"

    for node in reversed(nodes):
        if node["status"] in {"completed", "waiting", "error"}:
            return node["label"]

    return "等待开始"


def get_collaboration_overview(task_id: str | None = None) -> dict:
    task = enrich_task_payload(_get_selected_task(task_id))
    if task.get("workflow_run_id"):
        run = get_workflow_run(task["workflow_run_id"])
        task = enrich_task_payload(task, run=run)
        workflow = _get_workflow_by_id(task.get("workflow_id") or run["workflow_id"])
        session = {
            "task_id": task["id"],
            "task_title": task["title"],
            "task_status": task["status"],
            "task_priority": task["priority"],
            "workflow_id": run["workflow_id"],
            "workflow_name": run["workflow_name"],
            "started_at": run["started_at"],
            "completed_at": run.get("completed_at"),
            "total_tokens": task["tokens"],
            "progress_percent": _progress_from_nodes(run["nodes"]),
            "current_stage": task.get("current_stage") or run["current_stage"],
            "failure_stage": task.get("failure_stage"),
            "failure_message": task.get("failure_message"),
            "dispatch_state": task.get("dispatch_state"),
            "delivery_status": task.get("delivery_status"),
            "delivery_message": task.get("delivery_message"),
            "status_reason": task.get("status_reason"),
            "active_agent_count": len([node for node in run["nodes"] if node["status"] == "running"]),
            "completed_steps": len([node for node in run["nodes"] if node["status"] == "completed"]),
            "total_steps": len(run["nodes"]),
            "workflow_run_id": run["id"],
        }
        return {
            "session": session,
            "tasks": _build_task_options(),
            "workflow": workflow,
            "nodes": run["nodes"],
            "active_edges": run["active_edges"],
            "logs": run["logs"],
        }

    workflow = _get_workflow_by_id(task.get("workflow_id"))
    steps = _load_task_steps(task["id"])
    branch = _infer_branch(task)

    nodes = _build_nodes(workflow, task, steps, branch)
    active_edges = _build_active_edges(task, branch, nodes)
    logs = _build_logs(task, steps, branch)

    completed_steps = sum(1 for node in nodes if node["status"] == "completed")
    active_agent_count = sum(
        1
        for node in nodes
        if node["type"] == "agent" and node["status"] in {"running", "waiting"}
    )

    session = {
        "task_id": task["id"],
        "task_title": task["title"],
        "task_status": task["status"],
        "task_priority": task["priority"],
        "workflow_id": workflow["id"],
        "workflow_name": workflow["name"],
        "started_at": task["created_at"],
        "completed_at": task.get("completed_at"),
        "total_tokens": task["tokens"],
        "progress_percent": _progress_from_nodes(nodes),
        "current_stage": task.get("current_stage") or _current_stage(task, nodes),
        "failure_stage": task.get("failure_stage"),
        "failure_message": task.get("failure_message"),
        "dispatch_state": task.get("dispatch_state"),
        "delivery_status": task.get("delivery_status"),
        "delivery_message": task.get("delivery_message"),
        "status_reason": task.get("status_reason"),
        "active_agent_count": active_agent_count,
        "completed_steps": completed_steps,
        "total_steps": len(nodes),
        "workflow_run_id": task.get("workflow_run_id"),
    }

    return {
        "session": session,
        "tasks": _build_task_options(),
        "workflow": workflow,
        "nodes": nodes,
        "active_edges": active_edges,
        "logs": logs,
    }
