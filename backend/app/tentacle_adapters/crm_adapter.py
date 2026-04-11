from __future__ import annotations

from typing import Any


class CRMAdapter:
    tool_name = "crm-query"

    def to_tentacle_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "customer": str(payload.get("customer") or "").strip(),
            "fields": payload.get("fields") if isinstance(payload.get("fields"), list) else [],
            "top_k": int(payload.get("top_k") or 5),
        }

    def from_tentacle_response(self, response: dict[str, Any]) -> dict[str, Any]:
        rows = response.get("items") if isinstance(response.get("items"), list) else []
        return {
            "summary": str(response.get("summary") or f"Fetched {len(rows)} CRM record(s)"),
            "items": rows,
        }

