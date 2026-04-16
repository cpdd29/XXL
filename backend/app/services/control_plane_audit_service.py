from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.services.persistence_service import persistence_service
from app.services.store import store
from app.services.tenancy_service import attach_scope, default_scope


def append_control_plane_audit_log(
    *,
    action: str,
    user: str,
    resource: str,
    details: str,
    status_text: str = "success",
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    scope = default_scope()
    if tenant_id:
        scope["tenant_id"] = tenant_id
    if project_id:
        scope["project_id"] = project_id
    if environment:
        scope["environment"] = environment
    payload: dict[str, Any] = {
        "id": f"audit-control-plane-{uuid4().hex[:12]}",
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "action": action,
        "user": user,
        "resource": resource,
        "status": status_text,
        "ip": "-",
        "details": details,
    }
    if metadata:
        payload["metadata"] = deepcopy(metadata)
    payload = attach_scope(payload, scope=scope)

    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    return payload
