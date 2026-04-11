from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import re
from typing import Any
from urllib.parse import quote_plus
from urllib.request import urlopen

from app.services.mcp_runtime_service import MCPRuntimeService, mcp_runtime_service
from app.services import task_service
from app.services.skill_registry_service import SkillRegistryService, skill_registry_service
from app.services.skill_runtime_service import (
    SkillRuntimeService,
    skill_runtime_service,
)


IN_PROGRESS_STATUSES = {
    "pending",
    "running",
    "queued",
    "dispatching",
    "await_worker",
    "agent_queued",
    "executing",
}
WEATHER_HINTS = {"天气", "气温", "温度", "下雨", "预报", "weather", "forecast", "temperature"}
TASK_STATUS_HINTS = {"进行中的任务", "任务状态", "在执行", "running task", "task status", "进行中"}
TASK_LIST_HINTS = {"最近任务", "任务列表", "任务清单", "task list", "my tasks", "tasks"}
SEARCH_HINTS = {"搜索", "检索", "查一下", "查找", "search", "lookup", "find", "web"}
PDF_HINTS = {"pdf", "文档", "文件", "附件"}
SUMMARY_HINTS = {"总结", "摘要", "要点", "summarize", "summary", "highlights"}
SPEECH_HINTS = {"演讲", "发言稿", "演讲稿", "speech", "keynote"}
WRITING_HINTS = {"写", "生成", "草稿", "文案", "稿子", "write", "draft", "copy"}
RUNTIME_ELIGIBLE_SKILLS = {
    "web_search_skill",
    "pdf_read_skill",
    "pdf_summary_skill",
    "weather_skill",
    "speech_writer_skill",
    "general_writer_skill",
}
RUNTIME_TOOL_NAME_CANDIDATES: dict[str, tuple[str, ...]] = {
    "web_search_skill": ("web_search", "search", "web-search"),
    "pdf_read_skill": ("pdf_read", "pdf-read", "pdf_reader"),
    "pdf_summary_skill": ("pdf_summary", "pdf-summary"),
    "weather_skill": ("weather", "get_weather", "weather_lookup"),
    "speech_writer_skill": ("speech_writer", "speech", "writer_speech"),
    "general_writer_skill": ("general_writer", "writer", "copywriter", "text_writer"),
}
# Builtin skills are kept on a strict allowlist:
# - read-only retainers stay in brain for lightweight task/status views
# - transitional fallbacks remain only as external runtime degradation paths
READ_ONLY_BUILTIN_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "id": "skill_task_status",
        "name": "task_status_skill",
        "type": "skill",
        "source": "internal",
        "description": "Query current in-progress tasks.",
        "tags": ["task", "status", "free-workflow", "readonly-retained"],
        "capabilities": ["task_status", "task_query", "task_status_lookup", "task_listing"],
        "timeout_seconds": 2.0,
        "handler_name": "_task_status_skill",
    },
    {
        "id": "skill_task_list",
        "name": "task_list_skill",
        "type": "skill",
        "source": "internal",
        "description": "List recent tasks.",
        "tags": ["task", "list", "free-workflow", "readonly-retained"],
        "capabilities": ["task_list", "task_query", "task_listing", "task_status_lookup"],
        "timeout_seconds": 2.0,
        "handler_name": "_task_list_skill",
    },
)
TRANSITIONAL_FALLBACK_BUILTIN_SKILLS: tuple[dict[str, Any], ...] = ()


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_lower(value: object) -> str:
    return _normalize_text(value).lower()


