from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from app.modules.dispatch.skill_runtime.execution_policy import TrafficPolicy
from app.modules.dispatch.skill_runtime.runtime_router import RuntimeRouter
from app.platform.contracts.execution_protocol import ExecutionAttempt, ExecutionRequest, ExecutionResult


Executor = Callable[[ExecutionRequest], dict[str, Any]]


def _failed_result_message(result: dict[str, Any] | None) -> str | None:
    if not isinstance(result, dict):
        return None
    if bool(result.get("ok", True)):
        return None

    error = result.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or error.get("code") or "").strip()
        if message:
            return message
    message = str(error or result.get("result_summary") or "execution_failed").strip()
    return message or "execution_failed"


@dataclass(slots=True)
class SkillExecutionOutcome:
    selected_path: str
    execution_result: ExecutionResult | None
    runtime_result: dict[str, Any] | None
    builtin_result: dict[str, Any] | None
    shadow_result: dict[str, Any] | None
    fallback_reason: str | None = None


class SkillExecutionGateway:
    """Unify skill runtime/builtin dispatch under execution_gateway."""

    def __init__(self, *, router: RuntimeRouter | None = None) -> None:
        self._router = router or RuntimeRouter()

    def execute(
        self,
        *,
        request: ExecutionRequest,
        mode: str,
        builtin_executor: Executor,
        runtime_executor: Executor | None = None,
        shadow_mode: bool = False,
        shadow_executor: Executor | None = None,
        strict_runtime_required: bool = False,
        seed: str | None = None,
    ) -> SkillExecutionOutcome:
        shadow_result = shadow_executor(request) if shadow_mode and shadow_executor is not None else None
        normalized_mode = str(mode or "").strip().lower()

        if normalized_mode != "runtime_primary":
            single = self._invoke_single("builtin", request, builtin_executor)
            return SkillExecutionOutcome(
                selected_path="builtin",
                execution_result=single["execution_result"],
                runtime_result=None,
                builtin_result=single["raw_result"],
                shadow_result=shadow_result,
            )

        if runtime_executor is None:
            if strict_runtime_required:
                return SkillExecutionOutcome(
                    selected_path="external_runtime_required",
                    execution_result=None,
                    runtime_result=None,
                    builtin_result=None,
                    shadow_result=shadow_result,
                    fallback_reason="runtime_tool_not_found",
                )
            single = self._invoke_single("builtin", request, builtin_executor)
            return SkillExecutionOutcome(
                selected_path="builtin",
                execution_result=single["execution_result"],
                runtime_result=None,
                builtin_result=single["raw_result"],
                shadow_result=shadow_result,
            )

        if strict_runtime_required:
            single = self._invoke_single("runtime", request, runtime_executor)
            return SkillExecutionOutcome(
                selected_path="runtime" if single["ok"] else "external_runtime_required",
                execution_result=single["execution_result"],
                runtime_result=single["raw_result"],
                builtin_result=None,
                shadow_result=shadow_result,
                fallback_reason=None if single["ok"] else single["attempt"].error,
            )

        captured: dict[str, dict[str, Any] | None] = {"runtime": None, "builtin": None}

        def runtime_dispatch(active_request: ExecutionRequest) -> dict[str, Any]:
            raw_result = runtime_executor(active_request)
            captured["runtime"] = raw_result
            error_message = _failed_result_message(raw_result)
            if error_message is not None:
                raise RuntimeError(error_message)
            return raw_result

        def builtin_dispatch(active_request: ExecutionRequest) -> dict[str, Any]:
            raw_result = builtin_executor(active_request)
            captured["builtin"] = raw_result
            error_message = _failed_result_message(raw_result)
            if error_message is not None:
                raise RuntimeError(error_message)
            return raw_result

        execution_result = self._router.invoke(
            request,
            runtime_executor=runtime_dispatch,
            builtin_executor=builtin_dispatch,
            policy=TrafficPolicy(mode="runtime_primary", canary_percent=100),
            seed=seed,
        )
        runtime_attempt = execution_result.attempts[0] if execution_result.attempts else None
        fallback_reason = None
        if runtime_attempt is not None and runtime_attempt.path == "runtime" and not runtime_attempt.ok:
            fallback_reason = runtime_attempt.error

        return SkillExecutionOutcome(
            selected_path="runtime" if execution_result.path == "runtime" and execution_result.ok else "builtin_fallback",
            execution_result=execution_result,
            runtime_result=captured["runtime"],
            builtin_result=captured["builtin"],
            shadow_result=shadow_result,
            fallback_reason=fallback_reason,
        )

    def _invoke_single(
        self,
        path: str,
        request: ExecutionRequest,
        executor: Executor,
    ) -> dict[str, Any]:
        started = perf_counter()
        raw_result: dict[str, Any] | None = None
        try:
            raw_result = executor(request)
            error_message = _failed_result_message(raw_result)
            if error_message is not None:
                attempt = ExecutionAttempt(
                    path=path,
                    ok=False,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    error=error_message,
                )
                return {
                    "ok": False,
                    "raw_result": raw_result,
                    "attempt": attempt,
                    "execution_result": ExecutionResult(
                        ok=False,
                        path=path,
                        result=None,
                        error={"type": "execution_failed", "message": error_message},
                        attempts=[attempt],
                    ),
                }
        except Exception as exc:
            attempt = ExecutionAttempt(
                path=path,
                ok=False,
                duration_ms=round((perf_counter() - started) * 1000, 3),
                error=str(exc),
            )
            return {
                "ok": False,
                "raw_result": raw_result,
                "attempt": attempt,
                "execution_result": ExecutionResult(
                    ok=False,
                    path=path,
                    result=None,
                    error={"type": "execution_failed", "message": str(exc)},
                    attempts=[attempt],
                ),
            }

        attempt = ExecutionAttempt(
            path=path,
            ok=True,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        return {
            "ok": True,
            "raw_result": raw_result,
            "attempt": attempt,
            "execution_result": ExecutionResult(
                ok=True,
                path=path,
                result=raw_result,
                error=None,
                attempts=[attempt],
            ),
        }


skill_execution_gateway = SkillExecutionGateway()
