from __future__ import annotations

from copy import deepcopy
from typing import Iterable
from uuid import uuid4

from app.modules.agent_config.protocol_bindings.schemas import (
    ActiveTaskContext,
    AdmissionStatus,
    CustomerContext,
    HermesMemoryNamespaces,
    KnowledgeHit,
    HermesProtocolRequest,
    MemoryNamespaceStrategy,
    ProtocolBinding,
    ProtocolBindingUpsertRequest,
    RetrievedLongTermMemory,
    RuntimeMemoryMode,
)
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


PROTOCOL_BINDINGS_SETTING_KEY = "protocol_bindings"


def normalize_runtime_memory_mode(value: object) -> RuntimeMemoryMode:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {
        "platform_stateless",
        "platform_only",
        "hermes_runtime_only",
        "platform_plus_hermes_runtime",
    }:
        return "platform_stateless"
    return "platform_stateless"


def _normalize_namespace_segment(value: object, *, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return fallback

    chars: list[str] = []
    last_was_dash = False
    for char in raw:
        allowed = char.isalnum() or char in {"_", "-"}
        normalized = char if allowed else "-"
        if normalized == "-":
            if last_was_dash:
                continue
            last_was_dash = True
        else:
            last_was_dash = False
        chars.append(normalized)

    collapsed = "".join(chars).strip("-")
    return collapsed or fallback


def build_memory_namespaces(
    *,
    tenant_id: str,
    customer_id: str,
    session_id: str,
    task_id: str | None = None,
) -> HermesMemoryNamespaces:
    tenant_key = _normalize_namespace_segment(tenant_id, fallback="tenant")
    customer_key = _normalize_namespace_segment(customer_id, fallback="customer")
    session_key = _normalize_namespace_segment(session_id, fallback="session")
    task_key = _normalize_namespace_segment(task_id, fallback="task") if task_id else None

    return HermesMemoryNamespaces(
        user=f"tenant/{tenant_key}/customer/{customer_key}",
        session=f"tenant/{tenant_key}/session/{session_key}",
        task=f"tenant/{tenant_key}/task/{task_key}" if task_key else None,
    )


def resolve_memory_namespace_strategy(
    *,
    strategy: MemoryNamespaceStrategy,
    namespaces: HermesMemoryNamespaces,
) -> dict[str, str | None]:
    if strategy == "tenant":
        tenant_prefix = namespaces.user.split("/customer/", maxsplit=1)[0]
        return {
            "memory_namespace_user": tenant_prefix,
            "memory_namespace_session": tenant_prefix,
            "memory_namespace_task": tenant_prefix,
        }

    if strategy == "tenant_session":
        return {
            "memory_namespace_user": namespaces.user,
            "memory_namespace_session": namespaces.session,
            "memory_namespace_task": namespaces.session,
        }

    if strategy == "tenant_task":
        task_namespace = namespaces.task or namespaces.session
        return {
            "memory_namespace_user": namespaces.user,
            "memory_namespace_session": task_namespace,
            "memory_namespace_task": task_namespace,
        }

    return {
        "memory_namespace_user": namespaces.user,
        "memory_namespace_session": namespaces.session,
        "memory_namespace_task": namespaces.task,
    }


def build_hermes_protocol_request(
    *,
    binding: ProtocolBinding,
    request_id: str,
    tenant_id: str,
    customer_id: str,
    agent_id: str,
    protocol_id: str,
    protocol_version: str,
    session_id: str,
    channel: str,
    channel_user_id: str,
    message_id: str,
    message_text: str,
    admission_status: AdmissionStatus,
    profile_id: str | None = None,
    task_id: str | None = None,
    channel_chat_id: str | None = None,
    message_language: str | None = None,
    tenant_soul: str | None = None,
    retrieved_long_term_memories: Iterable[RetrievedLongTermMemory] | None = None,
    knowledge_hits: Iterable[KnowledgeHit] | None = None,
    active_task_context: ActiveTaskContext | None = None,
    runtime_memory_mode: RuntimeMemoryMode | None = None,
    security_flags: Iterable[str] | None = None,
    customer_context: CustomerContext | None = None,
    metadata: dict | None = None,
) -> HermesProtocolRequest:
    if admission_status != "bound":
        raise ValueError("Only bound customers can enter Hermes reception")

    namespaces = build_memory_namespaces(
        tenant_id=tenant_id,
        customer_id=customer_id,
        session_id=session_id,
        task_id=task_id,
    )
    namespace_fields = resolve_memory_namespace_strategy(
        strategy=binding.memory_namespace_strategy,
        namespaces=namespaces,
    )

    return HermesProtocolRequest(
        request_id=request_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        profile_id=profile_id,
        agent_id=agent_id,
        protocol_id=protocol_id,
        protocol_version=protocol_version,
        session_id=session_id,
        task_id=task_id,
        channel=channel,
        channel_user_id=channel_user_id,
        channel_chat_id=channel_chat_id,
        message_id=message_id,
        message_text=message_text,
        message_language=message_language,
        tenant_soul=tenant_soul,
        retrieved_long_term_memories=list(retrieved_long_term_memories or []),
        knowledge_hits=list(knowledge_hits or []),
        active_task_context=active_task_context,
        memory_namespace_user=str(namespace_fields["memory_namespace_user"] or ""),
        memory_namespace_session=str(namespace_fields["memory_namespace_session"] or ""),
        memory_namespace_task=namespace_fields["memory_namespace_task"],
        runtime_memory_mode=normalize_runtime_memory_mode(runtime_memory_mode or binding.runtime_memory_mode),
        security_flags=list(security_flags or []),
        admission_status=admission_status,
        customer_context=customer_context,
        metadata=dict(metadata or {}),
    )


def _normalize_binding_payload(payload: object) -> ProtocolBinding | None:
    if not isinstance(payload, dict):
        return None
    tenant_id = str(payload.get("tenant_id") or payload.get("tenantId") or "").strip()
    agent_id = str(payload.get("agent_id") or payload.get("agentId") or "").strip()
    protocol_id = str(payload.get("protocol_id") or payload.get("protocolId") or "").strip()
    if not tenant_id or not agent_id or not protocol_id:
        return None
    binding_id = str(payload.get("binding_id") or payload.get("bindingId") or "").strip() or f"binding-{uuid4().hex[:12]}"
    return ProtocolBinding(
        binding_id=binding_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        protocol_id=protocol_id,
        protocol_version=str(payload.get("protocol_version") or payload.get("protocolVersion") or "v1").strip() or "v1",
        target_provider=str(payload.get("target_provider") or payload.get("targetProvider") or "hermes").strip() or "hermes",
        target_instance_id=str(payload.get("target_instance_id") or payload.get("targetInstanceId") or "").strip() or None,
        target_base_url=str(payload.get("target_base_url") or payload.get("targetBaseUrl") or "").strip() or None,
        runtime_memory_mode=normalize_runtime_memory_mode(
            payload.get("runtime_memory_mode") or payload.get("runtimeMemoryMode")
        ),
        memory_namespace_strategy=str(payload.get("memory_namespace_strategy") or payload.get("memoryNamespaceStrategy") or "tenant_customer").strip(),  # type: ignore[arg-type]
        enabled=bool(payload.get("enabled", True)),
        metadata=deepcopy(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
        created_at=str(payload.get("created_at") or payload.get("createdAt") or "").strip() or None,
        updated_at=str(payload.get("updated_at") or payload.get("updatedAt") or "").strip() or None,
    )


def _read_bindings() -> list[ProtocolBinding]:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        persisted, authoritative = read_setting(PROTOCOL_BINDINGS_SETTING_KEY)
        if authoritative and isinstance(persisted, dict):
            payload = persisted.get("payload")
            items = payload if isinstance(payload, list) else []
            bindings = [
                binding
                for item in items
                if (binding := _normalize_binding_payload(item)) is not None
            ]
            store.system_settings[PROTOCOL_BINDINGS_SETTING_KEY] = [item.model_dump(mode="json") for item in bindings]
            return bindings

    cached = store.system_settings.get(PROTOCOL_BINDINGS_SETTING_KEY)
    if isinstance(cached, list):
        return [
            binding
            for item in cached
            if (binding := _normalize_binding_payload(item)) is not None
        ]
    return []


def _persist_bindings(bindings: list[ProtocolBinding]) -> None:
    payload = [binding.model_dump(mode="json") for binding in bindings]
    store.system_settings[PROTOCOL_BINDINGS_SETTING_KEY] = deepcopy(payload)
    persistence_service.persist_system_setting(
        key=PROTOCOL_BINDINGS_SETTING_KEY,
        payload=payload,  # type: ignore[arg-type]
        updated_at=store.now_string(),
    )


def list_protocol_bindings(*, tenant_id: str | None = None, agent_id: str | None = None) -> list[ProtocolBinding]:
    bindings = _read_bindings()
    normalized_tenant_id = str(tenant_id or "").strip()
    normalized_agent_id = str(agent_id or "").strip()
    items: list[ProtocolBinding] = []
    for binding in bindings:
        if normalized_tenant_id and binding.tenant_id != normalized_tenant_id:
            continue
        if normalized_agent_id and binding.agent_id != normalized_agent_id:
            continue
        items.append(binding)
    items.sort(key=lambda item: (item.tenant_id, item.agent_id, item.binding_id))
    return items


def get_protocol_binding(*, tenant_id: str, agent_id: str) -> ProtocolBinding | None:
    for binding in list_protocol_bindings(tenant_id=tenant_id, agent_id=agent_id):
        if binding.enabled:
            return binding
    return None


def upsert_protocol_binding(payload: ProtocolBindingUpsertRequest) -> ProtocolBinding:
    bindings = _read_bindings()
    binding_id = str(payload.binding_id or "").strip() or f"binding-{uuid4().hex[:12]}"
    updated = ProtocolBinding(
        binding_id=binding_id,
        tenant_id=payload.tenant_id,
        agent_id=payload.agent_id,
        protocol_id=payload.protocol_id,
        protocol_version=payload.protocol_version,
        target_provider=payload.target_provider,
        target_instance_id=payload.target_instance_id,
        target_base_url=payload.target_base_url,
        runtime_memory_mode=payload.runtime_memory_mode,
        memory_namespace_strategy=payload.memory_namespace_strategy,
        enabled=payload.enabled,
        metadata=deepcopy(payload.metadata),
        updated_at=store.now_string(),
    )
    created_at = None
    replaced = False
    for index, existing in enumerate(bindings):
        if existing.binding_id == binding_id or (
            existing.tenant_id == updated.tenant_id and existing.agent_id == updated.agent_id
        ):
            created_at = existing.created_at
            updated.created_at = created_at or updated.updated_at
            bindings[index] = updated
            replaced = True
            break
    if not replaced:
        updated.created_at = updated.updated_at
        bindings.append(updated)

    _persist_bindings(bindings)
    return updated


def delete_protocol_binding(
    *,
    binding_id: str | None = None,
    tenant_id: str | None = None,
    agent_id: str | None = None,
) -> ProtocolBinding:
    normalized_binding_id = str(binding_id or "").strip()
    normalized_tenant_id = str(tenant_id or "").strip()
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_binding_id and not (normalized_tenant_id and normalized_agent_id):
        raise ValueError("删除协议绑定时需要提供 bindingId，或同时提供 tenantId 与 agentId。")

    bindings = _read_bindings()
    deleted: ProtocolBinding | None = None
    remaining: list[ProtocolBinding] = []
    for binding in bindings:
        matched_by_id = bool(normalized_binding_id) and binding.binding_id == normalized_binding_id
        matched_by_pair = (
            not normalized_binding_id
            and binding.tenant_id == normalized_tenant_id
            and binding.agent_id == normalized_agent_id
        )
        if deleted is None and (matched_by_id or matched_by_pair):
            deleted = binding
            continue
        remaining.append(binding)

    if deleted is None:
        raise LookupError("未找到可删除的协议绑定。")

    _persist_bindings(remaining)
    return deleted
