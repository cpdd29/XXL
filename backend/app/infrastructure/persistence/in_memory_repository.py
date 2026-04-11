from __future__ import annotations

from copy import deepcopy
from typing import Any


class InMemoryRepository:
    """Generic in-memory repository for compatibility and tests."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def upsert(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_id = str(item_id).strip()
        if not normalized_id:
            raise ValueError("item_id is required")
        self._data[normalized_id] = deepcopy(payload)
        return deepcopy(self._data[normalized_id])

    def get(self, item_id: str) -> dict[str, Any] | None:
        normalized_id = str(item_id).strip()
        value = self._data.get(normalized_id)
        return deepcopy(value) if value is not None else None

    def list_items(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._data.values()]

