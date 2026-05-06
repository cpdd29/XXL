from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent_config.protocol_bindings.schemas import ProtocolBindingUpsertRequest
from app.modules.agent_config.protocol_bindings.service import (
    PROTOCOL_BINDINGS_SETTING_KEY,
    delete_protocol_binding,
    list_protocol_bindings,
    upsert_protocol_binding,
)
from app.platform.persistence.runtime_store import store

client = TestClient(app)


def _seed_binding(*, tenant_id: str, agent_id: str, protocol_id: str) -> str:
    payload = ProtocolBindingUpsertRequest(
        tenant_id=tenant_id,
        agent_id=agent_id,
        protocol_id=protocol_id,
    )
    binding = upsert_protocol_binding(payload)
    return binding.binding_id


def test_delete_protocol_binding_by_binding_id() -> None:
    first_id = _seed_binding(tenant_id="tenant-a", agent_id="agent-a", protocol_id="protocol-a")
    _seed_binding(tenant_id="tenant-b", agent_id="agent-b", protocol_id="protocol-b")

    deleted = delete_protocol_binding(binding_id=first_id)
    bindings = list_protocol_bindings()

    assert deleted.binding_id == first_id
    assert len(bindings) == 1
    assert bindings[0].tenant_id == "tenant-b"


def test_delete_protocol_binding_by_tenant_and_agent() -> None:
    _seed_binding(tenant_id="tenant-x", agent_id="agent-x", protocol_id="protocol-x")
    _seed_binding(tenant_id="tenant-y", agent_id="agent-y", protocol_id="protocol-y")

    deleted = delete_protocol_binding(tenant_id="tenant-y", agent_id="agent-y")
    bindings = list_protocol_bindings()

    assert deleted.tenant_id == "tenant-y"
    assert deleted.agent_id == "agent-y"
    assert len(bindings) == 1
    assert bindings[0].tenant_id == "tenant-x"


def test_delete_protocol_binding_requires_selector() -> None:
    _seed_binding(tenant_id="tenant-a", agent_id="agent-a", protocol_id="protocol-a")

    with pytest.raises(ValueError, match="需要提供 bindingId"):
        delete_protocol_binding()


def test_delete_protocol_binding_not_found() -> None:
    store.system_settings[PROTOCOL_BINDINGS_SETTING_KEY] = []

    with pytest.raises(LookupError, match="未找到"):
        delete_protocol_binding(binding_id="binding-missing")


def test_delete_protocol_binding_route_by_binding_id(auth_headers) -> None:
    upsert_response = client.put(
        "/api/protocol-bindings",
        headers=auth_headers,
        json={
            "tenantId": "tenant-route-a",
            "agentId": "agent-route-a",
            "protocolId": "protocol-route-a",
        },
    )
    assert upsert_response.status_code == 200
    binding_id = upsert_response.json()["binding"]["bindingId"]

    delete_response = client.delete(
        f"/api/protocol-bindings?bindingId={binding_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 200
    body = delete_response.json()
    assert body["ok"] is True
    assert body["binding"]["bindingId"] == binding_id


def test_delete_protocol_binding_route_requires_selector(auth_headers) -> None:
    response = client.delete("/api/protocol-bindings", headers=auth_headers)

    assert response.status_code == 400
    assert "需要提供 bindingId" in response.json()["detail"]
