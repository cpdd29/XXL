from __future__ import annotations

from app.modules.dispatch.skill_runtime.skill_execution_gateway import SkillExecutionGateway
from app.platform.contracts.execution_protocol import ExecutionRequest


def test_skill_execution_gateway_builtin_mode_skips_runtime() -> None:
    gateway = SkillExecutionGateway()
    calls = {"runtime": 0, "builtin": 0, "shadow": 0}

    def runtime_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["runtime"] += 1
        return {"ok": True, "result": {"source": "runtime"}}

    def builtin_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["builtin"] += 1
        return {"ok": True, "result": {"source": "builtin"}}

    def shadow_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["shadow"] += 1
        return {"ok": True, "result": {"source": "shadow"}}

    outcome = gateway.execute(
        request=ExecutionRequest(tool_id="writer", payload={"prompt": "hello"}),
        mode="builtin_primary",
        runtime_executor=runtime_executor,
        builtin_executor=builtin_executor,
        shadow_mode=True,
        shadow_executor=shadow_executor,
    )

    assert outcome.selected_path == "builtin"
    assert calls == {"runtime": 0, "builtin": 1, "shadow": 1}
    assert outcome.builtin_result == {"ok": True, "result": {"source": "builtin"}}
    assert outcome.runtime_result is None
    assert outcome.execution_result is not None
    assert outcome.execution_result.ok is True
    assert outcome.execution_result.path == "builtin"


def test_skill_execution_gateway_runtime_primary_falls_back_to_builtin() -> None:
    gateway = SkillExecutionGateway()
    calls = {"runtime": 0, "builtin": 0}

    def runtime_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["runtime"] += 1
        return {
            "ok": False,
            "trace_id": "trace-runtime-failed",
            "error": {"message": "runtime unavailable"},
        }

    def builtin_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["builtin"] += 1
        return {"ok": True, "result": {"source": "builtin"}}

    outcome = gateway.execute(
        request=ExecutionRequest(tool_id="search", payload={"query": "agent"}),
        mode="runtime_primary",
        runtime_executor=runtime_executor,
        builtin_executor=builtin_executor,
    )

    assert outcome.selected_path == "builtin_fallback"
    assert outcome.fallback_reason == "runtime unavailable"
    assert calls == {"runtime": 1, "builtin": 1}
    assert outcome.runtime_result == {
        "ok": False,
        "trace_id": "trace-runtime-failed",
        "error": {"message": "runtime unavailable"},
    }
    assert outcome.builtin_result == {"ok": True, "result": {"source": "builtin"}}
    assert outcome.execution_result is not None
    assert outcome.execution_result.ok is True
    assert len(outcome.execution_result.attempts) == 2


def test_skill_execution_gateway_strict_runtime_required_blocks_builtin_fallback() -> None:
    gateway = SkillExecutionGateway()
    calls = {"runtime": 0, "builtin": 0}

    def runtime_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["runtime"] += 1
        return {
            "ok": False,
            "trace_id": "trace-runtime-failed",
            "error": {"message": "runtime unavailable"},
        }

    def builtin_executor(request: ExecutionRequest) -> dict:
        _ = request
        calls["builtin"] += 1
        return {"ok": True, "result": {"source": "builtin"}}

    outcome = gateway.execute(
        request=ExecutionRequest(tool_id="search", payload={"query": "agent"}),
        mode="runtime_primary",
        runtime_executor=runtime_executor,
        builtin_executor=builtin_executor,
        strict_runtime_required=True,
    )

    assert outcome.selected_path == "external_runtime_required"
    assert outcome.fallback_reason == "runtime unavailable"
    assert calls == {"runtime": 1, "builtin": 0}
    assert outcome.builtin_result is None
    assert outcome.execution_result is not None
    assert outcome.execution_result.ok is False
