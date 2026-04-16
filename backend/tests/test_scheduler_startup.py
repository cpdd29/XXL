from __future__ import annotations

from types import SimpleNamespace

import scripts.check_scheduler_startup as scheduler_startup_module
from scripts.check_scheduler_startup import run_check


def test_scheduler_startup_accepts_fallback_mode(monkeypatch) -> None:
    dummy_persistence = SimpleNamespace(enabled=False)
    monkeypatch.setattr(scheduler_startup_module, "persistence_service", dummy_persistence)
    monkeypatch.setattr(
        scheduler_startup_module,
        "run_persistence_contract_check",
        lambda: {"persistence_enabled": False, "ok": False},
    )
    monkeypatch.setattr(
        scheduler_startup_module,
        "run_nats_contract_check",
        lambda: {"connected": False, "ok": False, "fallback_mode": True},
    )
    monkeypatch.setattr(
        scheduler_startup_module,
        "platform_readiness",
        lambda: {"warnings": [], "persistence_enabled": False, "nats_connected": False},
    )

    payload = run_check()

    assert payload["ok"] is True
    assert payload["checks"]["dispatch_runtime"]["mode"] == "fallback"
    assert payload["checks"]["workflow_execution_runtime"]["mode"] == "fallback"
    assert payload["checks"]["agent_execution_runtime"]["mode"] == "fallback"
    assert payload["checks"]["multi_instance_guard"]["mode"] == "degraded"


def test_scheduler_startup_flags_missing_claim_interfaces(monkeypatch) -> None:
    dummy_persistence = SimpleNamespace(
        enabled=True,
        claim_due_workflow_dispatch_jobs=lambda **_: [],
        release_workflow_dispatch_job_claim=lambda *_, **__: {},
        list_workflow_dispatch_jobs=lambda: [],
    )
    monkeypatch.setattr(scheduler_startup_module, "persistence_service", dummy_persistence)
    monkeypatch.setattr(
        scheduler_startup_module,
        "run_persistence_contract_check",
        lambda: {"persistence_enabled": True, "ok": True},
    )
    monkeypatch.setattr(
        scheduler_startup_module,
        "run_nats_contract_check",
        lambda: {"connected": True, "ok": True, "fallback_mode": False},
    )
    monkeypatch.setattr(
        scheduler_startup_module,
        "platform_readiness",
        lambda: {"warnings": [], "persistence_enabled": True, "nats_connected": True},
    )

    payload = run_check()

    assert payload["ok"] is False
    assert payload["checks"]["dispatch_runtime"]["ok"] is False
    assert "claim_due_workflow_runs" in payload["checks"]["dispatch_runtime"]["methods"]["missing"]


def test_scheduler_startup_current_repo_is_green() -> None:
    payload = run_check()

    assert payload["ok"] is True
    assert payload["checks"]["guard_runtime"]["ok"] is True


def test_scheduler_startup_normalizes_platform_readiness_from_contracts(monkeypatch) -> None:
    dummy_persistence = SimpleNamespace(enabled=False)
    monkeypatch.setattr(scheduler_startup_module, "persistence_service", dummy_persistence)
    monkeypatch.setattr(
        scheduler_startup_module,
        "run_persistence_contract_check",
        lambda: {"persistence_enabled": True, "ok": True},
    )
    monkeypatch.setattr(
        scheduler_startup_module,
        "run_nats_contract_check",
        lambda: {"connected": True, "ok": True, "fallback_mode": False},
    )
    monkeypatch.setattr(
        scheduler_startup_module,
        "platform_readiness",
        lambda: {
            "warnings": [
                "当前未连接正式持久层，真源校验将基于内存/降级模式。",
                "NATS 当前未建立连接，将以 in-process fallback 视为可降级运行。",
            ],
            "persistence_enabled": False,
            "nats_connected": False,
        },
    )

    payload = run_check()

    readiness = payload["checks"]["platform_readiness"]["summary"]
    assert readiness["persistence_enabled"] is True
    assert readiness["nats_connected"] is True
    assert readiness["warnings"] == []
