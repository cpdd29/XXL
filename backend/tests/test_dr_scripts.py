from __future__ import annotations

import json
from pathlib import Path

import scripts.dr_common as dr_common_module
from scripts.dr_precheck import run_dr_precheck
from scripts.dr_result_gate import run_dr_result_gate
from scripts.external_tentacle_recovery import run_external_tentacle_recovery
from scripts.failover_prepare import run_failover_prepare
from scripts.post_failover_verify import run_post_failover_verify


SAMPLE_TRUTH_SOURCES = {
    "captured_at": "2026-04-15T00:00:00+00:00",
    "tasks": {"total": 3, "sample_ids": ["task-1"], "latest_created_at": "2026-04-15T00:00:00+00:00"},
    "runs": {"total": 2, "sample_ids": ["run-1"], "latest_updated_at": "2026-04-15T00:00:01+00:00"},
    "audit": {"total": 4, "sample_ids": ["audit-1"], "latest_timestamp": "2026-04-15T00:00:02+00:00"},
    "security": {
        "summary": {"active_rules": 5},
        "rule_total": 5,
        "recent_incident_ids": ["incident-1"],
        "latest_incident_at": "2026-04-15T00:00:03+00:00",
    },
}

SAMPLE_EXTERNAL_MANIFEST = {
    "captured_at": "2026-04-15T00:00:10+00:00",
    "summary": {
        "agent_families": 1,
        "skill_families": 1,
        "agent_instances": 1,
        "skill_instances": 1,
        "routable_instances": 2,
        "offline_instances": 0,
        "open_circuits": 0,
        "stale_heartbeats": 0,
    },
    "stale_items": [],
    "agents": [{"family": "planner", "id": "planner-v1"}],
    "skills": [{"family": "search", "id": "search-v1"}],
}

SAMPLE_READINESS = {
    "environment": "test",
    "persistence_enabled": True,
    "nats_connected": False,
    "fallback_event_bus_available": True,
    "runbook_exists": True,
    "result_template_exists": True,
    "warnings": [],
}

SAMPLE_STEP_PLAN = [
    {"order": index + 1, "step_key": f"step_{index + 1}", "title": f"Step {index + 1}"}
    for index in range(9)
]


