from __future__ import annotations

from typing import Any


class TaskViewService:
    """Render lightweight task-facing summaries from task records."""

    def summarize(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            "current_stage": task.get("current_stage") or task.get("dispatch_state"),
            "status_reason": task.get("status_reason"),
            "updated_at": task.get("updated_at"),
        }

