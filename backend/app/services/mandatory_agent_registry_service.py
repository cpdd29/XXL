from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from app.services.agent_config_service import agent_config_service, build_agent_config_summary
from app.services.persistence_service import persistence_service
from app.services.store import store


logger = logging.getLogger(__name__)

MANDATORY_AGENT_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "conversation",
        "name": "对话 Agent",
        "description": "负责接待用户、澄清需求并整理结构化需求包。",
        "type": "conversation",
    },
    {
        "id": "requirement_dispatcher",
        "name": "需求分析任务分发 Agent",
        "description": "负责整理需求、判断执行路径并把任务分发到外接触手执行层。",
        "type": "task_dispatcher",
    },
    {
        "id": "security",
        "name": "安全 Agent",
        "description": "负责语义级风险审查、升级审批建议与安全审计说明。",
        "type": "security",
    },
    {
        "id": "security-guardian",
        "name": "Security Guardian",
        "description": "负责主脑本地安全网关、脱敏审计与处罚状态治理。",
        "type": "security_guardian",
    },
    {
        "id": "workflow_designer",
        "name": "创建工作流 Agent",
        "description": "负责读取可用能力并生成需要人工审批的工作流提案。",
        "type": "workflow_planner",
    },
    {
        "id": "memory",
        "name": "记忆 Agent",
        "description": "负责租户内人员画像蒸馏、偏好抽取与记忆治理。",
        "type": "memory",
    },
)


def _clone(value: object) -> object:
    clone = getattr(store, "clone", None)
    if callable(clone):
        return clone(value)
    return deepcopy(value)


def _find_runtime_agent(agent_id: str) -> dict[str, Any] | None:
    for agent in getattr(store, "agents", []):
        if str(agent.get("id") or "").strip() == agent_id:
            return agent
    return None


def _upsert_runtime_agent(agent_payload: dict[str, Any]) -> dict[str, Any]:
    cloned = _clone(agent_payload)
    existing = _find_runtime_agent(str(agent_payload.get("id") or "").strip())
    if existing is None:
        getattr(store, "agents", []).append(cloned)
        return cloned

    existing.clear()
    existing.update(cloned)
    return existing


def _snapshot_runtime(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        return None
    return _clone(runtime)


def _build_agent_payload(
    spec: dict[str, str],
    *,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": spec["id"],
        "name": spec["name"],
        "description": spec["description"],
        "type": spec["type"],
        "status": str((existing or {}).get("status") or "idle"),
        "enabled": bool((existing or {}).get("enabled", True)),
        "tasks_completed": int((existing or {}).get("tasks_completed") or 0),
        "tasks_total": int((existing or {}).get("tasks_total") or 0),
        "avg_response_time": str((existing or {}).get("avg_response_time") or "--"),
        "tokens_used": int((existing or {}).get("tokens_used") or 0),
        "tokens_limit": int((existing or {}).get("tokens_limit") or 0),
        "success_rate": float((existing or {}).get("success_rate") or 0.0),
        "last_active": str((existing or {}).get("last_active") or "未运行"),
    }
    config_snapshot = agent_config_service.load_agent_config(payload)
    existing_runtime = _snapshot_runtime((existing or {}).get("config_snapshot"))
    if existing_runtime:
        config_snapshot["runtime"] = existing_runtime
    payload["config_snapshot"] = config_snapshot
    payload["config_summary"] = build_agent_config_summary(config_snapshot)
    return payload


def ensure_mandatory_agents_registered() -> dict[str, Any]:
    created: list[str] = []
    updated: list[str] = []
    items: list[dict[str, Any]] = []

    for spec in MANDATORY_AGENT_SPECS:
        agent_id = spec["id"]
        existing = _find_runtime_agent(agent_id)
        payload = _build_agent_payload(spec, existing=existing)
        persisted = _upsert_runtime_agent(payload)
        if existing is None:
            created.append(agent_id)
            logger.info("Registered mandatory agent %s", agent_id)
        else:
            updated.append(agent_id)
            logger.info("Refreshed mandatory agent %s", agent_id)
        persistence_service.persist_agent_state(agent=persisted)
        items.append(_clone(persisted))

    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "items": items,
        "total": len(items),
    }
