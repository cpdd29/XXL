from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def clone_metadata(value: object) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def read_json_list_setting(key: str) -> list[dict[str, Any]]:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        payload, authoritative = read_setting(key)
        if authoritative:
            setting_payload = payload.get("payload") if isinstance(payload, dict) else None
            return deepcopy(setting_payload) if isinstance(setting_payload, list) else []

    get_setting = getattr(persistence_service, "get_system_setting", None)
    if callable(get_setting):
        payload = get_setting(key)
        if isinstance(payload, dict):
            setting_payload = payload.get("payload")
            if isinstance(setting_payload, list):
                return deepcopy(setting_payload)

    runtime_value = store.system_settings.get(key)
    if isinstance(runtime_value, list):
        return store.clone(runtime_value)
    return []


def write_json_list_setting(key: str, items: list[dict[str, Any]]) -> None:
    payload = deepcopy(items)
    store.system_settings[key] = store.clone(payload)
    persist_setting = getattr(persistence_service, "persist_system_setting", None)
    if callable(persist_setting):
        persist_setting(
            key=key,
            payload=payload,
            updated_at=store.now_string(),
        )