def _write_baseline_report(tmp_path: Path) -> Path:
    path = tmp_path / "failover_prepare_fixture.json"
    path.write_text(
        json.dumps(
            {
                "timeline": {"failover_started_at": "2026-04-15T00:00:00+00:00"},
                "baseline": {
                    "truth_sources": SAMPLE_TRUTH_SOURCES,
                    "external_manifest": SAMPLE_EXTERNAL_MANIFEST,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _write_report_fixture(tmp_path: Path, prefix: str, payload: dict[str, object]) -> Path:
    path = tmp_path / f"{prefix}_fixture.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def test_run_dr_precheck_returns_ready_payload(monkeypatch) -> None:
    monkeypatch.setattr("scripts.dr_precheck.platform_readiness", lambda: dict(SAMPLE_READINESS))
    monkeypatch.setattr("scripts.dr_precheck.truth_source_snapshot", lambda: dict(SAMPLE_TRUTH_SOURCES))
    monkeypatch.setattr("scripts.dr_precheck.external_recovery_manifest", lambda: dict(SAMPLE_EXTERNAL_MANIFEST))
    monkeypatch.setattr("scripts.dr_precheck.runbook_step_plan", lambda: list(SAMPLE_STEP_PLAN))

    payload = run_dr_precheck(write_report=False)

    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert len(payload["checks"]) == 6
    assert payload["gate_stats"]["failed"] == 0
    assert isinstance(payload["gate_stats"]["manual_intervention"], int)
    assert payload["baseline"]["truth_sources"]["tasks"]["total"] == 3


def test_run_failover_prepare_builds_standard_template(monkeypatch) -> None:
    monkeypatch.setattr("scripts.failover_prepare.platform_readiness", lambda: dict(SAMPLE_READINESS))
    monkeypatch.setattr("scripts.failover_prepare.truth_source_snapshot", lambda: dict(SAMPLE_TRUTH_SOURCES))
    monkeypatch.setattr("scripts.failover_prepare.external_recovery_manifest", lambda: dict(SAMPLE_EXTERNAL_MANIFEST))
    monkeypatch.setattr("scripts.failover_prepare.runbook_step_plan", lambda: list(SAMPLE_STEP_PLAN))
    monkeypatch.setattr("scripts.failover_prepare.utc_now_iso", lambda: "2026-04-15T00:00:30+00:00")

    payload = run_failover_prepare(write_report=False)

    assert payload["ok"] is True
    assert payload["status"] == "prepared"
    assert payload["gate_stats"]["failed"] == 0
    assert isinstance(payload["gate_stats"]["manual_intervention"], int)
    assert payload["timeline"]["failover_started_at"] == "2026-04-15T00:00:30+00:00"
    assert payload["baseline"]["external_manifest"]["summary"]["skill_instances"] == 1
    assert len(payload["step_plan"]) == 9


def test_run_post_failover_verify_compares_truth_sources(monkeypatch, tmp_path: Path) -> None:
    baseline_report = _write_baseline_report(tmp_path)
    monkeypatch.setattr("scripts.post_failover_verify.truth_source_snapshot", lambda: dict(SAMPLE_TRUTH_SOURCES))
    monkeypatch.setattr("scripts.post_failover_verify.platform_readiness", lambda: dict(SAMPLE_READINESS))
    monkeypatch.setattr(
        "scripts.post_failover_verify.compare_truth_source_snapshots",
        lambda baseline, current: {
            "ok": True,
            "checks": [{"key": "truth_source_continuity", "ok": True, "details": {"baseline": baseline, "current": current}}],
            "failed_steps": [],
            "estimated_rpo_seconds": 0.0,
            "estimated_lost_records": 0,
        },
    )

    payload = run_post_failover_verify(
        baseline_report=str(baseline_report),
        verified_at="2026-04-15T00:05:00+00:00",
        write_report=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["measurements"]["rto_seconds"] == 300.0
    assert payload["measurements"]["estimated_lost_records"] == 0
    assert payload["gate_stats"] == {"failed": 0, "manual_intervention": 0}
    assert payload["baseline_report"] == str(baseline_report)


def test_run_external_tentacle_recovery_compares_manifest(monkeypatch, tmp_path: Path) -> None:
    baseline_report = _write_baseline_report(tmp_path)
    monkeypatch.setattr(
        "scripts.external_tentacle_recovery.external_recovery_manifest",
        lambda: dict(SAMPLE_EXTERNAL_MANIFEST),
    )
    monkeypatch.setattr(
        "scripts.external_tentacle_recovery.compare_external_manifests",
        lambda baseline, current: {
            "ok": True,
            "checks": [{"key": "family_recovered", "ok": True, "details": {"baseline": baseline, "current": current}}],
            "failed_steps": [],
            "missing_agent_families": [],
            "missing_skill_families": [],
        },
    )

    payload = run_external_tentacle_recovery(
        baseline_report=str(baseline_report),
        verified_at="2026-04-15T00:06:00+00:00",
        write_report=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["measurements"]["external_recovery_rto_seconds"] == 360.0
    assert payload["tentacle_recovery_scope"] == {"agent": True, "skill": True, "mcp": False}
    assert payload["gate_stats"] == {"failed": 0, "manual_intervention": 0}
    assert payload["post_state"]["external_manifest"]["summary"]["agent_instances"] == 1


def test_run_dr_result_gate_passes_with_complete_reports(tmp_path: Path) -> None:
    precheck_report = _write_report_fixture(
        tmp_path,
        "dr_precheck",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    prepare_report = _write_report_fixture(
        tmp_path,
        "failover_prepare",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    post_verify_report = _write_report_fixture(
        tmp_path,
        "post_failover_verify",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    recovery_report = _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 1, "manual_intervention": 0},
        },
    )

    payload = run_dr_result_gate(
        precheck_report=str(precheck_report),
        prepare_report=str(prepare_report),
        post_verify_report=str(post_verify_report),
        recovery_report=str(recovery_report),
        write_report=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["failed_steps"] == []
    assert payload["gate_stats"] == {"failed": 1, "manual_intervention": 10}


def test_run_dr_result_gate_fails_on_missing_required_fields(tmp_path: Path) -> None:
    prepare_report = _write_report_fixture(
        tmp_path,
        "failover_prepare",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    post_verify_report = _write_report_fixture(
        tmp_path,
        "post_failover_verify",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    recovery_report = _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )

    payload = run_dr_result_gate(
        precheck_report=str(tmp_path / "missing_precheck.json"),
        prepare_report=str(prepare_report),
        post_verify_report=str(post_verify_report),
        recovery_report=str(recovery_report),
        write_report=False,
    )

    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "required_reports_present" in payload["failed_steps"]
    assert "rto_rpo_fields_present" in payload["failed_steps"]
    assert "failed_manual_intervention_stats_present" in payload["failed_steps"]


def test_run_dr_result_gate_blocks_smoke_by_default(tmp_path: Path) -> None:
    precheck_report = _write_report_fixture(
        tmp_path,
        "dr_precheck",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    prepare_report = _write_report_fixture(
        tmp_path,
        "failover_prepare",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    post_verify_report = _write_report_fixture(
        tmp_path,
        "post_failover_verify",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    recovery_report = _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )

    payload = run_dr_result_gate(
        precheck_report=str(precheck_report),
        prepare_report=str(prepare_report),
        post_verify_report=str(post_verify_report),
        recovery_report=str(recovery_report),
        write_report=False,
    )

    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "formal_drill_kind_required" in payload["failed_steps"]


def test_run_dr_result_gate_allows_smoke_when_allow_smoke_enabled(tmp_path: Path) -> None:
    precheck_report = _write_report_fixture(
        tmp_path,
        "dr_precheck",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    prepare_report = _write_report_fixture(
        tmp_path,
        "failover_prepare",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    post_verify_report = _write_report_fixture(
        tmp_path,
        "post_failover_verify",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    recovery_report = _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )

    payload = run_dr_result_gate(
        precheck_report=str(precheck_report),
        prepare_report=str(prepare_report),
        post_verify_report=str(post_verify_report),
        recovery_report=str(recovery_report),
        allow_smoke=True,
        write_report=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["failed_steps"] == []


def test_find_latest_report_prefers_newer_timestamp_over_smoke_name(monkeypatch, tmp_path: Path) -> None:
    smoke_report = tmp_path / "dr_precheck_smoke_20260414_184336.json"
    smoke_report.write_text("{}", encoding="utf-8")
    newer_formal_report = tmp_path / "dr_precheck_20260415_052134.json"
    newer_formal_report.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(dr_common_module, "REPORTS_ROOT", tmp_path)

    resolved = dr_common_module.find_latest_report("dr_precheck")

    assert resolved == newer_formal_report


def test_run_dr_result_gate_uses_newer_formal_reports_when_smoke_reports_also_exist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(dr_common_module, "REPORTS_ROOT", tmp_path)

    _write_report_fixture(
        tmp_path,
        "dr_precheck_smoke_20260414_184336",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
        },
    )
    _write_report_fixture(
        tmp_path,
        "failover_prepare_smoke_20260414_184336",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
        },
    )
    _write_report_fixture(
        tmp_path,
        "post_failover_verify_smoke_20260414_184355",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
        },
    )
    _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery_smoke_20260414_184355",
        {
            "evidence": {"drill_kind": "smoke", "evidence_level": "smoke", "operator_notes": ""},
        },
    )

    _write_report_fixture(
        tmp_path,
        "dr_precheck_20260415_052134",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "precheck", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    _write_report_fixture(
        tmp_path,
        "failover_prepare_20260415_052134",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    _write_report_fixture(
        tmp_path,
        "post_failover_verify_20260415_052234",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery_20260415_052234",
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )

    payload = run_dr_result_gate(write_report=False)

    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["failed_steps"] == []
    assert payload["report_drill_kinds"] == {
        "precheck": "formal",
        "prepare": "formal",
        "post_verify": "formal",
        "recovery": "formal",
    }
