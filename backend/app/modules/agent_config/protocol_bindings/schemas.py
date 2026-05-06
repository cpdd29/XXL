from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


RuntimeMemoryMode = Literal[
    "platform_stateless",
]

InteractionMode = Literal[
    "continuation",
    "chat",
    "task",
]

MemoryNamespaceStrategy = Literal[
    "tenant",
    "tenant_customer",
    "tenant_session",
    "tenant_task",
]

AdmissionStatus = Literal["bound", "pending_verification", "rejected"]

TaskSignal = Literal["stay_in_reception", "dispatch_task"]


class ProtocolBinding(APIModel):
    binding_id: str
    tenant_id: str
    agent_id: str
    protocol_id: str
    protocol_version: str
    target_provider: str = "hermes"
    target_instance_id: str | None = None
    target_base_url: str | None = None
    runtime_memory_mode: RuntimeMemoryMode = "platform_stateless"
    memory_namespace_strategy: MemoryNamespaceStrategy = "tenant_customer"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class CustomerContext(APIModel):
    company_name: str | None = None
    contact_name: str | None = None
    mobile: str | None = None
    service_status: str | None = None
    tags: list[str] = Field(default_factory=list)
    profile_summary: str | None = None
    preferences: list[str] = Field(default_factory=list)
    business_background: list[str] = Field(default_factory=list)
    decision_history: list[str] = Field(default_factory=list)


class RetrievedLongTermMemory(APIModel):
    memory_id: str | None = None
    memory_type: str
    scope: str
    subject_id: str | None = None
    title: str | None = None
    summary: str
    importance: float | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeHit(APIModel):
    title: str | None = None
    summary: str
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HermesMemoryNamespaces(APIModel):
    user: str
    session: str
    task: str | None = None


class ActiveTaskContext(APIModel):
    task_id: str
    title: str | None = None
    status: str | None = None
    summary: str | None = None
    updated_at: str | None = None


class HermesProtocolRequest(APIModel):
    request_id: str
    tenant_id: str
    customer_id: str
    profile_id: str | None = None
    agent_id: str
    protocol_id: str
    protocol_version: str
    session_id: str
    task_id: str | None = None
    channel: str
    channel_user_id: str
    channel_chat_id: str | None = None
    message_id: str
    message_text: str
    message_language: str | None = None
    tenant_soul: str | None = None
    retrieved_long_term_memories: list[RetrievedLongTermMemory] = Field(default_factory=list)
    knowledge_hits: list[KnowledgeHit] = Field(default_factory=list)
    active_task_context: ActiveTaskContext | None = None
    memory_namespace_user: str
    memory_namespace_session: str
    memory_namespace_task: str | None = None
    runtime_memory_mode: RuntimeMemoryMode = "platform_stateless"
    security_flags: list[str] = Field(default_factory=list)
    admission_status: AdmissionStatus
    customer_context: CustomerContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryWritebackItem(APIModel):
    scope: Literal["tenant", "customer", "task_summary"]
    memory_type: str
    subject_id: str | None = None
    title: str | None = None
    summary: str
    importance: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RequirementPayload(APIModel):
    summary: str | None = None
    details: str | None = None
    category: str | None = None
    urgency: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProtocolAttachment(APIModel):
    title: str | None = None
    file_name: str
    file_path: str
    mime_type: str | None = None
    kind: str | None = None
    format: str | None = None
    size_bytes: int | None = None


class HermesProtocolResponse(APIModel):
    request_id: str
    reply_text: str
    interaction_mode: InteractionMode = "chat"
    intent: str | None = None
    needs_clarification: bool = False
    clarify_question: str | None = None
    task_signal: TaskSignal | None = None
    requirement_payload: RequirementPayload | None = None
    memory_writeback: list[MemoryWritebackItem] = Field(default_factory=list)
    attachments: list[ProtocolAttachment] = Field(default_factory=list)
    safety_signal: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProtocolBindingUpsertRequest(APIModel):
    binding_id: str | None = None
    tenant_id: str
    agent_id: str
    protocol_id: str
    protocol_version: str = "v1"
    target_provider: str = "hermes"
    target_instance_id: str | None = None
    target_base_url: str | None = None
    runtime_memory_mode: RuntimeMemoryMode = "platform_stateless"
    memory_namespace_strategy: MemoryNamespaceStrategy = "tenant_customer"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProtocolBindingListResponse(APIModel):
    items: list[ProtocolBinding]
    total: int


class ProtocolBindingActionResponse(APIModel):
    ok: bool
    message: str
    binding: ProtocolBinding
