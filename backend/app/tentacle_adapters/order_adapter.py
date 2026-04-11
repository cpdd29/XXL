from __future__ import annotations

from typing import Any


class OrderAdapter:
    tool_name = "order-query"

    def to_tentacle_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "customer": str(payload.get("customer") or "").strip(),
            "order_id": str(payload.get("order_id") or payload.get("orderId") or "").strip() or None,
            "top_k": int(payload.get("top_k") or 5),
        }

    def from_tentacle_response(self, response: dict[str, Any]) -> dict[str, Any]:
        rows = response.get("items") if isinstance(response.get("items"), list) else []
        return {
            "summary": str(response.get("summary") or f"Fetched {len(rows)} order record(s)"),
            "items": rows,
        }

