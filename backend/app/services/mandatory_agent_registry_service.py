from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import logging
from typing import Any

from app.services.agent_config_service import agent_config_service, build_agent_config_summary
from app.services.mandatory_workflow_registry_service import (
    CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION,
    CONVERSATION_AGENT_PIPELINE_INPUT_CONTRACT,
    CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT,
    CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
    GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION,
    GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT,
    GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT,
    GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID,
    SECURITY_AGENT_PIPELINE_CONTRACT_VERSION,
    SECURITY_AGENT_PIPELINE_INPUT_CONTRACT,
    SECURITY_AGENT_PIPELINE_OUTPUT_CONTRACT,
    SECURITY_AGENT_PIPELINE_WORKFLOW_ID,
)
from app.services.persistence_service import persistence_service
from app.services.store import LEGACY_AGENT_IDS, LEGACY_WORKFLOW_IDS, store


logger = logging.getLogger(__name__)
DEFAULT_AGENT_WORKFLOW_CONTRACT_VERSION = "agent-workflow-contract-v1"
MANDATORY_AGENT_SUPPRESSION_SETTING_KEY = "mandatory_agent_registry.suppressed_agent_ids"

MANDATORY_AGENT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "conversation",
        "name": "对话 Agent",
        "description": "负责接待用户、澄清需求并整理结构化需求包。",
        "type": "conversation",
        "agent_workflow_binding": {
            "agent_workflow_id": CONVERSATION_AGENT_PIPELINE_WORKFLOW_ID,
            "input_contract": deepcopy(CONVERSATION_AGENT_PIPELINE_INPUT_CONTRACT),
            "output_contract": deepcopy(CONVERSATION_AGENT_PIPELINE_OUTPUT_CONTRACT),
            "contract_version": CONVERSATION_AGENT_PIPELINE_CONTRACT_VERSION,
        },
    },
    {
        "id": "general_assistant",
        "name": "万事通 Agent",
        "description": "负责承接通用答疑、专业知识查询和联网查询后的统一结果整理。",
        "type": "default",
        "agent_workflow_binding": {
            "agent_workflow_id": GENERAL_ASSISTANT_AGENT_PIPELINE_WORKFLOW_ID,
            "input_contract": deepcopy(GENERAL_ASSISTANT_AGENT_PIPELINE_INPUT_CONTRACT),
            "output_contract": deepcopy(GENERAL_ASSISTANT_AGENT_PIPELINE_OUTPUT_CONTRACT),
            "contract_version": GENERAL_ASSISTANT_AGENT_PIPELINE_CONTRACT_VERSION,
        },
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
        "agent_workflow_binding": {
            "agent_workflow_id": SECURITY_AGENT_PIPELINE_WORKFLOW_ID,
            "input_contract": deepcopy(SECURITY_AGENT_PIPELINE_INPUT_CONTRACT),
            "output_contract": deepcopy(SECURITY_AGENT_PIPELINE_OUTPUT_CONTRACT),
            "contract_version": SECURITY_AGENT_PIPELINE_CONTRACT_VERSION,
        },
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
    {
        "id": "search",
        "name": "搜索 Agent",
        "description": "负责轻闭环检索与轻量执行，是前半段搜索/轻执行分流的稳定承接能力。",
        "type": "search",
        "builtin_config": {
            "version": "builtin-search-light-v1",
            "trigger_intents": ["search", "help", "manual"],
            "capabilities": [
                "information_retrieval",
                "live_information_lookup",
                "weather_lookup",
                "pdf_processing",
                "document_conversion",
                "lightweight_execution",
                "lightweight_closed_loop",
                "professional_escalation_judgement",
            ],
            "tools": [
                {
                    "id": "local_document_search",
                    "name": "local_document_search",
                    "description": "使用本地项目知识库与文档检索能力产出可引用结果。",
                },
                {
                    "id": "search_light_execution_skill",
                    "name": "search_light_execution_skill",
                    "description": "统一处理检索、天气、轻量文件转换和升级判断等轻闭环任务。",
                }
            ],
            "warnings": ["未找到搜索 Agent 目录，已使用 mandatory registry 内置的搜索/轻执行兜底配置。"],
        },
    },
    {
        "id": "write",
        "name": "写作 Agent",
        "description": "负责本地写作执行，作为外接触手写作分支的稳定兜底能力。",
        "type": "write",
        "builtin_config": {
            "version": "builtin-write-v1",
            "trigger_intents": ["write", "help"],
            "capabilities": [
                "write",
                "draft",
                "drafting",
                "rewriting",
                "summarization",
                "translation",
            ],
            "tools": [
                {
                    "id": "local_writer",
                    "name": "local_writer",
                    "description": "使用本地写作执行器生成可直接交付的草稿与回复。",
                }
            ],
            "warnings": ["未找到写作 Agent 目录，已使用 mandatory registry 内置配置。"],
        },
    },
)
MANDATORY_AGENT_SPECS = tuple(
    spec for spec in MANDATORY_AGENT_SPECS if str(spec.get("id") or "").strip() not in LEGACY_AGENT_IDS
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


def _active_mandatory_agent_specs() -> tuple[dict[str, Any], ...]:
    suppressed_agent_ids = _read_suppressed_mandatory_agent_ids()
    return tuple(
        spec
        for spec in MANDATORY_AGENT_SPECS
        if str(spec.get("id") or "").strip() not in LEGACY_AGENT_IDS
        and str(spec.get("id") or "").strip() not in suppressed_agent_ids
    )


def is_mandatory_agent_id(agent_id: str | None) -> bool:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return False
    return any(
        str(spec.get("id") or "").strip() == normalized_agent_id for spec in MANDATORY_AGENT_SPECS
    )


def _read_suppressed_mandatory_agent_ids() -> set[str]:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        payload, authoritative = read_setting(MANDATORY_AGENT_SUPPRESSION_SETTING_KEY)
        if authoritative:
            setting_payload = payload.get("payload") if isinstance(payload, dict) else None
            values = setting_payload if isinstance(setting_payload, list) else []
            return {
                str(value or "").strip()
                for value in values
                if str(value or "").strip() and is_mandatory_agent_id(str(value or "").strip())
            }

    runtime_value = store.system_settings.get(MANDATORY_AGENT_SUPPRESSION_SETTING_KEY)
    values = runtime_value if isinstance(runtime_value, list) else []
    return {
        str(value or "").strip()
        for value in values
        if str(value or "").strip() and is_mandatory_agent_id(str(value or "").strip())
    }


def _write_suppressed_mandatory_agent_ids(agent_ids: set[str]) -> bool:
    payload = sorted(
        {
            str(agent_id or "").strip()
            for agent_id in agent_ids
            if str(agent_id or "").strip() and is_mandatory_agent_id(str(agent_id or "").strip())
        }
    )
    store.system_settings[MANDATORY_AGENT_SUPPRESSION_SETTING_KEY] = _clone(payload)
    if not getattr(persistence_service, "enabled", False):
        return True
    persist_setting = getattr(persistence_service, "persist_system_setting", None)
    if callable(persist_setting):
        return bool(
            persist_setting(
                key=MANDATORY_AGENT_SUPPRESSION_SETTING_KEY,
                payload=payload,
                updated_at=store.now_string(),
            )
        )
    return True


def suppress_mandatory_agent(agent_id: str | None) -> bool:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id or not is_mandatory_agent_id(normalized_agent_id):
        return False
    suppressed_agent_ids = _read_suppressed_mandatory_agent_ids()
    suppressed_agent_ids.add(normalized_agent_id)
    return _write_suppressed_mandatory_agent_ids(suppressed_agent_ids)


def get_mandatory_agent_projection(
    agent_id: str | None,
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return None

    spec = next(
        (
            candidate
            for candidate in _active_mandatory_agent_specs()
            if str(candidate.get("id") or "").strip() == normalized_agent_id
        ),
        None,
    )
    if spec is None:
        return None
    return _build_agent_payload(spec, existing=existing)


def list_mandatory_agent_projections(
    *,
    existing_agents: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing_by_id = {
        str(agent.get("id") or "").strip(): agent
        for agent in (existing_agents or [])
        if str(agent.get("id") or "").strip()
    }
    return [
        _build_agent_payload(
            spec,
            existing=existing_by_id.get(str(spec.get("id") or "").strip()),
        )
        for spec in _active_mandatory_agent_specs()
    ]


def _purge_legacy_agents() -> None:
    delete_agents = getattr(store, "delete_agents", None)
    removed_runtime: list[str] = []
    if callable(delete_agents):
        removed_runtime = list(delete_agents(LEGACY_AGENT_IDS))
    else:
        retained_agents = []
        for agent in getattr(store, "agents", []):
            agent_id = str(agent.get("id") or "").strip()
            if agent_id in LEGACY_AGENT_IDS:
                removed_runtime.append(agent_id)
                continue
            retained_agents.append(agent)
        store.agents = retained_agents

    removed_persistence = persistence_service.delete_agent_states(agent_ids=list(LEGACY_AGENT_IDS))
    if removed_runtime:
        logger.info("Purged legacy mandatory agents from runtime store: %s", ", ".join(removed_runtime))
    if removed_persistence:
        logger.info("Purged %s legacy mandatory agents from persistence", removed_persistence)


def _normalize_workflow_ids(
    workflow_ids: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
) -> set[str]:
    values = workflow_ids if workflow_ids is not None else LEGACY_WORKFLOW_IDS
    return {str(workflow_id or "").strip() for workflow_id in values if str(workflow_id or "").strip()}


def _clear_agent_workflow_binding_snapshot(
    config_snapshot: dict[str, Any] | None,
    *,
    workflow_ids: set[str],
) -> tuple[dict[str, Any] | None, bool]:
    snapshot = _clone(config_snapshot) if isinstance(config_snapshot, dict) else None
    if not isinstance(snapshot, dict):
        return snapshot, False

    changed = False
    agent_doc = snapshot.get("agent")
    runtime = snapshot.get("runtime")
    binding_workflow_id = ""
    if isinstance(runtime, dict):
        binding = runtime.get("agent_workflow_binding")
        if isinstance(binding, dict):
            binding_workflow_id = str(binding.get("agent_workflow_id") or "").strip()
    if not binding_workflow_id and isinstance(agent_doc, dict):
        binding_workflow_id = str(agent_doc.get("agent_workflow_id") or "").strip()

    if binding_workflow_id not in workflow_ids:
        return snapshot, False

    if isinstance(agent_doc, dict):
        for key in ("agent_workflow_id", "input_contract", "output_contract", "contract_version"):
            if key in agent_doc:
                agent_doc.pop(key, None)
                changed = True
    if isinstance(runtime, dict) and "agent_workflow_binding" in runtime:
        runtime.pop("agent_workflow_binding", None)
        changed = True
    return snapshot, changed


def _strip_removed_workflow_binding_from_agent(
    agent: dict[str, Any],
    *,
    workflow_ids: set[str],
) -> bool:
    current_workflow_id = str(agent.get("agent_workflow_id") or "").strip()
    next_snapshot, snapshot_changed = _clear_agent_workflow_binding_snapshot(
        agent.get("config_snapshot"),
        workflow_ids=workflow_ids,
    )
    if current_workflow_id not in workflow_ids and not snapshot_changed:
        return False

    if current_workflow_id in workflow_ids:
        agent.pop("agent_workflow_id", None)
        agent.pop("input_contract", None)
        agent.pop("output_contract", None)
        agent.pop("contract_version", None)
    if snapshot_changed:
        agent["config_snapshot"] = next_snapshot
    if "config_snapshot" in agent:
        agent["config_summary"] = build_agent_config_summary(agent.get("config_snapshot"))
    return True


def purge_removed_workflow_agent_bindings(
    *,
    workflow_ids: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    normalized_workflow_ids = _normalize_workflow_ids(workflow_ids)
    if not normalized_workflow_ids:
        return {"ok": True, "workflow_ids": [], "sanitized_agent_ids": [], "total": 0}

    sanitized_agent_ids: list[str] = []
    seen_agent_ids: set[str] = set()
    runtime_agents = getattr(store, "agents", [])
    persist_agent_state = getattr(persistence_service, "persist_agent_state", None)

    for agent in runtime_agents:
        agent_id = str(agent.get("id") or "").strip()
        if not agent_id or agent_id in seen_agent_ids:
            continue
        if not _strip_removed_workflow_binding_from_agent(agent, workflow_ids=normalized_workflow_ids):
            continue
        if callable(persist_agent_state):
            persist_agent_state(agent=agent)
        sanitized_agent_ids.append(agent_id)
        seen_agent_ids.add(agent_id)

    persisted_agents = persistence_service.list_agents() or []
    for agent in persisted_agents:
        agent_id = str(agent.get("id") or "").strip()
        if not agent_id or agent_id in seen_agent_ids:
            continue
        if not _strip_removed_workflow_binding_from_agent(agent, workflow_ids=normalized_workflow_ids):
            continue
        if callable(persist_agent_state):
            persist_agent_state(agent=agent)
        sanitized_agent_ids.append(agent_id)
        seen_agent_ids.add(agent_id)

    if sanitized_agent_ids:
        logger.info(
            "Cleared removed workflow bindings from agents: %s",
            ", ".join(sanitized_agent_ids),
        )

    return {
        "ok": True,
        "workflow_ids": sorted(normalized_workflow_ids),
        "sanitized_agent_ids": sanitized_agent_ids,
        "total": len(sanitized_agent_ids),
    }


def _snapshot_runtime(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        return None
    return _clone(runtime)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _should_use_builtin_config_snapshot(
    spec: dict[str, Any],
    config_snapshot: dict[str, Any] | None,
) -> bool:
    if not isinstance(spec.get("builtin_config"), dict):
        return False
    if not isinstance(config_snapshot, dict):
        return True
    if str(config_snapshot.get("status") or "").strip().lower() != "missing":
        return False
    return config_snapshot.get("directory") in {None, ""}


def _build_builtin_config_snapshot(
    spec: dict[str, Any],
    *,
    existing_runtime: dict[str, Any] | None,
) -> dict[str, Any]:
    builtin_config = spec.get("builtin_config")
    assert isinstance(builtin_config, dict)
    snapshot = {
        "agent_id": spec["id"],
        "status": "builtin",
        "directory": None,
        "version": str(builtin_config.get("version") or "builtin-v1"),
        "loaded_at": _now_iso(),
        "files_loaded": [],
        "warnings": list(builtin_config.get("warnings") or ["已使用 mandatory registry 内置配置。"]),
        "agent": {
            "agent_id": spec["id"],
            "name": spec["name"],
            "agent_family": spec["type"],
            "type": spec["type"],
            "trigger_intents": list(builtin_config.get("trigger_intents") or []),
            "capabilities": list(builtin_config.get("capabilities") or []),
        },
        "soul": None,
        "tools": {"tools": list(builtin_config.get("tools") or [])},
        "memory_rules": None,
        "examples": [],
    }
    if existing_runtime:
        snapshot["runtime"] = existing_runtime
    return snapshot


def _apply_agent_workflow_binding(
    config_snapshot: dict[str, Any] | None,
    *,
    binding: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot = _clone(config_snapshot) if isinstance(config_snapshot, dict) else {}
    if not isinstance(binding, dict):
        return snapshot

    workflow_id = str(binding.get("agent_workflow_id") or "").strip()
    if not workflow_id:
        return snapshot

    input_contract = binding.get("input_contract") if isinstance(binding.get("input_contract"), dict) else {}
    output_contract = binding.get("output_contract") if isinstance(binding.get("output_contract"), dict) else {}
    contract_version = (
        str(binding.get("contract_version") or DEFAULT_AGENT_WORKFLOW_CONTRACT_VERSION).strip()
        or DEFAULT_AGENT_WORKFLOW_CONTRACT_VERSION
    )

    agent_doc = snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        agent_doc = {}
    agent_doc["agent_workflow_id"] = workflow_id
    agent_doc["input_contract"] = _clone(input_contract)
    agent_doc["output_contract"] = _clone(output_contract)
    agent_doc["contract_version"] = contract_version
    snapshot["agent"] = agent_doc

    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime["agent_workflow_binding"] = {
        "agent_workflow_id": workflow_id,
        "input_contract": _clone(input_contract),
        "output_contract": _clone(output_contract),
        "contract_version": contract_version,
        "source": "mandatory_registry",
    }
    snapshot["runtime"] = runtime
    return snapshot


def _extract_agent_workflow_binding(config_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(config_snapshot, dict):
        return None

    runtime = config_snapshot.get("runtime")
    if isinstance(runtime, dict):
        binding = runtime.get("agent_workflow_binding")
        if isinstance(binding, dict):
            workflow_id = str(binding.get("agent_workflow_id") or "").strip()
            if workflow_id:
                return {
                    "agent_workflow_id": workflow_id,
                    "input_contract": _clone(binding.get("input_contract"))
                    if isinstance(binding.get("input_contract"), dict)
                    else {},
                    "output_contract": _clone(binding.get("output_contract"))
                    if isinstance(binding.get("output_contract"), dict)
                    else {},
                    "contract_version": str(binding.get("contract_version") or "").strip() or None,
                }

    agent_doc = config_snapshot.get("agent")
    if not isinstance(agent_doc, dict):
        return None
    workflow_id = str(agent_doc.get("agent_workflow_id") or "").strip()
    if not workflow_id:
        return None
    return {
        "agent_workflow_id": workflow_id,
        "input_contract": _clone(agent_doc.get("input_contract"))
        if isinstance(agent_doc.get("input_contract"), dict)
        else {},
        "output_contract": _clone(agent_doc.get("output_contract"))
        if isinstance(agent_doc.get("output_contract"), dict)
        else {},
        "contract_version": str(agent_doc.get("contract_version") or "").strip() or None,
    }


def _build_agent_payload(
    spec: dict[str, Any],
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
    if _should_use_builtin_config_snapshot(spec, config_snapshot):
        config_snapshot = _build_builtin_config_snapshot(spec, existing_runtime=existing_runtime)
    if existing_runtime:
        config_snapshot["runtime"] = existing_runtime
    config_snapshot = _apply_agent_workflow_binding(
        config_snapshot,
        binding=spec.get("agent_workflow_binding"),
    )
    workflow_binding = _extract_agent_workflow_binding(config_snapshot) or {}
    payload["config_snapshot"] = config_snapshot
    payload["config_summary"] = build_agent_config_summary(config_snapshot)
    payload["agent_workflow_id"] = str(workflow_binding.get("agent_workflow_id") or "").strip() or None
    payload["input_contract"] = (
        _clone(workflow_binding.get("input_contract"))
        if isinstance(workflow_binding.get("input_contract"), dict)
        else {}
    )
    payload["output_contract"] = (
        _clone(workflow_binding.get("output_contract"))
        if isinstance(workflow_binding.get("output_contract"), dict)
        else {}
    )
    payload["contract_version"] = str(workflow_binding.get("contract_version") or "").strip() or None
    return payload


def ensure_mandatory_agents_registered() -> dict[str, Any]:
    _purge_legacy_agents()
    purge_removed_workflow_agent_bindings()

    created: list[str] = []
    updated: list[str] = []
    items: list[dict[str, Any]] = []

    for spec in _active_mandatory_agent_specs():
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
