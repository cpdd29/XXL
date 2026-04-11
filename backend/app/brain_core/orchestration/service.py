from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.execution_gateway.contracts import ExecutionRequest


@dataclass(slots=True)
class OrchestrationService:
    """Build execution-gateway requests from brain decisions."""

    def build_execution_request(
        self,
        *,
        tool_id: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        run_id: str | None = None,
        workflow_mode: str | None = None,
    ) -> ExecutionRequest:
        trace_context = {
            "task_id": task_id,
            "run_id": run_id,
            "workflow_mode": workflow_mode or "unknown",
        }
        return ExecutionRequest(
            tool_id=tool_id,
            payload=dict(payload),
            trace_context=trace_context,
        )

