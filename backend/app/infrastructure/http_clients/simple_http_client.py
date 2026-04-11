from __future__ import annotations

from typing import Any

import httpx


class SimpleHTTPClient:
    """Thin HTTP client wrapper used by the new infrastructure layer."""

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        timeout_seconds: float = 15.0,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"data": parsed}