def _contains_any(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


def _http_get_json(url: str, *, timeout_seconds: float) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            raw = response.read()
    except Exception:
        return None
    try:
        loaded = json.loads(raw.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _stable_bucket(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:8], 16) % 100


def _coerce_percent(value: Any, *, default: int = 0) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = default
    if percent < 0:
        return 0
    if percent > 100:
        return 100
    return percent


def _normalize_mode(value: Any, *, default: str = "builtin_primary") -> str:
    mode = _normalize_lower(value or default)
    if mode not in {"builtin_primary", "runtime_primary"}:
        return default
    return mode


def _env_as_bool(name: str, *, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _tool_sources_mode() -> str:
    mode = _normalize_lower(os.getenv("WORKBOT_TOOL_SOURCES_MODE", "hybrid") or "hybrid")
    if mode not in {"external_only", "hybrid", "local_only"}:
        return "hybrid"
    return mode


def _is_legacy_runtime_source(source: str) -> bool:
    return source in {"local-agents", "local-mcp-services"}


class FreeWorkflowService:
    def __init__(
        self,
        *,
        registry: SkillRegistryService | None = None,
        runtime: SkillRuntimeService | None = None,
        mcp_runtime: MCPRuntimeService | None = None,
    ) -> None:
        self._registry = registry or skill_registry_service
        self._runtime = runtime or (
            skill_runtime_service if self._registry is skill_registry_service else SkillRuntimeService(registry=self._registry)
        )
        self._mcp_runtime = mcp_runtime or mcp_runtime_service
        self._register_builtin_skills()

    def list_skills(
        self,
        *,
        name: str | None = None,
        ability_type: str | None = "skill",
        tag: str | None = None,
        source: str | None = None,
        capability: str | None = None,
        enabled: bool | None = True,
    ) -> list[dict[str, Any]]:
        return self._registry.list_abilities(
            name=name,
            ability_type=ability_type,
            tag=tag,
            source=source,
            capability=capability,
            enabled=enabled,
        )

    def execute_skill(
        self,
        skill_name: str,
        *,
        text: str | None = None,
        payload: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged_payload = dict(payload or {})
        if text and "text" not in merged_payload:
            merged_payload["text"] = text

        normalized_context = context or {}
        mcp_tool_id = self._resolve_runtime_tool_id(skill_name=skill_name)
        strict_external = self._strict_external_skills_enabled()
        policy = self._resolve_runtime_policy(
            skill_name=skill_name,
            payload=merged_payload,
            context=normalized_context,
            mcp_tool_id=mcp_tool_id,
        )
        if strict_external and skill_name in RUNTIME_ELIGIBLE_SKILLS:
            policy = {
                **policy,
                "mode": "runtime_primary",
                "policy_source": "strict_external_runtime",
            }

        runtime_result: dict[str, Any] | None = None
        selected_result: dict[str, Any] | None = None
        selected_path = "builtin"
        fallback_reason = None
        primary_runtime_result: dict[str, Any] | None = None
        shadow_runtime_result: dict[str, Any] | None = None
        external_required_error: str | None = None

        if skill_name in RUNTIME_ELIGIBLE_SKILLS and mcp_tool_id:
            if policy["mode"] == "runtime_primary":
                primary_runtime_result = self._mcp_runtime.invoke_tool(
                    tool_id=mcp_tool_id,
                    payload=merged_payload,
                    trace_context={
                        "workflow_mode": "free_workflow",
                        "selected_skill": skill_name,
                        "execution_mode": "runtime_primary",
                    },
                )
                if primary_runtime_result.get("ok"):
                    selected_path = "runtime"
                else:
                    fallback_reason = str((primary_runtime_result.get("error") or {}).get("message") or "")
                    selected_path = "builtin_fallback"
                    if strict_external:
                        selected_path = "external_runtime_required"
                        external_required_error = (
                            f"external_runtime_required: runtime invoke failed for {skill_name} ({fallback_reason or 'unknown_error'})"
                        )

            if policy["shadow_mode"]:
                shadow_runtime_result = self._mcp_runtime.invoke_shadow_tool(
                    tool_id=mcp_tool_id,
                    payload=merged_payload,
                    trace_context={
                        "workflow_mode": "free_workflow",
                        "selected_skill": skill_name,
                        "execution_mode": "shadow",
                    },
                )
        elif strict_external and skill_name in RUNTIME_ELIGIBLE_SKILLS:
            selected_path = "external_runtime_required"
            fallback_reason = "runtime_tool_not_found"
            external_required_error = (
                f"external_runtime_required: runtime tool not found for {skill_name}"
            )

        if strict_external and skill_name in RUNTIME_ELIGIBLE_SKILLS and selected_path != "runtime":
            selected_result = {
                "ok": False,
                "trace_id": (primary_runtime_result or {}).get("trace_id"),
                "duration_ms": (primary_runtime_result or {}).get("duration_ms"),
                "result": {
                    "summary": "External runtime is required for this skill.",
                    "source": "external_runtime_required",
                    "runtime_result": (primary_runtime_result or {}).get("result"),
                    "runtime_tool_id": mcp_tool_id,
                },
                "result_summary": "External runtime required",
                "error": {
                    "type": "RuntimeError",
                    "code": "external_runtime_required",
                    "message": external_required_error or "external_runtime_required",
                },
            }
        elif selected_path != "runtime":
            runtime_result = self._runtime.execute(
                skill_name,
                payload=merged_payload,
                context=normalized_context,
            )

        if selected_path == "runtime" and primary_runtime_result:
            selected_result = {
                "ok": True,
                "trace_id": primary_runtime_result.get("trace_id"),
                "duration_ms": primary_runtime_result.get("duration_ms"),
                "result": {
                    "summary": "Executed through MCP runtime.",
                    "source": "mcp_runtime",
                    "runtime_result": primary_runtime_result.get("result"),
                    "runtime_tool_id": mcp_tool_id,
                },
                "result_summary": "Executed through MCP runtime",
                "error": None,
            }
        elif selected_result is None:
            selected_result = runtime_result or {
                "ok": False,
                "trace_id": None,
                "duration_ms": None,
                "result": {"summary": "Skill runtime unavailable"},
                "result_summary": "Skill runtime unavailable",
                "error": {"message": "skill_runtime_unavailable"},
            }

        wrapped_result = self._wrap_result(
            skill_name=skill_name,
            result=selected_result.get("result"),
            summary=selected_result.get("result_summary"),
        )
        return {
            "ok": selected_result["ok"],
            "workflow_mode": "free_workflow",
            "selected_skill": skill_name,
            "trace_id": selected_result["trace_id"],
            "duration_ms": selected_result["duration_ms"],
            "result": selected_result["result"],
            "result_summary": selected_result["result_summary"],
            "error": selected_result["error"],
            "runtime": selected_result,
            "wrapped_result": wrapped_result,
            "migration_runtime": {
                "mode": policy["mode"],
                "shadow_mode": policy["shadow_mode"],
                "selected_path": selected_path,
                "fallback_reason": fallback_reason,
                "runtime_tool_id": mcp_tool_id,
                "strict_external_required": strict_external and skill_name in RUNTIME_ELIGIBLE_SKILLS,
                "policy_source": policy["policy_source"],
                "route_key": policy["route_key"],
                "canary_percent": policy["canary_percent"],
                "canary_hit": policy["canary_hit"],
                "rollback_applied": policy["rollback_applied"],
                "rollback_target_mode": policy["rollback_target_mode"],
                "primary_runtime_trace_id": (primary_runtime_result or {}).get("trace_id"),
                "shadow_runtime_trace_id": (shadow_runtime_result or {}).get("trace_id"),
                "shadow_status": (shadow_runtime_result or {}).get("ok"),
            },
        }

    def _strict_external_skills_enabled(self) -> bool:
        if _tool_sources_mode() == "external_only":
            return True
        return _env_as_bool("WORKBOT_STRICT_EXTERNAL_SKILLS", default=False)

    def run(
        self,
        *,
        text: str,
        required_capabilities: list[str] | None = None,
        skill_name: str | None = None,
        payload: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_skill, reason = self._select_skill(
            text=text,
            required_capabilities=required_capabilities or [],
            skill_name=skill_name,
            payload=payload or {},
        )
        result = self.execute_skill(
            selected_skill,
            text=text,
            payload=payload,
            context=context,
        )
        result["selection_reason"] = reason
        return result

    def _resolve_runtime_policy(
        self,
        *,
        skill_name: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        mcp_tool_id: str | None,
    ) -> dict[str, Any]:
        raw_policy = payload.get("runtime_policy")
        policy = raw_policy if isinstance(raw_policy, dict) else {}

        tool_mapping = self._mcp_runtime.build_tool_mapping(refresh=False) if mcp_tool_id else {}
        tool_entry = tool_mapping.get(mcp_tool_id or "") if isinstance(tool_mapping, dict) else None
        tool_entry = tool_entry if isinstance(tool_entry, dict) else {}

        traffic_policy = tool_entry.get("traffic_policy") if isinstance(tool_entry.get("traffic_policy"), dict) else {}
        rollback_policy = tool_entry.get("rollback") if isinstance(tool_entry.get("rollback"), dict) else {}

        default_mode = (
            "runtime_primary"
            if skill_name in RUNTIME_ELIGIBLE_SKILLS and bool(mcp_tool_id)
            else "builtin_primary"
        )
        configured_mode = _normalize_mode(traffic_policy.get("mode"), default=default_mode) if traffic_policy else default_mode
        configured_shadow = bool(traffic_policy.get("shadow_mode", skill_name in RUNTIME_ELIGIBLE_SKILLS))
        canary_percent = _coerce_percent(traffic_policy.get("canary_percent"), default=100 if configured_mode == "runtime_primary" else 0)
        route_key = _normalize_text(traffic_policy.get("route_key") or "global")
        canary_hit = False

        if configured_mode == "runtime_primary":
            if canary_percent >= 100:
                canary_hit = True
            elif canary_percent <= 0:
                configured_mode = "builtin_primary"
            else:
                seed = self._resolve_route_seed(
                    context=context,
                    payload=payload,
                    route_key=route_key,
                    skill_name=skill_name,
                    mcp_tool_id=mcp_tool_id or "",
                )
                canary_hit = _stable_bucket(seed) < canary_percent
                if not canary_hit:
                    configured_mode = "builtin_primary"

        mode_override = policy.get("mode") if "mode" in policy else None
        mode = _normalize_mode(mode_override, default=configured_mode) if mode_override is not None else configured_mode
        shadow_mode = bool(policy.get("shadow_mode", configured_shadow))

        rollback_applied = False
        rollback_target_mode = _normalize_mode(rollback_policy.get("target_mode"), default="builtin_primary")
        rollback_switch = bool(policy.get("force_builtin") or policy.get("rollback"))
        if rollback_switch or bool(rollback_policy.get("active") or rollback_policy.get("force_builtin")):
            mode = rollback_target_mode
            rollback_applied = True

        policy_source = "default"
        if traffic_policy:
            policy_source = "tool_traffic_policy"
        if mode_override is not None or "shadow_mode" in policy:
            policy_source = "request_override"
        if rollback_applied:
            policy_source = "rollback_switch"

        return {
            "mode": mode,
            "shadow_mode": shadow_mode,
            "policy_source": policy_source,
            "route_key": route_key,
            "canary_percent": canary_percent,
            "canary_hit": canary_hit,
            "rollback_applied": rollback_applied,
            "rollback_target_mode": rollback_target_mode if rollback_applied else None,
        }

    def _resolve_route_seed(
        self,
        *,
        context: dict[str, Any],
        payload: dict[str, Any],
        route_key: str,
        skill_name: str,
        mcp_tool_id: str,
    ) -> str:
        candidates: list[str] = []
        for key in (
            "route_seed",
            "user_id",
            "userId",
            "platform_user_id",
            "platformUserId",
            "chat_id",
            "chatId",
            "tenant_id",
            "tenantId",
            "task_id",
            "taskId",
        ):
            value = context.get(key)
            if value not in {None, ""}:
                candidates.append(f"{key}:{_normalize_text(value)}")
        payload_seed = payload.get("route_seed")
        if payload_seed not in {None, ""}:
            candidates.append(f"payload:{_normalize_text(payload_seed)}")
        if not candidates:
            candidates.append(f"skill:{skill_name}")
        candidates.append(f"tool:{mcp_tool_id}")
        candidates.append(f"route_key:{route_key}")
        return "|".join(candidates)

    def _resolve_runtime_tool_id(self, *, skill_name: str) -> str | None:
        if skill_name not in RUNTIME_ELIGIBLE_SKILLS:
            return None
        mapping = self._mcp_runtime.build_tool_mapping(refresh=False)
        if not mapping:
            return None
        allow_legacy_fallback_runtime = _tool_sources_mode() == "local_only"
        candidates = RUNTIME_TOOL_NAME_CANDIDATES.get(skill_name, ())
        best_match: tuple[int, str] | None = None
        for tool in mapping.values():
            if not isinstance(tool, dict):
                continue
            source = _normalize_lower(tool.get("source"))
            if source in {"internal", "internal-skills"}:
                continue
            if _is_legacy_runtime_source(source) and not allow_legacy_fallback_runtime:
                continue
            tool_type = _normalize_lower(tool.get("type"))
            if tool_type == "skill":
                continue
            tool_id = _normalize_text(tool.get("id"))
            tool_name = _normalize_lower(tool.get("name"))
            if not tool_id:
                continue
            normalized_tool_id = _normalize_lower(tool_id)
            match_score = -1
            for candidate in candidates:
                normalized_candidate = _normalize_lower(candidate)
                if not normalized_candidate:
                    continue
                if tool_name == normalized_candidate or normalized_tool_id.endswith(normalized_candidate):
                    match_score = max(match_score, 300 + len(normalized_candidate))
                    continue
                if normalized_candidate in tool_name or normalized_candidate in normalized_tool_id:
                    match_score = max(match_score, 100 + len(normalized_candidate))
            if match_score < 0:
                continue
            if best_match is None or match_score > best_match[0]:
                best_match = (match_score, tool_id)
        return best_match[1] if best_match is not None else None

    def _wrap_result(self, *, skill_name: str, result: Any, summary: Any) -> dict[str, Any]:
        result_dict = result if isinstance(result, dict) else {"value": result}
        summary_text = _normalize_text(summary or result_dict.get("summary") or "")
        if not summary_text:
            summary_text = f"{skill_name} executed"
        bullets = [
            f"skill: {skill_name}",
            f"source: {_normalize_text(result_dict.get('source') or 'internal')}",
        ]
        return {
            "title": _normalize_text(result_dict.get("title") or skill_name),
            "summary": summary_text,
            "content": _normalize_text(
                result_dict.get("content")
                or result_dict.get("speech")
                or result_dict.get("text")
                or summary_text
            ),
            "bullets": bullets,
            "references": result_dict.get("results") if isinstance(result_dict.get("results"), list) else [],
            "execution_trace": [
                {
                    "stage": "skill_runtime",
                    "title": skill_name,
                    "status": "completed",
                    "detail": summary_text,
                }
            ],
        }

    def _register_builtin_skills(self) -> None:
        abilities = []
        definitions = list(READ_ONLY_BUILTIN_SKILLS)
        if _tool_sources_mode() != "external_only":
            definitions.extend(TRANSITIONAL_FALLBACK_BUILTIN_SKILLS)
        for definition in definitions:
            ability = dict(definition)
            handler_name = str(ability.pop("handler_name"))
            ability["handler"] = getattr(self, handler_name)
            abilities.append(ability)
        self._registry.register_many(abilities, overwrite=True)

    def _select_skill(
        self,
        *,
        text: str,
        required_capabilities: list[str],
        skill_name: str | None,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        if skill_name:
            return skill_name, "explicit_skill_name"

        capability_candidates = self._registry.query_by_capabilities(
            required_capabilities,
            ability_type="skill",
            enabled=True,
        )
        if capability_candidates:
            return capability_candidates[0]["name"], "required_capabilities_match"

        has_pdf_payload = bool(payload.get("path") or payload.get("bytes_base64") or payload.get("bytes"))
        normalized_text = _normalize_lower(text)
        if not normalized_text and has_pdf_payload:
            return "pdf_read_skill", "pdf_payload_detected"

        if _contains_any(normalized_text, TASK_LIST_HINTS):
            return "task_list_skill", "task_list_hint"
        if _contains_any(normalized_text, TASK_STATUS_HINTS):
            return "task_status_skill", "task_status_hint"
        if _contains_any(normalized_text, WEATHER_HINTS):
            return "weather_skill", "weather_hint"
        if has_pdf_payload or _contains_any(normalized_text, PDF_HINTS):
            if _contains_any(normalized_text, SUMMARY_HINTS):
                return "pdf_summary_skill", "pdf_summary_hint"
            return "pdf_read_skill", "pdf_hint"
        if _contains_any(normalized_text, SEARCH_HINTS):
            return "web_search_skill", "search_hint"
        if _contains_any(normalized_text, SPEECH_HINTS):
            return "speech_writer_skill", "speech_hint"
        if _contains_any(normalized_text, WRITING_HINTS):
            return "general_writer_skill", "writing_hint"
        return "general_writer_skill", "default_fallback"

    def _task_status_skill(self, payload: dict[str, Any], context: dict[str, Any], ability: dict[str, Any]) -> dict[str, Any]:
        limit = int(payload.get("limit", 8) or 8)
        if limit <= 0:
            limit = 8
        task_response = task_service.list_tasks()
        items = [item for item in task_response.get("items", []) if str(item.get("status") or "").lower() in IN_PROGRESS_STATUSES]
        items = items[:limit]
        summary = f"Found {len(items)} in-progress task(s)."
        return {
            "summary": summary,
            "in_progress_count": len(items),
            "items": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "priority": item.get("priority"),
                    "agent": item.get("agent"),
                    "created_at": item.get("created_at"),
                    "current_stage": item.get("current_stage"),
                }
                for item in items
            ],
            "source": "task_service.list_tasks",
            "ability": ability.get("name"),
            "context_keys": sorted(str(key) for key in context.keys()),
        }

    def _task_list_skill(self, payload: dict[str, Any], context: dict[str, Any], ability: dict[str, Any]) -> dict[str, Any]:
        limit = int(payload.get("limit", 10) or 10)
        if limit <= 0:
            limit = 10

        status_filter = _normalize_text(payload.get("status_filter"))
        search = _normalize_text(payload.get("search"))
        task_response = task_service.list_tasks(
            status_filter=status_filter or None,
            search=search or None,
        )
        items = task_response.get("items", [])[:limit]
        summary = f"Listed {len(items)} task(s)."
        return {
            "summary": summary,
            "total": task_response.get("total", len(items)),
            "items": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "priority": item.get("priority"),
                    "agent": item.get("agent"),
                    "created_at": item.get("created_at"),
                    "completed_at": item.get("completed_at"),
                }
                for item in items
            ],
            "source": "task_service.list_tasks",
            "ability": ability.get("name"),
            "context_keys": sorted(str(key) for key in context.keys()),
        }

free_workflow_service = FreeWorkflowService()
