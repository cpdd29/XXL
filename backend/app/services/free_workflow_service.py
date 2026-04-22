from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import re
from typing import Any
from urllib.parse import quote_plus
from urllib.request import urlopen

from app.execution_gateway import ExecutionRequest, SkillExecutionGateway
from app.execution_gateway.skill_execution_gateway import skill_execution_gateway
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
TASK_BOARD_HINTS = {"任务看板", "任务面板", "task board", "kanban"}
SEARCH_HINTS = {"搜索", "检索", "查一下", "查找", "search", "lookup", "find", "web"}
PDF_HINTS = {"pdf", "文档", "文件", "附件"}
DOCX_HINTS = {"word", "docx", "doc", "转word", "转成word", "转为word", "转换word", "转换成word", "转成docx", "转换成docx"}
SUMMARY_HINTS = {"总结", "摘要", "要点", "summarize", "summary", "highlights"}
SPEECH_HINTS = {"演讲", "发言稿", "演讲稿", "speech", "keynote"}
WRITING_HINTS = {"写", "生成", "草稿", "文案", "稿子", "write", "draft", "copy"}
CURRENT_TASK_HINTS = {"当前任务", "这个任务", "this task", "current task"}
SCHEDULE_HINTS = {
    "定时",
    "定期",
    "计划执行",
    "schedule",
    "scheduled",
    "cron",
    "提醒",
    "remind",
    "稍后",
    "later",
    "每周",
    "每月",
    "每天",
    "每晚",
    "每早",
}
SCHEDULE_TIME_HINTS = {
    "上午",
    "下午",
    "晚上",
    "am",
    "pm",
    "点",
    "分",
    ":",
    "明天",
    "后天",
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
    "周末",
}
UPGRADE_HINTS = {
    "升级",
    "专业流程",
    "审批",
    "approve",
    "approval",
    "写入",
    "更新",
    "同步",
    "提交",
    "创建",
    "删除",
    "发送",
    "publish",
    "batch",
    "批量",
    "自动执行",
    "执行这个流程",
}
TEXT_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".xml",
    ".sql",
    ".sh",
}
OFFICE_FILE_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
IMAGE_FILE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
ARCHIVE_FILE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}
WEATHER_LABELS = {
    "sunny": "晴",
    "cloudy": "多云",
    "rainy": "下雨",
    "windy": "有风",
}
RUNTIME_ELIGIBLE_SKILLS = {
    "web_search_skill",
    "pdf_read_skill",
    "pdf_summary_skill",
    "pdf_to_docx_skill",
    "weather_skill",
    "speech_writer_skill",
    "general_writer_skill",
}
RUNTIME_TOOL_NAME_CANDIDATES: dict[str, tuple[str, ...]] = {
    "web_search_skill": ("web_search", "search", "web-search"),
    "pdf_read_skill": ("pdf_read", "pdf-read", "pdf_reader"),
    "pdf_summary_skill": ("pdf_summary", "pdf-summary"),
    "pdf_to_docx_skill": ("pdf_to_docx", "to_docx", "docx"),
    "weather_skill": ("weather", "get_weather", "weather_lookup"),
    "speech_writer_skill": ("speech_writer", "speech", "writer_speech"),
    "general_writer_skill": ("general_writer", "writer", "copywriter", "text_writer"),
}
PROJECT_LIGHT_OPS_SKILL_ID = "skill_search_light_execution"
PROJECT_LIGHT_OPS_SKILL_NAME = "search_light_execution_skill"
PROJECT_LIGHT_OPS_CAPABILITIES = {
    "web_search",
    "live_information_lookup",
    "information_retrieval",
    "weather_lookup",
    "task_status_lookup",
    "task_listing",
    "pdf_processing",
    "document_conversion",
    "schedule_intent_detection",
    "workflow_upgrade_assessment",
}
PROJECT_LIGHT_TRIGGER_CAPABILITIES = {
    "web_search",
    "live_information_lookup",
    "information_retrieval",
    "weather_lookup",
    "task_status_lookup",
    "task_listing",
    "pdf_processing",
    "document_conversion",
}
SCHEDULE_TIME_PATTERN = re.compile(
    r"(每[天周月晚早]|周[一二三四五六日末]|明天|后天|cron|schedule|提醒|定时).{0,18}(\d{1,2}[:点]\d{0,2}|上午|下午|晚上|am|pm)",
    re.IGNORECASE,
)
TASK_ID_PATTERN = re.compile(r"\b(task[-_a-zA-Z0-9]+)\b", re.IGNORECASE)
# Builtin skills are kept on a strict allowlist:
# - read-only retainers stay in brain for lightweight task/status views
# - transitional fallbacks remain only as external runtime degradation paths
READ_ONLY_BUILTIN_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "id": PROJECT_LIGHT_OPS_SKILL_ID,
        "name": PROJECT_LIGHT_OPS_SKILL_NAME,
        "type": "skill",
        "source": "internal",
        "description": "Project-tailored search/light-execution router for front-half light closed-loop flows.",
        "tags": ["project", "search-light-execution", "free-workflow", "readonly-retained", "search-agent"],
        "capabilities": sorted(PROJECT_LIGHT_OPS_CAPABILITIES),
        "timeout_seconds": 6.0,
        "handler_name": "_project_light_ops",
    },
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


