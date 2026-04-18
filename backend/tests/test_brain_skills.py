from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api.routes import agents as agents_route
from app.main import app
from app.services.brain_skill_service import (
    BRAIN_SKILL_LIBRARY_SETTING_KEY,
    BRAIN_SKILL_LIBRARY_SOURCE,
    BrainSkillService,
)
from app.services.skill_registry_service import skill_registry_service
from app.services.store import store
from app.services.tool_source_service import ToolSourceService


client = TestClient(app)


class _MemoryPersistence:
    def __init__(self) -> None:
        self._settings: dict[str, dict] = {}

    def read_system_setting(self, key: str) -> tuple[dict | None, bool]:
        payload = self._settings.get(key)
        if payload is None:
            return None, False
        return {
            "key": key,
            "payload": deepcopy(payload),
            "updated_at": "",
        }, True

    def persist_system_setting(self, *, key: str, payload: dict, updated_at: str | None = None) -> bool:
        self._settings[key] = deepcopy(payload)
        return True


@pytest.fixture(autouse=True)
def reset_brain_skill_runtime_state() -> None:
    original_setting = deepcopy(store.system_settings.get(BRAIN_SKILL_LIBRARY_SETTING_KEY))
    original_registry = skill_registry_service.list_abilities(enabled=None)
    store.system_settings.pop(BRAIN_SKILL_LIBRARY_SETTING_KEY, None)
    skill_registry_service.clear()
    yield
    store.system_settings.pop(BRAIN_SKILL_LIBRARY_SETTING_KEY, None)
    if original_setting is not None:
        store.system_settings[BRAIN_SKILL_LIBRARY_SETTING_KEY] = original_setting
    skill_registry_service.clear()
    for ability in original_registry:
        skill_registry_service.register_ability(ability, overwrite=True)


def _mount_brain_skill_service(monkeypatch: pytest.MonkeyPatch) -> BrainSkillService:
    service = BrainSkillService(
        runtime_store=store,
        persistence=_MemoryPersistence(),
        registry=skill_registry_service,
    )
    monkeypatch.setattr(agents_route, "brain_skill_service", service)
    return service


def test_upload_list_and_delete_brain_skill_routes(auth_headers, monkeypatch: pytest.MonkeyPatch) -> None:
    _mount_brain_skill_service(monkeypatch)

    response = client.post(
        "/api/agents/brain-skills",
        headers=auth_headers,
        json={
            "fileName": "handoff_packet_builder.yaml",
            "content": """
id: handoff-packet-builder
name: Handoff Packet Builder
description: 负责构建主脑交接包。
capabilities:
  - handoff
  - packet
tags:
  - brain
  - workflow
enabled: true
""".strip(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["skill"]["id"] == "handoff-packet-builder"
    assert payload["skill"]["name"] == "Handoff Packet Builder"
    assert payload["skill"]["fileName"] == "handoff_packet_builder.yaml"
    assert payload["skill"]["format"] == "yaml"
    assert payload["skill"]["capabilities"] == ["handoff", "packet"]
    assert payload["skill"]["tags"] == ["brain", "workflow"]

    stored_library = store.system_settings[BRAIN_SKILL_LIBRARY_SETTING_KEY]
    assert len(stored_library["items"]) == 1
    assert stored_library["items"][0]["file_name"] == "handoff_packet_builder.yaml"

    registered = skill_registry_service.get_ability("handoff-packet-builder")
    assert registered is not None
    assert registered["source"] == BRAIN_SKILL_LIBRARY_SOURCE
    assert registered["metadata"]["display_name"] == "Handoff Packet Builder"

    listed = client.get("/api/agents/brain-skills", headers=auth_headers)
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload["total"] == 1
    assert listed_payload["items"][0]["id"] == "handoff-packet-builder"

    deleted = client.delete("/api/agents/brain-skills/handoff-packet-builder", headers=auth_headers)
    assert deleted.status_code == 200
    assert deleted.json()["skillId"] == "handoff-packet-builder"

    refreshed = client.get("/api/agents/brain-skills", headers=auth_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["total"] == 0
    assert skill_registry_service.get_ability("handoff-packet-builder") is None


def test_upload_markdown_skill_bootstrap_keeps_it_out_of_internal_tool_catalog(
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _mount_brain_skill_service(monkeypatch)

    created = client.post(
        "/api/agents/brain-skills",
        headers=auth_headers,
        json={
            "fileName": "tenant_profile_memory.md",
            "content": """
---
id: tenant-profile-memory
name: Tenant Profile Memory
tags:
  - memory
capabilities:
  - profile
---
负责整理租户下的画像记忆。
""".strip(),
        },
    )
    assert created.status_code == 200

    service.bootstrap()
    source_service = ToolSourceService()
    _, internal_tools = source_service._scan_internal_skills_source()

    assert skill_registry_service.get_ability("tenant-profile-memory") is not None
    assert all(tool["id"] != "tenant-profile-memory" for tool in internal_tools)


def test_create_brain_skill_route_requires_agents_reload_permission(
    auth_headers_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mount_brain_skill_service(monkeypatch)

    response = client.post(
        "/api/agents/brain-skills",
        headers=auth_headers_factory(role="power_user"),
        json={
            "fileName": "blocked_skill.yaml",
            "content": "name: blocked skill",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
