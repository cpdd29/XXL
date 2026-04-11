from __future__ import annotations

from typing import Any


class PDFAdapter:
    tool_name = "pdf"

    def to_tentacle_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        for key in ("file_path", "path", "pdf_base64", "bytes_base64", "text", "mode"):
            if key in payload and payload[key] not in {None, ""}:
                mapped[key] = payload[key]
        return mapped

    def from_tentacle_response(self, response: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": str(response.get("summary") or "PDF processed"),
            "text": response.get("text"),
            "highlights": response.get("highlights") if isinstance(response.get("highlights"), list) else [],
            "output_file": response.get("output_file"),
        }

