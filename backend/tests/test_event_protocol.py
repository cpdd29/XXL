from __future__ import annotations

import json

from app.core.event_protocol import (
    BUS_PAYLOAD_MAX_BYTES,
    build_event_envelope,
    is_legacy_agent_protocol_envelope,
    is_event_envelope,
    normalize_event_envelope,
    summarize_payload_for_bus,
    validate_event_envelope,
)
from app.core.event_types import MESSAGE_TYPE_AUDIT, MESSAGE_TYPE_COMMAND, MESSAGE_TYPE_EVENT, MESSAGE_TYPE_REALTIME


def test_build_event_envelope_creates_complete_protocol_payload() -> None:
    envelope = build_event_envelope(
        subject="brain.agent.execution.request",
        event_name="brain.agent.execution.request",
        message_type=MESSAGE_TYPE_COMMAND,
        aggregate={"type": "agent_execution", "id": "run-1"},
        trace={"trace_id": "trace-1", "request_id": "req-1"},
        routing={"partition_key": "workflow-1", "idempotency_key": "idem-1"},
        source={"kind": "dispatcher", "id": "brain-1"},
        target={"kind": "worker", "id": "queue-1"},
        payload={"run_id": "run-1"},
    )

    assert is_event_envelope(envelope) is True
    assert envelope["event_name"] == "brain.agent.execution.request"
    assert envelope["message_type"] == MESSAGE_TYPE_COMMAND
    assert envelope["aggregate"]["id"] == "run-1"
    assert envelope["trace"]["trace_id"] == "trace-1"
    assert envelope["routing"]["idempotency_key"] == "idem-1"
    assert envelope["payload"]["run_id"] == "run-1"


def test_normalize_event_envelope_wraps_legacy_payload_without_breaking_fields() -> None:
    legacy_payload = {
        "type": "workflow_run.updated",
        "workflowId": "workflow-1",
        "run": {"id": "run-1"},
        "items": [{"id": "run-1"}],
    }

    normalized = normalize_event_envelope("workflow.runs.workflow-1", legacy_payload)

    assert normalized["type"] == "workflow_run.updated"
    assert normalized["workflowId"] == "workflow-1"
    assert normalized["event_name"] == "workflow_run.updated"
    assert normalized["message_type"] == MESSAGE_TYPE_EVENT
    assert normalized["payload"]["workflowId"] == "workflow-1"
    assert normalized["spec_version"] == "brain_event.v1"


def test_validate_event_envelope_fills_required_defaults_for_legacy_payload() -> None:
    normalized = validate_event_envelope(
        "brain.workflow.run.updated",
        {"type": "workflow_run.updated", "workflow_id": "workflow-1"},
    )

    assert normalized["subject"] == "brain.workflow.run.updated"
    assert normalized["event_id"].startswith("evt_")
    assert normalized["aggregate"]["type"] == "event"
    assert normalized["routing"]["idempotency_key"]
    assert normalized["timing"]["emitted_at"]


def test_validate_event_envelope_keeps_stable_idempotency_key_for_same_legacy_payload() -> None:
    payload = {
        "type": "workflow_run.updated",
        "workflow_id": "workflow-1",
        "run_id": "run-1",
    }

    first = validate_event_envelope("brain.workflow.run.updated", payload)
    second = validate_event_envelope("brain.workflow.run.updated", payload)

    assert first["routing"]["idempotency_key"] == second["routing"]["idempotency_key"]
    assert first["routing"]["partition_key"] == second["routing"]["partition_key"] == "workflow-1"


def test_build_event_envelope_keeps_lease_until_field() -> None:
    envelope = build_event_envelope(
        subject="brain.internal_event.delivery.claimed",
        event_name="brain.internal_event.delivery.claimed",
        aggregate={"type": "internal_event_delivery", "id": "evt-1"},
        timing={
            "emitted_at": "2026-04-13T10:00:00+00:00",
            "available_at": "2026-04-13T10:00:00+00:00",
            "lease_until": "2026-04-13T10:01:00+00:00",
        },
        payload={"internal_event_id": "evt-1"},
    )

    assert envelope["timing"]["lease_until"] == "2026-04-13T10:01:00+00:00"


def test_validate_event_envelope_normalizes_lease_until_from_legacy_payload() -> None:
    normalized = validate_event_envelope(
        "brain.internal_event.delivery.claimed",
        {
            "type": "brain.internal_event.delivery.claimed",
            "internal_event_id": "evt-legacy-1",
            "lease_until": "2026-04-13T10:01:00+00:00",
        },
    )

    assert normalized["timing"]["lease_until"] == "2026-04-13T10:01:00+00:00"


