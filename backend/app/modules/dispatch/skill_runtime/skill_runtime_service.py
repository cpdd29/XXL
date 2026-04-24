from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from inspect import signature
import time
from typing import Any, Callable
from uuid import uuid4

from app.modules.agent_config.registries.skill_registry_service import SkillRegistryService, skill_registry_service


class SkillRuntimeError(RuntimeError):
    def __init__(self, message: str, *, code: str = "runtime_error", detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = str(code).strip() or "runtime_error"
        self.detail = detail or {}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_summary(value: object, *, max_length: int = 180) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def _summarize_result(result: Any) -> str:
    if result is None:
        return "empty result"
    if isinstance(result, dict):
        if isinstance(result.get("summary"), str) and result["summary"].strip():
            return _normalize_summary(result["summary"])
        if isinstance(result.get("message"), str) and result["message"].strip():
            return _normalize_summary(result["message"])
        keys = sorted(str(key) for key in result.keys())
        return f"dict result with keys: {', '.join(keys[:8])}"
    if isinstance(result, list):
        return f"list result with {len(result)} item(s)"
    if isinstance(result, str):
        return _normalize_summary(result)
    return _normalize_summary(repr(result))


def _invoke_handler(
    handler: Callable[..., Any],
    payload: dict[str, Any],
    context: dict[str, Any],
    ability: dict[str, Any],
) -> Any:
    try:
        params = signature(handler).parameters
    except (TypeError, ValueError):
        return handler(payload, context, ability)

    if "payload" in params:
        kwargs: dict[str, Any] = {"payload": payload}
        if "context" in params:
            kwargs["context"] = context
        if "ability" in params:
            kwargs["ability"] = ability
        return handler(**kwargs)

    positional_count = len(params)
    if positional_count >= 3:
        return handler(payload, context, ability)
    if positional_count == 2:
        return handler(payload, context)
    if positional_count == 1:
        return handler(payload)
    return handler()


class SkillRuntimeService:
    def __init__(self, *, registry: SkillRegistryService | None = None, max_workers: int = 4) -> None:
        self._registry = registry or skill_registry_service
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._traces: list[dict[str, Any]] = []

    def execute(
        self,
        ability_name: str,
        *,
        payload: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now_iso()
        started = time.perf_counter()
        trace_id = f"trace_{uuid4().hex}"
        normalized_payload = payload or {}
        normalized_context = context or {}

        ability = self._registry.get_ability(ability_name)
        if ability is None:
            return self._record_failure(
                trace_id=trace_id,
                started_at=started_at,
                started=started,
                ability_name=ability_name,
                ability_type=None,
                source=None,
                timeout_seconds=timeout_seconds,
                error=SkillRuntimeError(
                    f"Ability '{ability_name}' not found",
                    code="ability_not_found",
                ),
            )

        if not ability.get("enabled", True):
            return self._record_failure(
                trace_id=trace_id,
                started_at=started_at,
                started=started,
                ability_name=ability["name"],
                ability_type=str(ability.get("type") or ""),
                source=str(ability.get("source") or ""),
                timeout_seconds=timeout_seconds,
                error=SkillRuntimeError(
                    f"Ability '{ability['name']}' is disabled",
                    code="ability_disabled",
                ),
            )

        handler = ability.get("handler")
        if not callable(handler):
            if str(ability.get("type") or "") == "mcp":
                handler = self._mcp_bridge_handler
            else:
                return self._record_failure(
                    trace_id=trace_id,
                    started_at=started_at,
                    started=started,
                    ability_name=ability["name"],
                    ability_type=str(ability.get("type") or ""),
                    source=str(ability.get("source") or ""),
                    timeout_seconds=timeout_seconds,
                    error=SkillRuntimeError(
                        f"Ability '{ability['name']}' does not define a callable handler",
                        code="invalid_ability_handler",
                    ),
                )

        resolved_timeout = float(timeout_seconds or ability.get("timeout_seconds") or 8.0)
        if resolved_timeout <= 0:
            resolved_timeout = 8.0

        future = self._executor.submit(
            _invoke_handler,
            handler,
            normalized_payload,
            normalized_context,
            ability,
        )
        try:
            result = future.result(timeout=resolved_timeout)
        except FutureTimeoutError:
            future.cancel()
            return self._record_failure(
                trace_id=trace_id,
                started_at=started_at,
                started=started,
                ability_name=ability["name"],
                ability_type=str(ability.get("type") or ""),
                source=str(ability.get("source") or ""),
                timeout_seconds=resolved_timeout,
                error=SkillRuntimeError(
                    f"Ability '{ability['name']}' timed out",
                    code="runtime_timeout",
                    detail={"timeout_seconds": resolved_timeout},
                ),
            )
        except SkillRuntimeError as runtime_error:
            return self._record_failure(
                trace_id=trace_id,
                started_at=started_at,
                started=started,
                ability_name=ability["name"],
                ability_type=str(ability.get("type") or ""),
                source=str(ability.get("source") or ""),
                timeout_seconds=resolved_timeout,
                error=runtime_error,
            )
        except Exception as exc:
            return self._record_failure(
                trace_id=trace_id,
                started_at=started_at,
                started=started,
                ability_name=ability["name"],
                ability_type=str(ability.get("type") or ""),
                source=str(ability.get("source") or ""),
                timeout_seconds=resolved_timeout,
                error=SkillRuntimeError(
                    str(exc) or f"Ability '{ability['name']}' execution failed",
                    code="runtime_execution_error",
                    detail={"exception_type": exc.__class__.__name__},
                ),
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        result_summary = _summarize_result(result)
        trace = {
            "trace_id": trace_id,
            "status": "success",
            "started_at": started_at,
            "duration_ms": duration_ms,
            "ability_name": ability["name"],
            "ability_id": ability.get("id"),
            "ability_type": ability.get("type"),
            "source": ability.get("source"),
            "timeout_seconds": resolved_timeout,
            "result_summary": result_summary,
            "error": None,
        }
        self._append_trace(trace)
        return {
            "ok": True,
            "trace_id": trace_id,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "ability_name": ability["name"],
            "ability_id": ability.get("id"),
            "ability_type": ability.get("type"),
            "source": ability.get("source"),
            "result": result,
            "result_summary": result_summary,
            "error": None,
            "meta": {
                "tags": list(ability.get("tags") or []),
                "capabilities": list(ability.get("capabilities") or []),
                "timeout_seconds": resolved_timeout,
            },
        }

    def execute_skill(
        self,
        *,
        skill_id: str,
        payload: dict[str, Any],
        trace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime_result = self.execute(
            skill_id,
            payload=payload,
            context=trace_context or {},
        )
        if not runtime_result["ok"]:
            error = runtime_result["error"] or {}
            raise SkillRuntimeError(
                str(error.get("message") or "Skill runtime execution failed"),
                code=str(error.get("code") or "runtime_error"),
                detail=error.get("detail") if isinstance(error.get("detail"), dict) else {},
            )
        ability = self._registry.get_ability(skill_id) or {
            "id": skill_id,
            "name": skill_id,
            "type": "skill",
            "source": "internal",
        }
        return self._build_task_result_payload(ability, runtime_result)

    def execute_for_capabilities(
        self,
        *,
        capabilities: list[str],
        payload: dict[str, Any],
        trace_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ability = self._registry.resolve_skill_for_capabilities(capabilities)
        if ability is None:
            raise SkillRuntimeError(
                "No skill matched required capabilities",
                code="ability_not_found",
                detail={"required_capabilities": capabilities},
            )
        result = self.execute_skill(
            skill_id=str(ability["id"]),
            payload=payload,
            trace_context=trace_context,
        )
        return ability, result

    def list_recent_invocations(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.list_traces(limit=limit)

    def get_last_invocation(self, skill_id: str) -> dict[str, Any] | None:
        normalized = str(skill_id or "").strip()
        if not normalized:
            return None
        for item in reversed(self._traces):
            if str(item.get("ability_id") or "") == normalized or str(item.get("ability_name") or "") == normalized:
                return dict(item)
        return None

    def build_last_call_summary(self, skill_id: str) -> dict[str, Any] | None:
        invocation = self.get_last_invocation(skill_id)
        if invocation is None:
            return None
        return {
            "at": invocation.get("started_at"),
            "status": invocation.get("status"),
            "duration_ms": invocation.get("duration_ms"),
            "summary": invocation.get("result_summary"),
            "error": invocation.get("error"),
        }

    def list_traces(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        items = self._traces
        if normalized_status:
            items = [item for item in items if str(item.get("status") or "").strip().lower() == normalized_status]
        if limit <= 0:
            return []
        return [dict(item) for item in items[-limit:]][::-1]

    def clear_traces(self) -> None:
        self._traces.clear()

    def _append_trace(self, trace: dict[str, Any]) -> None:
        self._traces.append(trace)
        if len(self._traces) > 500:
            self._traces = self._traces[-500:]

    def _record_failure(
        self,
        *,
        trace_id: str,
        started_at: str,
        started: float,
        ability_name: str,
        ability_type: str | None,
        source: str | None,
        timeout_seconds: float | None,
        error: SkillRuntimeError,
    ) -> dict[str, Any]:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        error_payload = {
            "code": error.code,
            "message": str(error),
            "detail": error.detail,
        }
        trace = {
            "trace_id": trace_id,
            "status": "failed",
            "started_at": started_at,
            "duration_ms": duration_ms,
            "ability_name": ability_name,
            "ability_id": None,
            "ability_type": ability_type,
            "source": source,
            "timeout_seconds": timeout_seconds,
            "result_summary": None,
            "error": error_payload,
        }
        self._append_trace(trace)
        return {
            "ok": False,
            "trace_id": trace_id,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "ability_name": ability_name,
            "ability_id": None,
            "ability_type": ability_type,
            "source": source,
            "result": None,
            "result_summary": None,
            "error": error_payload,
            "meta": {
                "timeout_seconds": timeout_seconds,
            },
        }

    def _build_task_result_payload(self, ability: dict[str, Any], runtime_result: dict[str, Any]) -> dict[str, Any]:
        result = runtime_result.get("result")
        summary = str(runtime_result.get("result_summary") or "").strip()
        if isinstance(result, dict):
            title = str(result.get("title") or ability.get("name") or ability.get("id") or "free workflow result")
            content = str(result.get("content") or result.get("summary") or summary)
            bullets_value = result.get("bullets")
            bullets = [str(item) for item in bullets_value if str(item).strip()] if isinstance(bullets_value, list) else []
            references_value = result.get("references")
            references = [item for item in references_value if isinstance(item, dict)] if isinstance(references_value, list) else []
            structured_data = result
            kind = str(result.get("kind") or "help_note")
        else:
            title = str(ability.get("name") or ability.get("id") or "free workflow result")
            content = str(result or summary)
            bullets = []
            references = []
            structured_data = {"result": result}
            kind = "help_note"
        return {
            "kind": kind,
            "title": title,
            "summary": summary or "Skill execution completed",
            "content": content,
            "bullets": bullets,
            "references": references,
            "structured_data": structured_data,
            "execution_trace": [
                {
                    "stage": "skill_runtime",
                    "title": "Skill Runtime",
                    "status": "completed",
                    "detail": f"Ability '{ability.get('name') or ability.get('id')}' executed.",
                    "metadata": {
                        "trace_id": runtime_result.get("trace_id"),
                        "duration_ms": runtime_result.get("duration_ms"),
                        "ability_id": ability.get("id"),
                        "ability_name": ability.get("name"),
                    },
                }
            ],
        }

    def _mcp_bridge_handler(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
        ability: dict[str, Any],
    ) -> dict[str, Any]:
        from app.modules.agent_config.registries.mcp_runtime_service import mcp_runtime_service

        action = str(ability.get("id") or ability.get("name") or "").strip()
        bridge_result = mcp_runtime_service.execute_bridge(action, payload)
        return {
            "summary": str(bridge_result.get("summary") or ""),
            "kind": "help_note",
            "title": str(ability.get("name") or action),
            "content": str(bridge_result.get("summary") or ""),
            "bullets": [str(bridge_result.get("summary") or "")],
            "references": [],
            "structured_data": bridge_result.get("details") or {},
            "context_keys": sorted(str(key) for key in context.keys()),
        }


skill_runtime_service = SkillRuntimeService()
