from __future__ import annotations

from typing import Any


class SearchAdapter:
    tool_name = "search"

    def to_tentacle_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or payload.get("text") or "").strip()
        top_k = int(payload.get("top_k") or payload.get("limit") or 5)
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        return {"query": query, "top_k": max(1, top_k), "filters": dict(filters)}

    def from_tentacle_response(self, response: dict[str, Any]) -> dict[str, Any]:
        items = response.get("items") if isinstance(response.get("items"), list) else []
        return {
            "summary": str(response.get("summary") or f"Found {len(items)} result(s)"),
            "items": items,
            "references": response.get("references") if isinstance(response.get("references"), list) else [],
        }

