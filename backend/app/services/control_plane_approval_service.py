from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.services.control_plane_audit_service import append_control_plane_audit_log
from app.services.persistence_service import persistence_service
from app.services.store import store


CONTROL_PLANE_APPROVALS_KEY = "control_plane_approvals"


def _read_setting_payload() -> tuple[list[dict[str, Any]], bool]:
    payload, authoritative = persistence_service.read_system_setting(CONTROL_PLANE_APPROVALS_KEY)
    if authoritative:
        data = payload.get("items") if isinstance(payload, dict) else []
        return (deepcopy(data) if isinstance(data, list) else []), True
    items = store.system_settings.get(CONTROL_PLANE_APPROVALS_KEY, {}).get("items", [])
    return deepcopy(items) if isinstance(items, list) else [], False


def _persist_items(items: list[dict[str, Any]]) -> None:
    payload = {"items": deepcopy(items)}
    if not persistence_service.persist_system_setting(
        key=CONTROL_PLANE_APPROVALS_KEY,
        payload=payload,
        updated_at=datetime.now(UTC).isoformat(),
    ):
        store.system_settings[CONTROL_PLANE_APPROVALS_KEY] = payload


def list_approvals(*, status_filter: str | None = None, request_type: str | None = None) -> dict:
    items, _ = _read_setting_payload()
    normalized_status = str(status_filter or "").strip().lower() or None
    normalized_type = str(request_type or "").strip().lower() or None
    filtered: list[dict] = []
    for item in items:
        if normalized_status and str(item.get("status") or "").strip().lower() != normalized_status:
            continue
        if normalized_type and str(item.get("request_type") or "").strip().lower() != normalized_type:
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: str(item.get("requested_at") or ""), reverse=True)
    return {"items": filtered, "total": len(filtered)}


def create_approval(
    *,
    request_type: str,
    title: str,
    resource: str,
    requested_by: str,
    reason: str | None = None,
    note: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict:
    items, _ = _read_setting_payload()
    approval = {
        "id": f"approval-{uuid4().hex[:10]}",
        "request_type": request_type,
        "status": "pending",
        "title": title,
        "resource": resource,
        "requested_by": requested_by,
        "requested_at": datetime.now(UTC).isoformat(),
        "reviewed_by": None,
        "reviewed_at": None,
        "reason": str(reason or "").strip() or None,
        "note": str(note or "").strip() or None,
        "payload": deepcopy(payload) if isinstance(payload, dict) else {},
    }
    items.insert(0, approval)
    _persist_items(items)
    append_control_plane_audit_log(
        action="approval.created",
        user=requested_by,
        resource=f"approval:{approval['resource']}",
        details=f"创建审批单 {approval['title']}",
        metadata={"approval_id": approval["id"], "request_type": approval["request_type"]},
    )
    return approval


def _payload_hash(payload: dict[str, Any] | None) -> str:
    normalized = deepcopy(payload) if isinstance(payload, dict) else {}
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def create_bound_approval(
    *,
    request_type: str,
    title: str,
    resource: str,
    requested_by: str,
    request_payload: dict[str, Any] | None = None,
    target_action: str,
    reason: str | None = None,
    note: str | None = None,
) -> dict:
    normalized_payload = deepcopy(request_payload) if isinstance(request_payload, dict) else {}
    normalized_payload["_control_plane"] = {
        "target_action": target_action,
        "resource": resource,
        "requested_by": requested_by,
        "request_payload_hash": _payload_hash(normalized_payload),
    }
    return create_approval(
        request_type=request_type,
        title=title,
        resource=resource,
        requested_by=requested_by,
        reason=reason,
        note=note,
        payload=normalized_payload,
    )


def _find_approval_mutable(approval_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items, _ = _read_setting_payload()
    normalized_approval_id = str(approval_id or "").strip()
    for item in items:
        if str(item.get("id") or "").strip() == normalized_approval_id:
            return items, item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")


def process_approval(
    approval_id: str,
    *,
    next_status: str,
    reviewer: str,
    note: str | None = None,
) -> dict:
    if next_status not in {"approved", "rejected", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported approval status")
    items, approval = _find_approval_mutable(approval_id)
    if str(approval.get("status") or "").strip().lower() != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval is not pending")
    approval["status"] = next_status
    approval["reviewed_by"] = reviewer
    approval["reviewed_at"] = datetime.now(UTC).isoformat()
    approval["note"] = str(note or approval.get("note") or "").strip() or None
    _persist_items(items)
    append_control_plane_audit_log(
        action=f"approval.{next_status}",
        user=reviewer,
        resource=f"approval:{approval['resource']}",
        details=f"{next_status} 审批单 {approval['title']}",
        metadata={"approval_id": approval["id"], "request_type": approval["request_type"]},
    )
    return approval


def require_approved_execution(
    approval_id: str,
    *,
    request_type: str,
    resource: str,
    request_payload: dict[str, Any] | None,
    target_action: str,
    executed_by: str,
    execution_ref: str | None = None,
) -> dict[str, Any]:
    items, approval = _find_approval_mutable(approval_id)
    if str(approval.get("status") or "").strip().lower() != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval is not approved")
    if str(approval.get("request_type") or "").strip().lower() != str(request_type).strip().lower():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval request type mismatch")
    if str(approval.get("resource") or "").strip() != str(resource or "").strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval resource mismatch")
    if approval.get("executed_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval already executed")

    binding = approval.get("payload") if isinstance(approval.get("payload"), dict) else {}
    control_plane = (
        binding.get("_control_plane") if isinstance(binding.get("_control_plane"), dict) else {}
    )
    expected_hash = str(control_plane.get("request_payload_hash") or "").strip()
    if expected_hash and expected_hash != _payload_hash(request_payload):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval payload mismatch")
    expected_target_action = str(control_plane.get("target_action") or "").strip()
    if expected_target_action and expected_target_action != str(target_action or "").strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval target action mismatch")

    approval["executed_by"] = executed_by
    approval["executed_at"] = datetime.now(UTC).isoformat()
    approval["execution_ref"] = str(execution_ref or target_action or approval_id).strip() or approval_id
    _persist_items(items)
    append_control_plane_audit_log(
        action="approval.executed",
        user=executed_by,
        resource=f"approval:{approval['resource']}",
        details=f"执行审批单 {approval['title']}",
        metadata={
            "approval_id": approval["id"],
            "request_type": approval["request_type"],
            "execution_ref": approval["execution_ref"],
        },
    )
    return approval
