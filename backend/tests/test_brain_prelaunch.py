from __future__ import annotations

from pathlib import Path

import scripts.check_brain_prelaunch as brain_prelaunch_module
from scripts.check_brain_prelaunch import run_brain_prelaunch_check


def test_brain_prelaunch_reports_degraded_startable_when_startup_is_green(monkeypatch) -> None:
    monkeypatch.setattr(
        brain_prelaunch_module,
        "platform_readiness",
        lambda: {
            "persistence_enabled": False,
            "nats_connected": False,
            "fallback_event_bus_available": True,
            "runbook_exists": True,
            "result_template_exists": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": False,
            "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
            "uses_default_url": True,
            "is_localhost": True,
            "persistence_enabled": False,
            "warnings": ["database_url 仍为默认值。"],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_contract_check",
        lambda: {
            "ok": False,
            "nats_url": "nats://localhost:4222",
            "uses_default_url": True,
            "is_localhost": True,
            "connected": False,
            "fallback_mode": True,
            "handler_registrations": 0,
            "subscription_registrations": 0,
            "warnings": ["NATS 未连接，当前处于降级/回退路径。"],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_startup_check",
        lambda: {
            "ok": True,
            "checks": {
                "dispatch_runtime": {"mode": "fallback"},
                "workflow_execution_runtime": {"mode": "fallback"},
                "agent_execution_runtime": {"mode": "fallback"},
                "multi_instance_guard": {
                    "summary": {"strict_multi_instance_ready": False},
                },
            },
        },
    )
    monkeypatch.setattr(brain_prelaunch_module, "run_preflight", lambda _repo_root, **kwargs: {"ok": True})
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_entrypoint_check",
        lambda *, repo_root=None: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_control_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_audit_persistence_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_external_ingress_bypass_check",
        lambda *, repo_root=None: {
            "ok": True,
            "routes": [],
            "failed_public_routes": [],
            "manual_review_required": [],
            "summary": {"failed_public_routes": 0},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_dr_result_gate",
        lambda **kwargs: {"ok": False, "failed_steps": ["required_reports_present"]},
    )
    monkeypatch.setattr(
        brain_prelaunch_module.nats_event_bus,
        "connection_snapshot",
        lambda: {"connected": False, "fallback_mode": True},
    )

    payload = run_brain_prelaunch_check(repo_root=Path("/tmp/repo"))

    assert payload["ok"] is True
    assert payload["startup_ready"] is True
    assert payload["production_ready"] is False
    assert payload["status"] == "degraded_startable"
    assert len(payload["strict_blockers"]) >= 3
    assert payload["checks"]["persistence_contract"]["ok"] is False
    assert payload["checks"]["nats_contract"]["ok"] is False
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["ran"] is False
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["skipped"] is True
    assert payload["checks"]["nats_roundtrip"]["ran"] is False
    assert payload["checks"]["nats_roundtrip"]["skipped"] is True
    assert payload["checks"]["security_controls"]["ok"] is True
    assert payload["checks"]["security_entrypoints"]["ok"] is True
    assert payload["checks"]["security_audit_persistence"]["ok"] is True
    assert payload["checks"]["external_ingress_bypass"]["ok"] is True
    assert "persistent_truth_source_ready" in payload["summary"]["strict_failed_keys"]


def test_brain_prelaunch_reports_production_ready_when_all_strict_gates_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        brain_prelaunch_module,
        "platform_readiness",
        lambda: {
            "persistence_enabled": True,
            "nats_connected": True,
            "fallback_event_bus_available": True,
            "runbook_exists": True,
            "result_template_exists": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": True,
            "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot",
            "uses_default_url": False,
            "is_localhost": False,
            "persistence_enabled": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_contract_check",
        lambda: {
            "ok": True,
            "nats_url": "nats://nats.prod.internal:4222",
            "uses_default_url": False,
            "is_localhost": False,
            "connected": True,
            "fallback_mode": False,
            "handler_registrations": 4,
            "subscription_registrations": 4,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_startup_check",
        lambda: {
            "ok": True,
            "checks": {
                "dispatch_runtime": {"mode": "persistent"},
                "workflow_execution_runtime": {"mode": "persistent"},
                "agent_execution_runtime": {"mode": "persistent"},
                "multi_instance_guard": {
                    "summary": {"strict_multi_instance_ready": True},
                },
            },
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_runtime_pg_acceptance_check",
        lambda *, database_url: {
            "ok": True,
            "database_url": database_url,
            "checks": {"reopen_visibility": {"ok": True}},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_roundtrip_check",
        lambda *, nats_url: {
            "ok": True,
            "nats_url": nats_url,
            "phases": {"roundtrip": {"ok": True}},
        },
    )
    monkeypatch.setattr(brain_prelaunch_module, "run_preflight", lambda _repo_root, **kwargs: {"ok": True})
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_entrypoint_check",
        lambda *, repo_root=None: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_control_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_audit_persistence_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_external_ingress_bypass_check",
        lambda *, repo_root=None: {
            "ok": True,
            "routes": [],
            "failed_public_routes": [],
            "manual_review_required": [],
            "summary": {"failed_public_routes": 0},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_dr_result_gate",
        lambda **kwargs: {"ok": True, "failed_steps": []},
    )
    monkeypatch.setattr(
        brain_prelaunch_module.nats_event_bus,
        "connection_snapshot",
        lambda: {"connected": True, "fallback_mode": False},
    )

    payload = run_brain_prelaunch_check(repo_root=Path("/tmp/repo"))

    assert payload["ok"] is True
    assert payload["production_ready"] is True
    assert payload["status"] == "production_ready"
    assert payload["strict_blockers"] == []
    assert payload["checks"]["persistence_contract"]["ok"] is True
    assert payload["checks"]["nats_contract"]["ok"] is True
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["ran"] is True
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["ok"] is True
    assert payload["checks"]["nats_roundtrip"]["ran"] is True
    assert payload["checks"]["nats_roundtrip"]["ok"] is True
    assert payload["summary"]["strict_failed"] == 0
    assert payload["summary"]["strict_failed_keys"] == []
    assert payload["checks"]["security_controls"]["ok"] is True
    assert payload["checks"]["security_entrypoints"]["ok"] is True
    assert payload["checks"]["security_audit_persistence"]["ok"] is True
    assert payload["checks"]["external_ingress_bypass"]["ok"] is True


def test_brain_prelaunch_normalizes_platform_readiness_from_contracts(monkeypatch) -> None:
    monkeypatch.setattr(
        brain_prelaunch_module,
        "platform_readiness",
        lambda: {
            "persistence_enabled": False,
            "nats_connected": False,
            "fallback_event_bus_available": True,
            "runbook_exists": True,
            "result_template_exists": True,
            "warnings": [
                "当前未连接正式持久层，真源校验将基于内存/降级模式。",
                "NATS 当前未建立连接，将以 in-process fallback 视为可降级运行。",
            ],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": True,
            "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot",
            "uses_default_url": False,
            "is_localhost": False,
            "persistence_enabled": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_contract_check",
        lambda: {
            "ok": True,
            "nats_url": "nats://nats.prod.internal:4222",
            "uses_default_url": False,
            "is_localhost": False,
            "connected": True,
            "fallback_mode": False,
            "handler_registrations": 4,
            "subscription_registrations": 4,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_startup_check",
        lambda: {
            "ok": True,
            "checks": {
                "dispatch_runtime": {"mode": "persistent"},
                "workflow_execution_runtime": {"mode": "persistent"},
                "agent_execution_runtime": {"mode": "persistent"},
                "multi_instance_guard": {"summary": {"strict_multi_instance_ready": True}},
            },
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_runtime_pg_acceptance_check",
        lambda *, database_url: {"ok": True, "database_url": database_url, "checks": {}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_roundtrip_check",
        lambda *, nats_url: {"ok": True, "nats_url": nats_url, "phases": {}},
    )
    monkeypatch.setattr(brain_prelaunch_module, "run_preflight", lambda _repo_root, **kwargs: {"ok": True})
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_entrypoint_check",
        lambda *, repo_root=None: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_control_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_audit_persistence_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_external_ingress_bypass_check",
        lambda *, repo_root=None: {
            "ok": True,
            "routes": [],
            "failed_public_routes": [],
            "manual_review_required": [],
            "summary": {"failed_public_routes": 0},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_dr_result_gate",
        lambda **kwargs: {"ok": True, "failed_steps": []},
    )
    monkeypatch.setattr(
        brain_prelaunch_module.nats_event_bus,
        "connection_snapshot",
        lambda: {"connected": True, "fallback_mode": False},
    )

    payload = run_brain_prelaunch_check(repo_root=Path("/tmp/repo"))

    assert payload["checks"]["platform_readiness"]["persistence_enabled"] is True
    assert payload["checks"]["platform_readiness"]["nats_connected"] is True
    assert payload["checks"]["platform_readiness"]["warnings"] == []


def test_brain_prelaunch_reports_blocked_when_scheduler_startup_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        brain_prelaunch_module,
        "platform_readiness",
        lambda: {
            "persistence_enabled": False,
            "nats_connected": False,
            "fallback_event_bus_available": True,
            "runbook_exists": True,
            "result_template_exists": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": False,
            "database_url": "postgresql+psycopg://workbot:workbot@localhost:5432/workbot",
            "uses_default_url": True,
            "is_localhost": True,
            "persistence_enabled": False,
            "warnings": ["持久化初始化未通过。"],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_contract_check",
        lambda: {
            "ok": False,
            "nats_url": "http://localhost:4222",
            "uses_default_url": False,
            "is_localhost": True,
            "connected": False,
            "fallback_mode": True,
            "handler_registrations": 0,
            "subscription_registrations": 0,
            "warnings": ["nats_url scheme 非预期: http"],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_startup_check",
        lambda: {
            "ok": False,
            "checks": {
                "dispatch_runtime": {"mode": "fallback"},
                "workflow_execution_runtime": {"mode": "fallback"},
                "agent_execution_runtime": {"mode": "fallback"},
                "multi_instance_guard": {
                    "summary": {"strict_multi_instance_ready": False},
                },
            },
        },
    )
    monkeypatch.setattr(brain_prelaunch_module, "run_preflight", lambda _repo_root, **kwargs: {"ok": False})
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_entrypoint_check",
        lambda *, repo_root=None: {"ok": False, "checks": [], "summary": {"failed_checks": 1}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_control_check",
        lambda: {"ok": False, "checks": [], "summary": {"failed_checks": 1}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_audit_persistence_check",
        lambda: {"ok": False, "checks": [], "summary": {"failed_checks": 1}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_external_ingress_bypass_check",
        lambda *, repo_root=None: {
            "ok": False,
            "routes": [],
            "failed_public_routes": [{"path": "/unsafe"}],
            "manual_review_required": [],
            "summary": {"failed_public_routes": 1},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_dr_result_gate",
        lambda **kwargs: {"ok": False, "failed_steps": ["required_reports_present"]},
    )
    monkeypatch.setattr(
        brain_prelaunch_module.nats_event_bus,
        "connection_snapshot",
        lambda: {"connected": False, "fallback_mode": True},
    )

    payload = run_brain_prelaunch_check(repo_root=Path("/tmp/repo"))

    assert payload["ok"] is False
    assert payload["startup_ready"] is False
    assert payload["production_ready"] is False
    assert payload["status"] == "blocked"
    assert payload["checks"]["persistence_contract"]["ok"] is False
    assert payload["checks"]["nats_contract"]["ok"] is False
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["ran"] is False
    assert payload["checks"]["nats_roundtrip"]["ran"] is False
    assert payload["checks"]["security_controls"]["ok"] is False
    assert payload["checks"]["security_entrypoints"]["ok"] is False
    assert payload["checks"]["security_audit_persistence"]["ok"] is False
    assert payload["checks"]["external_ingress_bypass"]["ok"] is False


def test_brain_prelaunch_blocks_when_real_nats_roundtrip_acceptance_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        brain_prelaunch_module,
        "platform_readiness",
        lambda: {
            "persistence_enabled": True,
            "nats_connected": True,
            "fallback_event_bus_available": False,
            "runbook_exists": True,
            "result_template_exists": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": True,
            "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot",
            "uses_default_url": False,
            "is_localhost": False,
            "persistence_enabled": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_contract_check",
        lambda: {
            "ok": True,
            "nats_url": "nats://nats.prod.internal:4222",
            "uses_default_url": False,
            "is_localhost": False,
            "connected": True,
            "fallback_mode": False,
            "handler_registrations": 4,
            "subscription_registrations": 4,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_startup_check",
        lambda: {
            "ok": True,
            "checks": {
                "dispatch_runtime": {"mode": "persistent"},
                "workflow_execution_runtime": {"mode": "persistent"},
                "agent_execution_runtime": {"mode": "persistent"},
                "multi_instance_guard": {
                    "summary": {"strict_multi_instance_ready": True},
                },
            },
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_runtime_pg_acceptance_check",
        lambda *, database_url: {
            "ok": True,
            "database_url": database_url,
            "checks": {"reopen_visibility": {"ok": True}},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_roundtrip_check",
        lambda *, nats_url: {
            "ok": False,
            "nats_url": nats_url,
            "phases": {"dispatch_queue": {"ok": False}},
        },
    )
    monkeypatch.setattr(brain_prelaunch_module, "run_preflight", lambda _repo_root, **kwargs: {"ok": True})
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_entrypoint_check",
        lambda *, repo_root=None: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_control_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_audit_persistence_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_external_ingress_bypass_check",
        lambda *, repo_root=None: {
            "ok": True,
            "routes": [],
            "failed_public_routes": [],
            "manual_review_required": [],
            "summary": {"failed_public_routes": 0},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_dr_result_gate",
        lambda **kwargs: {"ok": True, "failed_steps": []},
    )
    monkeypatch.setattr(
        brain_prelaunch_module.nats_event_bus,
        "connection_snapshot",
        lambda: {"connected": True, "fallback_mode": False},
    )

    payload = run_brain_prelaunch_check(repo_root=Path("/tmp/repo"))

    assert payload["ok"] is True
    assert payload["startup_ready"] is True
    assert payload["production_ready"] is False
    assert payload["status"] == "degraded_startable"
    assert payload["checks"]["nats_roundtrip"]["ran"] is True
    assert payload["checks"]["nats_roundtrip"]["ok"] is False
    assert "nats_transport_ready" in payload["summary"]["strict_failed_keys"]


def test_brain_prelaunch_blocks_when_real_scheduler_pg_acceptance_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        brain_prelaunch_module,
        "platform_readiness",
        lambda: {
            "persistence_enabled": True,
            "nats_connected": True,
            "fallback_event_bus_available": False,
            "runbook_exists": True,
            "result_template_exists": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": True,
            "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot",
            "uses_default_url": False,
            "is_localhost": False,
            "persistence_enabled": True,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_contract_check",
        lambda: {
            "ok": True,
            "nats_url": "nats://nats.prod.internal:4222",
            "uses_default_url": False,
            "is_localhost": False,
            "connected": True,
            "fallback_mode": False,
            "handler_registrations": 4,
            "subscription_registrations": 4,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_startup_check",
        lambda: {
            "ok": True,
            "checks": {
                "dispatch_runtime": {"mode": "persistent"},
                "workflow_execution_runtime": {"mode": "persistent"},
                "agent_execution_runtime": {"mode": "persistent"},
                "multi_instance_guard": {
                    "summary": {"strict_multi_instance_ready": True},
                },
            },
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_scheduler_runtime_pg_acceptance_check",
        lambda *, database_url: {
            "ok": False,
            "database_url": database_url,
            "checks": {"dispatch_job_claim_cycle": {"ok": False}},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_nats_roundtrip_check",
        lambda *, nats_url: {
            "ok": True,
            "nats_url": nats_url,
            "phases": {"roundtrip": {"ok": True}},
        },
    )
    monkeypatch.setattr(brain_prelaunch_module, "run_preflight", lambda _repo_root, **kwargs: {"ok": True})
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_entrypoint_check",
        lambda *, repo_root=None: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_control_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_security_audit_persistence_check",
        lambda: {"ok": True, "checks": [], "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_external_ingress_bypass_check",
        lambda *, repo_root=None: {
            "ok": True,
            "routes": [],
            "failed_public_routes": [],
            "manual_review_required": [],
            "summary": {"failed_public_routes": 0},
        },
    )
    monkeypatch.setattr(
        brain_prelaunch_module,
        "run_dr_result_gate",
        lambda **kwargs: {"ok": True, "failed_steps": []},
    )
    monkeypatch.setattr(
        brain_prelaunch_module.nats_event_bus,
        "connection_snapshot",
        lambda: {"connected": True, "fallback_mode": False},
    )

    payload = run_brain_prelaunch_check(repo_root=Path("/tmp/repo"))

    assert payload["ok"] is True
    assert payload["startup_ready"] is True
    assert payload["production_ready"] is False
    assert payload["status"] == "degraded_startable"
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["ran"] is True
    assert payload["checks"]["scheduler_runtime_pg_acceptance"]["ok"] is False
    assert "scheduler_multi_instance_ready" in payload["summary"]["strict_failed_keys"]
    assert "scheduler_runtime_persistent" in payload["summary"]["strict_failed_keys"]
