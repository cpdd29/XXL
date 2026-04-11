from __future__ import annotations

from typing import Any


class WeatherAdapter:
    tool_name = "weather"

    def to_tentacle_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        location = str(payload.get("location") or payload.get("city") or payload.get("query") or "").strip()
        duration = int(payload.get("duration") or 3)
        return {"location": location, "duration": max(1, duration)}

    def from_tentacle_response(self, response: dict[str, Any]) -> dict[str, Any]:
        forecasts = response.get("forecasts") if isinstance(response.get("forecasts"), list) else []
        return {
            "summary": str(response.get("summary") or "Weather fetched"),
            "location": response.get("location"),
            "forecasts": forecasts,
        }

