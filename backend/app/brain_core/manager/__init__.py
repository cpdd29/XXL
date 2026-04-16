"""Brain-local receptionist/project-manager module."""

from app.brain_core.manager.policies import (
    build_clarify_question,
    build_decomposition_hint,
    build_delivery_mode,
    build_handoff_summary,
    build_manager_action,
    build_next_owner,
    build_response_contract,
    build_task_shape,
    build_workflow_admission,
    clarify_required_for_reception_mode,
    truncate_manager_text,
)
from app.brain_core.manager.service import BrainManagerPacket, BrainManagerService

__all__ = [
    "BrainManagerPacket",
    "BrainManagerService",
    "build_clarify_question",
    "build_decomposition_hint",
    "build_delivery_mode",
    "build_handoff_summary",
    "build_manager_action",
    "build_next_owner",
    "build_response_contract",
    "build_task_shape",
    "build_workflow_admission",
    "clarify_required_for_reception_mode",
    "truncate_manager_text",
]
