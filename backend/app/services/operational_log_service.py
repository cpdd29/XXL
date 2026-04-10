from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.services.persistence_service import persistence_service
from app.services.store import store


RUNTIME_OPERATIONAL_LOG_LIMIT = 20


def append_realtime_event(
    *,
    agent: str,
    message: str,
    type_: str = "info",
    source: str = "runtime",
    timestamp: datetime | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    workflow_run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = timestamp or datetime.now(UTC)
    event_id = f"rt-{uuid4().hex[:10]}"
    payload = {
        "id": event_id,
        "timestamp": now.isoformat(),
        "type": str(type_ or "info"),
        "agent": str(agent or "Runtime"),
        "message": str(message or ""),
        "source": str(source or "runtime"),
        "trace_id": str(trace_id).strip() or None if trace_id is not None else None,
        "task_id": str(task_id).strip() or None if task_id is not None else None,
        "workflow_run_id": (
            str(workflow_run_id).strip() or None if workflow_run_id is not None else None
        ),
        "metadata": store.clone(metadata) if isinstance(metadata, dict) else None,
    }

    store.realtime_logs.insert(
        0,
        {
            "id": event_id,
            "timestamp": now.strftime("%H:%M:%S"),
            "type": payload["type"],
            "agent": payload["agent"],
            "message": payload["message"],
            "source": payload["source"],
        },
    )
    del store.realtime_logs[RUNTIME_OPERATIONAL_LOG_LIMIT:]

    persistence_service.append_operational_log(log=payload)
    return payload
