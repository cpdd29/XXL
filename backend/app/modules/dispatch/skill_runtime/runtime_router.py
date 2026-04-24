from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from app.modules.dispatch.skill_runtime.execution_policy import (
    TrafficPolicy,
    resolve_effective_mode,
    should_use_runtime,
)
from app.platform.contracts.execution_protocol import ExecutionAttempt, ExecutionRequest, ExecutionResult


Executor = Callable[[ExecutionRequest], dict[str, Any]]


class RuntimeRouter:
    """Route execution between runtime and builtin paths with fallback support."""

    def invoke(
        self,
        request: ExecutionRequest,
        *,
        runtime_executor: Executor,
        builtin_executor: Executor,
        policy: TrafficPolicy | None = None,
        seed: str | None = None,
    ) -> ExecutionResult:
        active_policy = policy or TrafficPolicy()
        route_seed = seed or f"{request.tool_id}:{active_policy.route_key}"
        mode = resolve_effective_mode(active_policy)
        prefer_runtime = should_use_runtime(active_policy, seed=route_seed)
        first_path = "runtime" if mode == "runtime_primary" and prefer_runtime else "builtin"
        second_path = "builtin" if first_path == "runtime" else "runtime"

        attempts: list[ExecutionAttempt] = []
        first_result = self._call(first_path, request, runtime_executor, builtin_executor)
        attempts.append(first_result["attempt"])
        if first_result["ok"]:
            return ExecutionResult(
                ok=True,
                path=first_path,
                result=first_result["payload"],
                error=None,
                attempts=attempts,
            )

        second_result = self._call(second_path, request, runtime_executor, builtin_executor)
        attempts.append(second_result["attempt"])
        if second_result["ok"]:
            return ExecutionResult(
                ok=True,
                path=second_path,
                result=second_result["payload"],
                error=None,
                attempts=attempts,
            )
        return ExecutionResult(
            ok=False,
            path=second_path,
            result=None,
            error={
                "type": "execution_failed",
                "message": second_result["attempt"].error or "runtime_and_builtin_failed",
            },
            attempts=attempts,
        )

    def _call(
        self,
        path: str,
        request: ExecutionRequest,
        runtime_executor: Executor,
        builtin_executor: Executor,
    ) -> dict[str, Any]:
        executor = runtime_executor if path == "runtime" else builtin_executor
        started = perf_counter()
        try:
            payload = executor(request)
        except Exception as exc:
            return {
                "ok": False,
                "payload": None,
                "attempt": ExecutionAttempt(
                    path=path,
                    ok=False,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    error=str(exc),
                ),
            }
        return {
            "ok": True,
            "payload": payload,
            "attempt": ExecutionAttempt(
                path=path,
                ok=True,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            ),
        }
