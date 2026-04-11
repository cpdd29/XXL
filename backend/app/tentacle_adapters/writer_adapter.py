from __future__ import annotations

from typing import Any


class WriterAdapter:
    tool_name = "writer"

    def to_tentacle_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt") or payload.get("topic") or payload.get("text") or "").strip()
        style = str(payload.get("style") or "clear").strip()
        audience = str(payload.get("audience") or "general").strip()
        return {"prompt": prompt, "style": style, "audience": audience}

    def from_tentacle_response(self, response: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": str(response.get("summary") or "Draft generated"),
            "content": str(response.get("content") or ""),
            "outline": response.get("outline") if isinstance(response.get("outline"), list) else [],
        }