def test_build_event_envelope_supports_audit_and_trace_chain_fields() -> None:
    envelope = build_event_envelope(
        subject="brain.control.audit",
        event_name="brain.control.audit",
        message_type=MESSAGE_TYPE_AUDIT,
        aggregate={"type": "audit", "id": "audit-1"},
        trace={
            "trace_id": "trace-audit-1",
            "parent_event_id": "evt-parent-1",
            "causation_id": "evt-cause-1",
            "correlation_id": "corr-1",
        },
        payload={"message": "control plane audit"},
    )

    assert envelope["message_type"] == MESSAGE_TYPE_AUDIT
    assert envelope["trace"]["parent_event_id"] == "evt-parent-1"
    assert envelope["trace"]["causation_id"] == "evt-cause-1"
    assert envelope["trace"]["correlation_id"] == "corr-1"


def test_validate_event_envelope_accepts_realtime_message_type_and_trace_chain() -> None:
    normalized = validate_event_envelope(
        "brain.workflow.run.updated",
        {
            "event_name": "brain.workflow.run.updated",
            "message_type": MESSAGE_TYPE_REALTIME,
            "aggregate": {"type": "workflow_run", "id": "run-1"},
            "trace": {
                "trace_id": "trace-1",
                "causation_id": "evt-cause-2",
                "correlation_id": "corr-2",
            },
            "payload": {"run_id": "run-1"},
        },
    )

    assert normalized["message_type"] == MESSAGE_TYPE_REALTIME
    assert normalized["trace"]["causation_id"] == "evt-cause-2"
    assert normalized["trace"]["correlation_id"] == "corr-2"


def test_normalize_event_envelope_keeps_legacy_agent_protocol_payload_unchanged() -> None:
    payload = {
        "spec_version": "agentbus.v1",
        "message_id": "msg-1",
        "message_type": "command",
        "message_name": "agent.execution.request",
        "request_id": "req-1",
        "payload": {"run_id": "run-1"},
    }

    assert is_legacy_agent_protocol_envelope(payload) is True
    assert normalize_event_envelope("agent.execution.command", payload) == payload


def test_summarize_payload_for_bus_replaces_full_run_with_summary_and_redacts_sensitive_fields() -> None:
    summarized = summarize_payload_for_bus(
        {
            "type": "workflow_run.updated",
            "workflow_id": "workflow-1",
            "run": {
                "id": "run-1",
                "workflow_id": "workflow-1",
                "workflow_name": "主脑工作流",
                "task_id": "task-1",
                "status": "running",
                "current_stage": "执行中",
                "nodes": [{"id": "node-1", "status": "running"}],
                "logs": [{"id": "log-1", "message": "very long" * 80}],
                "dispatch_context": {
                    "type": "message",
                    "manager_packet": {"secret": "should-not-leak"},
                    "memory": {"raw": "secret-memory"},
                    "audit": {"trace": "secret-audit"},
                },
            },
        }
    )

    run = summarized["run"]
    assert run["summary_only"] is True
    assert run["summary_kind"] == "workflow_run"
    assert run["id"] == "run-1"
    assert run["node_count"] == 1
    assert run["log_count"] == 1
    assert "nodes" not in run
    assert "logs" not in run
    assert run["dispatch_context"]["manager_packet"]["redacted"] is True
    assert run["dispatch_context"]["memory"]["redacted"] is True
    assert run["dispatch_context"]["audit"]["redacted"] is True


def test_summarize_payload_for_bus_enforces_payload_size_limit() -> None:
    summarized = summarize_payload_for_bus(
        {
            "type": "workflow_run.snapshot",
            "items": [
                {
                    "id": f"run-{index}",
                    "workflow_id": "workflow-1",
                    "workflow_name": "工作流",
                    "status": "running",
                    "current_stage": "执行中",
                    "nodes": [{"id": f"node-{node}", "message": "x" * 1000} for node in range(20)],
                    "logs": [{"id": f"log-{log}", "message": "y" * 2000} for log in range(20)],
                }
                for index in range(20)
            ],
            "audit": {"raw": "z" * 20000},
        }
    )

    assert summarized["audit"]["redacted"] is True
    assert len(json.dumps(summarized, ensure_ascii=False).encode("utf-8")) <= BUS_PAYLOAD_MAX_BYTES
