"""Execution gateway layer.

This layer is the only execution entrance for tentacle invocations.
"""

from app.execution_gateway.contracts import ExecutionAttempt, ExecutionRequest, ExecutionResult
from app.execution_gateway.policy import TrafficPolicy, resolve_effective_mode, should_use_runtime
from app.execution_gateway.runtime_router import RuntimeRouter
from app.execution_gateway.skill_execution_gateway import (
    SkillExecutionGateway,
    SkillExecutionOutcome,
)

__all__ = [
    "ExecutionAttempt",
    "ExecutionRequest",
    "ExecutionResult",
    "TrafficPolicy",
    "RuntimeRouter",
    "SkillExecutionGateway",
    "SkillExecutionOutcome",
    "resolve_effective_mode",
    "should_use_runtime",
]