def _format_decimal(value: Any, *, suffix: str = "") -> str | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric.is_integer():
        text = str(int(numeric))
    else:
        text = f"{numeric:.1f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _normalize_weather_label(value: Any) -> str:
    raw = _normalize_text(value)
    if not raw:
        return ""
    return WEATHER_LABELS.get(raw.lower(), raw)


def _forecast_day_label(offset: Any) -> str:
    try:
        numeric = int(offset)
    except (TypeError, ValueError):
        return ""
    if numeric == 0:
        return "今天"
    if numeric == 1:
        return "明天"
    if numeric == 2:
        return "后天"
    return f"{numeric}天后"


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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    if value in {None, ""}:
        return []
    normalized = _normalize_text(value)
    return [normalized] if normalized else []


class FreeWorkflowService:
    def __init__(
        self,
        *,
        registry: SkillRegistryService | None = None,
        runtime: SkillRuntimeService | None = None,
        mcp_runtime: MCPRuntimeService | None = None,
        execution_gateway: SkillExecutionGateway | None = None,
    ) -> None:
        self._registry = registry or skill_registry_service
        self._runtime = runtime or (
            skill_runtime_service if self._registry is skill_registry_service else SkillRuntimeService(registry=self._registry)
        )
        self._mcp_runtime = mcp_runtime or mcp_runtime_service
        self._execution_gateway = execution_gateway or skill_execution_gateway
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

        selected_result: dict[str, Any] | None = None
        external_required_error: str | None = None

        gateway_request = ExecutionRequest(
            tool_id=mcp_tool_id or skill_name,
            payload=merged_payload,
            trace_context={
                "workflow_mode": "free_workflow",
                "selected_skill": skill_name,
            },
        )
        gateway_outcome = self._execution_gateway.execute(
            request=gateway_request,
            mode=str(policy.get("mode") or "builtin_primary"),
            runtime_executor=(
                (
                    lambda request: self._mcp_runtime.invoke_tool(
                        tool_id=mcp_tool_id,
                        payload=request.payload,
                        trace_context={
                            **request.trace_context,
                            "execution_mode": "runtime_primary",
                        },
                    )
                )
                if mcp_tool_id
                else None
            ),
            builtin_executor=lambda request: self._runtime.execute(
                skill_name,
                payload=request.payload,
                context=normalized_context,
            ),
            shadow_mode=bool(policy.get("shadow_mode")),
            shadow_executor=(
                (
                    lambda request: self._mcp_runtime.invoke_shadow_tool(
                        tool_id=mcp_tool_id,
                        payload=request.payload,
                        trace_context={
                            **request.trace_context,
                            "execution_mode": "shadow",
                        },
                    )
                )
                if mcp_tool_id
                else None
            ),
            strict_runtime_required=strict_external and skill_name in RUNTIME_ELIGIBLE_SKILLS,
        )
        selected_path = gateway_outcome.selected_path
        fallback_reason = gateway_outcome.fallback_reason
        primary_runtime_result = gateway_outcome.runtime_result
        shadow_runtime_result = gateway_outcome.shadow_result
        builtin_result = gateway_outcome.builtin_result

        if selected_path == "external_runtime_required":
            external_required_error = (
                f"external_runtime_required: runtime tool not found for {skill_name}"
                if fallback_reason == "runtime_tool_not_found"
                else f"external_runtime_required: runtime invoke failed for {skill_name} ({fallback_reason or 'unknown_error'})"
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
            runtime_payload = self._runtime_result_payload(
                skill_name=skill_name,
                runtime_result=primary_runtime_result.get("result"),
                runtime_tool_id=mcp_tool_id,
            )
            selected_result = {
                "ok": True,
                "trace_id": primary_runtime_result.get("trace_id"),
                "duration_ms": primary_runtime_result.get("duration_ms"),
                "result": runtime_payload,
                "result_summary": _normalize_text(
                    runtime_payload.get("summary") or "Executed through MCP runtime"
                ),
                "error": None,
            }
        elif selected_result is None:
            selected_result = builtin_result or {
                "ok": False,
                "trace_id": None,
                "duration_ms": None,
                "result": {"summary": "Skill runtime unavailable"},
                "result_summary": "Skill runtime unavailable",
                "error": {"message": "skill_runtime_unavailable"},
            }

        structured_error = self._structured_result_error(selected_result.get("result"))
        if structured_error is not None:
            selected_result = {
                **selected_result,
                "ok": False,
                "result_summary": _normalize_text(
                    selected_result.get("result_summary")
                    or structured_error.get("message")
                    or selected_result.get("result", {}).get("summary")
                    or "Free workflow upgrade required"
                ),
                "error": structured_error,
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
        merged_payload = dict(payload or {})
        if required_capabilities and "required_capabilities" not in merged_payload:
            merged_payload["required_capabilities"] = list(required_capabilities)
        selected_skill, reason = self._select_skill(
            text=text,
            required_capabilities=required_capabilities or [],
            skill_name=skill_name,
            payload=merged_payload,
        )
        result = self.execute_skill(
            selected_skill,
            text=text,
            payload=merged_payload,
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
        result_bullets = [
            str(item).strip()
            for item in result_dict.get("bullets") or []
            if str(item).strip()
        ]
        bullets = [
            *result_bullets,
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
            "references": (
                result_dict.get("references")
                if isinstance(result_dict.get("references"), list)
                else result_dict.get("results")
                if isinstance(result_dict.get("results"), list)
                else []
            ),
            "execution_trace": [
                {
                    "stage": "skill_runtime",
                    "title": skill_name,
                    "status": "completed",
                    "detail": summary_text,
                }
            ],
        }

    def _runtime_result_payload(
        self,
        *,
        skill_name: str,
        runtime_result: dict[str, Any] | None,
        runtime_tool_id: str | None,
    ) -> dict[str, Any]:
        runtime_payload = runtime_result if isinstance(runtime_result, dict) else {}
        bridge_output = runtime_payload.get("output")
        if not isinstance(bridge_output, dict):
            bridge_output = {}
        result_value = bridge_output.get("result")
        structured_result = result_value if isinstance(result_value, dict) else {}

        if skill_name == "weather_skill" and structured_result:
            weather_payload = self._weather_runtime_payload(
                structured_result=structured_result,
                runtime_payload=runtime_payload,
                runtime_tool_id=runtime_tool_id,
            )
            if weather_payload is not None:
                return weather_payload

        summary_text = _normalize_text(
            structured_result.get("summary")
            or bridge_output.get("summary")
            or runtime_payload.get("summary")
            or ""
        )
        content_text = _normalize_text(
            structured_result.get("content")
            or structured_result.get("text")
            or structured_result.get("speech")
            or structured_result.get("message")
            or summary_text
        )
        if not content_text and result_value is not None and not isinstance(result_value, dict):
            content_text = _normalize_text(result_value)
        if not content_text and structured_result:
            try:
                content_text = json.dumps(structured_result, ensure_ascii=False)
            except TypeError:
                content_text = _normalize_text(structured_result)
        if not summary_text:
            summary_text = content_text or "Executed through MCP runtime."

        bullets_value = structured_result.get("bullets")
        bullets = (
            [str(item).strip() for item in bullets_value if str(item).strip()]
            if isinstance(bullets_value, list)
            else []
        )
        references_value = structured_result.get("references")
        references = (
            [item for item in references_value if isinstance(item, dict)]
            if isinstance(references_value, list)
            else []
        )
        title = _normalize_text(
            structured_result.get("title")
            or bridge_output.get("tool")
            or skill_name
        )
        return {
            "title": title or skill_name,
            "summary": summary_text,
            "content": content_text or summary_text,
            "bullets": bullets,
            "references": references,
            "source": "mcp_runtime",
            "runtime_result": runtime_payload,
            "runtime_tool_id": runtime_tool_id,
            "structured_data": structured_result or result_value,
        }

    def _weather_runtime_payload(
        self,
        *,
        structured_result: dict[str, Any],
        runtime_payload: dict[str, Any],
        runtime_tool_id: str | None,
    ) -> dict[str, Any] | None:
        location = _normalize_text(
            structured_result.get("location")
            or structured_result.get("city")
            or structured_result.get("query")
            or ""
        )
        weather_label = _normalize_weather_label(
            structured_result.get("weather_description") or structured_result.get("weather")
        )
        temperature = _format_decimal(structured_result.get("temperature_c"), suffix="°C")
        wind_speed = _format_decimal(structured_result.get("wind_speed_kmh"), suffix=" km/h")

        forecast_lines: list[str] = []
        forecast_entries = structured_result.get("forecast")
        if isinstance(forecast_entries, list):
            for entry in forecast_entries[:3]:
                if not isinstance(entry, dict):
                    continue
                day_label = _forecast_day_label(entry.get("day_offset"))
                day_weather = _normalize_weather_label(entry.get("weather"))
                day_temperature = _format_decimal(entry.get("temperature_c"), suffix="°C")
                detail_parts = [piece for piece in (day_weather, day_temperature) if piece]
                if not detail_parts:
                    continue
                detail = "，".join(detail_parts)
                forecast_lines.append(f"{day_label}：{detail}" if day_label else detail)

        if not any((location, weather_label, temperature, wind_speed, forecast_lines)):
            return None

        summary_parts = [piece for piece in (location, weather_label, temperature) if piece]
        summary = "，".join(summary_parts)
        if wind_speed:
            summary = f"{summary}，风速{wind_speed}" if summary else f"风速{wind_speed}"
        if not summary:
            summary = "天气查询已完成"

        content_lines: list[str] = []
        if location and weather_label:
            content_lines.append(f"{location}当前天气：{weather_label}")
        elif weather_label:
            content_lines.append(f"当前天气：{weather_label}")
        elif location:
            content_lines.append(f"查询城市：{location}")
        if temperature:
            content_lines.append(f"当前温度：{temperature}")
        if wind_speed:
            content_lines.append(f"风速：{wind_speed}")
        if forecast_lines:
            content_lines.append("未来天气：")
            content_lines.extend(f"- {line}" for line in forecast_lines)

        title = f"{location}天气" if location else "天气结果"
        return {
            "title": title,
            "summary": summary,
            "content": "\n".join(content_lines) or summary,
            "bullets": forecast_lines,
            "references": [],
            "source": "mcp_runtime",
            "runtime_result": runtime_payload,
            "runtime_tool_id": runtime_tool_id,
            "structured_data": structured_result,
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

    def _structured_result_error(self, result: Any) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        status = _normalize_lower(result.get("status"))
        if not status:
            if bool(result.get("upgrade_required")):
                status = "upgrade_required"
            elif bool(result.get("unsupported")):
                status = "unsupported"
        if status not in {"upgrade_required", "unsupported"}:
            return None

        reason = _normalize_text(
            result.get("reason")
            or result.get("message")
            or result.get("summary")
            or status
        )
        detail: dict[str, Any] = {}
        for key in (
            "operation",
            "assessment",
            "schedule_intent",
            "file_analysis",
            "delegate_skill",
            "delegate_execution",
            "delegate_error",
            "upgrade_target",
        ):
            value = result.get(key)
            if value is not None:
                detail[key] = value
        return {
            "type": "UpgradeRequiredError" if status == "upgrade_required" else "UnsupportedOperationError",
            "code": status,
            "message": reason or status,
            "detail": detail,
        }

    def _route_decision_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        route_decision = payload.get("route_decision") or payload.get("routeDecision")
        return route_decision if isinstance(route_decision, dict) else {}

    def _payload_required_capabilities(self, payload: dict[str, Any]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        route_decision = self._route_decision_payload(payload)
        for raw in (
            payload.get("required_capabilities"),
            payload.get("requiredCapabilities"),
            route_decision.get("required_capabilities"),
            route_decision.get("requiredCapabilities"),
        ):
            for item in _string_list(raw):
                lowered = _normalize_lower(item)
                if not lowered or lowered in seen:
                    continue
                seen.add(lowered)
                normalized.append(lowered)
        return normalized

    def _is_agent_context_payload(self, payload: dict[str, Any]) -> bool:
        if not payload:
            return False
        if self._route_decision_payload(payload):
            return True
        if isinstance(payload.get("manager_packet"), dict):
            return True
        return any(
            payload.get(key) not in {None, ""}
            for key in ("task_id", "request_text", "requires_permission")
        )

    def _should_select_project_light_ops(
        self,
        *,
        text: str,
        required_capabilities: list[str],
        payload: dict[str, Any],
    ) -> bool:
        if not self._is_agent_context_payload(payload):
            return False

        route_decision = self._route_decision_payload(payload)
        schedule_plan = route_decision.get("schedule_plan") or route_decision.get("schedulePlan")
        normalized_caps = {_normalize_lower(item) for item in required_capabilities}
        normalized_caps.update(self._payload_required_capabilities(payload))

        normalized_text = _normalize_lower(text or payload.get("request_text"))
        has_file_payload = bool(
            payload.get("file_path")
            or payload.get("filePath")
            or payload.get("path")
            or payload.get("bytes")
            or payload.get("bytes_base64")
            or payload.get("document_text")
            or payload.get("documentText")
        )
        return bool(
            normalized_caps & PROJECT_LIGHT_OPS_CAPABILITIES
            or (isinstance(schedule_plan, dict) and schedule_plan)
            or bool(
                payload.get("requires_permission")
                or route_decision.get("requires_permission")
                or route_decision.get("requiresPermission")
            )
            or has_file_payload
            or _contains_any(
                normalized_text,
                TASK_BOARD_HINTS
                | TASK_STATUS_HINTS
                | TASK_LIST_HINTS
                | WEATHER_HINTS
                | SEARCH_HINTS
                | SCHEDULE_HINTS,
            )
        )

    def _detect_schedule_intent(self, *, text: str, payload: dict[str, Any]) -> dict[str, Any]:
        route_decision = self._route_decision_payload(payload)
        schedule_plan = route_decision.get("schedule_plan") or route_decision.get("schedulePlan")
        if isinstance(schedule_plan, dict) and schedule_plan:
            return {
                "detected": True,
                "source": "route_decision.schedule_plan",
                "summary": _normalize_text(schedule_plan.get("summary") or schedule_plan.get("cron") or "schedule_plan"),
                "schedule_plan": schedule_plan,
            }

        normalized_text = _normalize_lower(text or payload.get("request_text"))
        if not normalized_text:
            return {"detected": False, "source": "none", "summary": "", "schedule_plan": None}

        matched_hints = [hint for hint in sorted(SCHEDULE_HINTS) if hint in normalized_text][:4]
        time_like = _contains_any(normalized_text, SCHEDULE_TIME_HINTS) or bool(SCHEDULE_TIME_PATTERN.search(text or ""))
        if matched_hints and time_like:
            return {
                "detected": True,
                "source": "text_hint",
                "summary": _normalize_text(text or payload.get("request_text")),
                "matched_hints": matched_hints,
                "schedule_plan": None,
            }
        return {"detected": False, "source": "none", "summary": "", "schedule_plan": None}

    def _task_id_from_request(self, *, text: str, payload: dict[str, Any]) -> str:
        for key in ("focus_task_id", "focusTaskId"):
            value = _normalize_text(payload.get(key))
            if value:
                return value

        normalized_text = _normalize_lower(text)
        if _contains_any(normalized_text, CURRENT_TASK_HINTS):
            return _normalize_text(payload.get("task_id"))

        matched = TASK_ID_PATTERN.search(text or "")
        if matched:
            return _normalize_text(matched.group(1))
        return ""

    def _simplify_task_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "agent": item.get("agent"),
            "created_at": item.get("created_at"),
            "completed_at": item.get("completed_at"),
            "current_stage": item.get("current_stage"),
        }

    def _build_task_board_result(
        self,
        *,
        payload: dict[str, Any],
        text: str,
        ability_name: str,
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        limit = int(payload.get("limit", 8) or 8)
        if limit <= 0:
            limit = 8
        task_id = self._task_id_from_request(text=text, payload=payload)
        focus_task: dict[str, Any] | None = None
        if task_id:
            try:
                focus_task = task_service.get_task(task_id)
            except Exception:
                focus_task = None

        status_filter = _normalize_text(payload.get("status_filter"))
        search = _normalize_text(payload.get("search"))
        task_response = task_service.list_tasks(
            status_filter=status_filter or None,
            search=search or None,
        )
        items = task_response.get("items", [])
        total = int(task_response.get("total", len(items)) or 0)
        status_counts = Counter(_normalize_lower(item.get("status") or "unknown") for item in items)
        running = sum(status_counts.get(status, 0) for status in IN_PROGRESS_STATUSES)
        completed = status_counts.get("completed", 0)
        pending = status_counts.get("pending", 0)
        recent_items = [self._simplify_task_item(item) for item in items[:limit]]

        summary = f"任务看板：共 {total} 个任务，进行中 {running} 个，待处理 {pending} 个，已完成 {completed} 个。"
        bullets = [
            f"进行中: {running}",
            f"待处理: {pending}",
            f"已完成: {completed}",
        ]
        content_parts = [summary]
        if focus_task is not None:
            focus_status = _normalize_text(focus_task.get("status") or "unknown")
            focus_title = _normalize_text(focus_task.get("title") or focus_task.get("id") or "当前任务")
            content_parts.append(f"当前任务：{focus_title}，状态 {focus_status}")
            bullets.append(f"当前任务: {focus_title} ({focus_status})")
        if recent_items:
            content_parts.append("最近任务：" + "；".join(
                f"{_normalize_text(item.get('title') or item.get('id'))} [{_normalize_text(item.get('status'))}]"
                for item in recent_items[:5]
            ))
        return {
            "title": "任务看板",
            "summary": summary,
            "content": " ".join(content_parts),
            "bullets": bullets,
            "references": [],
            "source": ability_name,
            "status": "completed",
            "operation": "task_board",
            "task_board": {
                "total": total,
                "running": running,
                "pending": pending,
                "completed": completed,
                "items": recent_items,
                "focus_task": self._simplify_task_item(focus_task) if isinstance(focus_task, dict) else None,
            },
            "assessment": assessment,
        }

    def _safe_file_preview(self, path: str) -> str:
        if not path or not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                return _normalize_text(handle.read(1200))
        except Exception:
            return ""

    def _analyze_file_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = _normalize_text(payload.get("file_path") or payload.get("filePath") or payload.get("path"))
        document_text = _normalize_text(payload.get("document_text") or payload.get("documentText"))
        raw_bytes = payload.get("bytes")
        bytes_base64 = _normalize_text(payload.get("bytes_base64"))

        file_name = os.path.basename(path) if path else ""
        extension = os.path.splitext(file_name)[1].lower()
        path_exists = bool(path and os.path.isfile(path))
        size_bytes = 0
        if path_exists:
            try:
                size_bytes = int(os.path.getsize(path))
            except OSError:
                size_bytes = 0
        elif isinstance(raw_bytes, (bytes, bytearray)):
            size_bytes = len(raw_bytes)
        elif document_text:
            size_bytes = len(document_text.encode("utf-8", errors="ignore"))

        is_pdf = (
            extension == ".pdf"
            or (isinstance(raw_bytes, (bytes, bytearray)) and bytes(raw_bytes[:4]) == b"%PDF")
            or bytes_base64.startswith("JVBERi0")
        )
        category = "unknown"
        if is_pdf:
            category = "pdf"
        elif extension in TEXT_FILE_EXTENSIONS or document_text:
            category = "text"
        elif extension in OFFICE_FILE_EXTENSIONS:
            category = "office"
        elif extension in IMAGE_FILE_EXTENSIONS:
            category = "image"
        elif extension in ARCHIVE_FILE_EXTENSIONS:
            category = "archive"

        preview = document_text[:280]
        if not preview and category == "text":
            preview = self._safe_file_preview(path)

        return {
            "path": path or None,
            "file_name": file_name or None,
            "extension": extension or None,
            "exists": path_exists,
            "size_bytes": size_bytes,
            "category": category,
            "is_pdf": is_pdf,
            "preview": _normalize_text(preview),
        }

    def _build_project_light_success(
        self,
        *,
        ability_name: str,
        title: str,
        summary: str,
        content: str,
        operation: str,
        bullets: list[str] | None = None,
        references: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "title": _normalize_text(title),
            "summary": _normalize_text(summary),
            "content": _normalize_text(content or summary),
            "bullets": [item for item in (bullets or []) if _normalize_text(item)],
            "references": [item for item in (references or []) if isinstance(item, dict)],
            "source": ability_name,
            "status": "completed",
            "operation": operation,
        }
        if isinstance(extra, dict):
            payload.update(extra)
        return payload

    def _build_project_light_error(
        self,
        *,
        ability_name: str,
        status: str,
        title: str,
        summary: str,
        operation: str,
        reason: str,
        bullets: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = "upgrade_required" if status == "upgrade_required" else "unsupported"
        payload = {
            "title": _normalize_text(title),
            "summary": _normalize_text(summary),
            "content": _normalize_text(summary),
            "bullets": [item for item in (bullets or []) if _normalize_text(item)],
            "references": [],
            "source": ability_name,
            "status": normalized_status,
            "operation": operation,
            "reason": _normalize_text(reason),
            "upgrade_required": normalized_status == "upgrade_required",
            "unsupported": normalized_status == "unsupported",
        }
        if normalized_status == "upgrade_required":
            payload["upgrade_target"] = "professional_workflow"
        if isinstance(extra, dict):
            payload.update(extra)
        return payload

    def _build_project_light_delegate_failure(
        self,
        *,
        ability_name: str,
        operation: str,
        delegate_skill: str,
        delegate_result: dict[str, Any],
        label: str,
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        error = delegate_result.get("error") if isinstance(delegate_result.get("error"), dict) else {}
        reason = _normalize_text(
            error.get("message")
            or error.get("code")
            or delegate_result.get("result_summary")
            or f"{label} execution failed"
        )
        summary = f"{label} 当前不能在 free_workflow 里可靠执行，建议升级到专业流程或补齐外部 runtime。"
        return self._build_project_light_error(
            ability_name=ability_name,
            status="upgrade_required",
            title=f"{label}需要升级",
            summary=summary,
            operation=operation,
            reason=reason,
            bullets=[
                f"delegate skill: {delegate_skill}",
                f"delegate path: {_normalize_text((delegate_result.get('migration_runtime') or {}).get('selected_path') or 'builtin')}",
                f"reason: {reason}",
            ],
            extra={
                "delegate_skill": delegate_skill,
                "delegate_error": error,
                "delegate_execution": delegate_result.get("migration_runtime"),
                "assessment": assessment,
            },
        )

    def _delegate_project_light_skill(
        self,
        *,
        skill_name: str,
        label: str,
        operation: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        ability_name: str,
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        delegate_result = self.execute_skill(
            skill_name,
            text=_normalize_text(payload.get("text") or payload.get("request_text")),
            payload=payload,
            context=context,
        )
        if not bool(delegate_result.get("ok")):
            return self._build_project_light_delegate_failure(
                ability_name=ability_name,
                operation=operation,
                delegate_skill=skill_name,
                delegate_result=delegate_result,
                label=label,
                assessment=assessment,
            )

        wrapped = delegate_result.get("wrapped_result") if isinstance(delegate_result.get("wrapped_result"), dict) else {}
        result_payload = delegate_result.get("result") if isinstance(delegate_result.get("result"), dict) else {}
        title = _normalize_text(wrapped.get("title") or result_payload.get("title") or label)
        summary = _normalize_text(delegate_result.get("result_summary") or result_payload.get("summary") or label)
        content = _normalize_text(
            wrapped.get("content")
            or result_payload.get("content")
            or summary
            or label
        )
        if skill_name == "pdf_to_docx_skill" and summary in {"", "Executed through MCP runtime."}:
            summary = "已调用 PDF 转 Word 轻执行运行时。"
        if skill_name == "pdf_to_docx_skill" and title in {"", "pdf_to_docx_skill"}:
            title = "PDF 转 Word"
        if skill_name == "pdf_to_docx_skill" and content in {"", "Executed through MCP runtime."}:
            content = "轻闭环已将当前 PDF 交给运行时执行 PDF 转 Word。"
        bullets = [
            *[
                str(item).strip()
                for item in (wrapped.get("bullets") or result_payload.get("bullets") or [])
                if str(item).strip()
            ],
            f"delegate skill: {skill_name}",
            f"delegate path: {_normalize_text((delegate_result.get('migration_runtime') or {}).get('selected_path') or 'builtin')}",
        ]
        references = wrapped.get("references") if isinstance(wrapped.get("references"), list) else []
        return self._build_project_light_success(
            ability_name=ability_name,
            title=title,
            summary=summary,
            content=content,
            operation=operation,
            bullets=bullets,
            references=references,
            extra={
                "delegate_skill": skill_name,
                "delegate_execution": delegate_result.get("migration_runtime"),
                "delegate_result": result_payload,
                "assessment": assessment,
            },
        )

    def _project_light_ops(self, payload: dict[str, Any], context: dict[str, Any], ability: dict[str, Any]) -> dict[str, Any]:
        ability_name = _normalize_text(ability.get("name") or PROJECT_LIGHT_OPS_SKILL_NAME)
        text = _normalize_text(payload.get("text") or payload.get("request_text"))
        normalized_text = _normalize_lower(text)
        required_capabilities = set(self._payload_required_capabilities(payload))
        schedule_intent = self._detect_schedule_intent(text=text, payload=payload)
        route_decision = self._route_decision_payload(payload)
        requires_permission = bool(
            payload.get("requires_permission")
            or route_decision.get("requires_permission")
            or route_decision.get("requiresPermission")
        )
        execution_scope = _normalize_lower(
            route_decision.get("execution_scope")
            or route_decision.get("executionScope")
            or ""
        )

        assessment_reasons: list[str] = []
        if requires_permission:
            assessment_reasons.append("请求带有权限/审批保护标记")
        if execution_scope in {"write_protected", "write"}:
            assessment_reasons.append("请求超出只读轻执行范围")
        if schedule_intent.get("detected"):
            assessment_reasons.append("已识别到定时/计划执行意图")
        if _contains_any(normalized_text, UPGRADE_HINTS):
            assessment_reasons.append("文本命中了写操作、审批或批处理提示")
        assessment = {
            "should_upgrade": bool(assessment_reasons),
            "reasons": assessment_reasons,
            "suggested_workflow": "professional_workflow" if assessment_reasons else None,
        }

        is_task_request = bool(required_capabilities & {"task_status_lookup", "task_listing"}) or _contains_any(
            normalized_text,
            TASK_BOARD_HINTS | TASK_STATUS_HINTS | TASK_LIST_HINTS,
        )
        is_weather_request = "weather_lookup" in required_capabilities or _contains_any(normalized_text, WEATHER_HINTS)
        has_file_payload = bool(
            payload.get("file_path")
            or payload.get("filePath")
            or payload.get("path")
            or payload.get("bytes")
            or payload.get("bytes_base64")
            or payload.get("document_text")
            or payload.get("documentText")
        )
        is_search_request = bool(
            required_capabilities & {"web_search", "live_information_lookup", "information_retrieval"}
        ) or _contains_any(normalized_text, SEARCH_HINTS)

        if schedule_intent.get("detected"):
            return self._build_project_light_error(
                ability_name=ability_name,
                status="upgrade_required",
                title="识别到定时执行意图",
                summary="当前项目定制轻闭环只负责识别定时意图，真正的调度与跟进需要升级到专业流程。",
                operation="schedule_intent",
                reason="schedule_intent_detected",
                bullets=[
                    f"source: {_normalize_text(schedule_intent.get('source'))}",
                    f"summary: {_normalize_text(schedule_intent.get('summary'))}",
                ],
                extra={"schedule_intent": schedule_intent, "assessment": assessment},
            )

        if is_task_request:
            return self._build_task_board_result(
                payload=payload,
                text=text,
                ability_name=ability_name,
                assessment=assessment,
            )

        if requires_permission or execution_scope in {"write_protected", "write"}:
            return self._build_project_light_error(
                ability_name=ability_name,
                status="upgrade_required",
                title="需要升级到专业流程",
                summary="当前请求超出了搜索/轻执行 Agent 的只读轻闭环范围，需交给专业流程处理。",
                operation="upgrade_assessment",
                reason="permission_or_write_scope_detected",
                bullets=assessment_reasons,
                extra={"assessment": assessment},
            )

        if is_weather_request:
            return self._delegate_project_light_skill(
                skill_name="weather_skill",
                label="天气查询",
                operation="weather_lookup",
                payload=payload,
                context=context,
                ability_name=ability_name,
                assessment=assessment,
            )

        if has_file_payload:
            file_analysis = self._analyze_file_request(payload)
            if file_analysis["category"] == "pdf":
                wants_docx = _contains_any(normalized_text, DOCX_HINTS)
                delegate_skill = (
                    "pdf_to_docx_skill"
                    if wants_docx
                    else "pdf_summary_skill"
                    if _contains_any(normalized_text, SUMMARY_HINTS)
                    else "pdf_read_skill"
                )
                label = "PDF 转 Word" if delegate_skill == "pdf_to_docx_skill" else "PDF 处理"
                return self._delegate_project_light_skill(
                    skill_name=delegate_skill,
                    label=label,
                    operation="file_processing",
                    payload=payload,
                    context=context,
                    ability_name=ability_name,
                    assessment={**assessment, "file_analysis": file_analysis},
                )
            if file_analysis["category"] == "text":
                preview = _normalize_text(file_analysis.get("preview") or "未读取到预览内容")
                summary = (
                    f"已识别文本文件 {file_analysis.get('file_name') or '(inline text)'}，"
                    f"大小约 {file_analysis.get('size_bytes') or 0} B。"
                )
                return self._build_project_light_success(
                    ability_name=ability_name,
                    title="文本文件识别",
                    summary=summary,
                    content=f"{summary} 预览：{preview or '无'}",
                    operation="file_processing",
                    bullets=[
                        f"category: {file_analysis.get('category')}",
                        f"extension: {_normalize_text(file_analysis.get('extension') or 'n/a')}",
                    ],
                    extra={"file_analysis": file_analysis, "assessment": assessment},
                )
            if file_analysis.get("path") and not file_analysis.get("exists"):
                return self._build_project_light_error(
                    ability_name=ability_name,
                    status="unsupported",
                    title="文件不可用",
                    summary="文件路径不可访问，当前轻闭环无法继续处理。",
                    operation="file_processing",
                    reason="file_not_found",
                    bullets=[f"path: {file_analysis.get('path')}"],
                    extra={"file_analysis": file_analysis, "assessment": assessment},
                )
            return self._build_project_light_error(
                ability_name=ability_name,
                status="upgrade_required",
                title="文件处理需要升级",
                summary="该文件类型当前只能做轻量识别，若需要深入解析/转换，请升级到专业流程。",
                operation="file_processing",
                reason=f"unsupported_file_category:{file_analysis.get('category')}",
                bullets=[
                    f"category: {file_analysis.get('category')}",
                    f"extension: {_normalize_text(file_analysis.get('extension') or 'n/a')}",
                ],
                extra={"file_analysis": file_analysis, "assessment": assessment},
            )

        if is_search_request:
            return self._delegate_project_light_skill(
                skill_name="web_search_skill",
                label="搜索查询",
                operation="search_lookup",
                payload=payload,
                context=context,
                ability_name=ability_name,
                assessment=assessment,
            )

        if assessment["should_upgrade"]:
            return self._build_project_light_error(
                ability_name=ability_name,
                status="upgrade_required",
                title="建议升级到专业流程",
                summary="已识别到超出轻闭环范围的诉求，建议走专业流程以保证权限、安全与执行闭环。",
                operation="upgrade_assessment",
                reason="upgrade_assessment_triggered",
                bullets=assessment_reasons,
                extra={"assessment": assessment},
            )

        return self._build_project_light_error(
            ability_name=ability_name,
            status="unsupported",
            title="当前轻闭环未识别到可执行动作",
            summary="该请求没有命中已支持的搜索/任务看板/天气/文件识别/定时识别能力。",
            operation="unsupported",
            reason="no_supported_light_operation_detected",
            extra={"assessment": assessment},
        )

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

        if self._should_select_project_light_ops(
            text=text,
            required_capabilities=required_capabilities,
            payload=payload,
        ):
            return PROJECT_LIGHT_OPS_SKILL_NAME, "search_light_execution_agent_context"

        has_pdf_payload = bool(
            payload.get("path")
            or payload.get("file_path")
            or payload.get("filePath")
            or payload.get("bytes_base64")
            or payload.get("bytes")
        )
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
            if _contains_any(normalized_text, DOCX_HINTS):
                return "pdf_to_docx_skill", "pdf_to_docx_hint"
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
