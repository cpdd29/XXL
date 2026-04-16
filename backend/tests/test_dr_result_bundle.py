from __future__ import annotations

import json
from pathlib import Path

import scripts.package_dr_result_bundle as bundle_module
from scripts.package_dr_result_bundle import run_package_dr_result_bundle


def _write_report_fixture(tmp_path: Path, prefix: str, payload: dict[str, object]) -> Path:
    path = tmp_path / f"{prefix}_fixture.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(f"# {prefix}\n", encoding="utf-8")
    return path


def _build_four_reports(tmp_path: Path, *, drill_kind: str = "formal") -> dict[str, str]:
    precheck_report = _write_report_fixture(
        tmp_path,
        "dr_precheck",
        {
            "evidence": {"drill_kind": drill_kind, "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    prepare_report = _write_report_fixture(
        tmp_path,
        "failover_prepare",
        {
            "evidence": {"drill_kind": drill_kind, "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 5},
        },
    )
    post_verify_report = _write_report_fixture(
        tmp_path,
        "post_failover_verify",
        {
            "evidence": {"drill_kind": drill_kind, "evidence_level": "full", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    recovery_report = _write_report_fixture(
        tmp_path,
        "external_tentacle_recovery",
        {
            "evidence": {"drill_kind": drill_kind, "evidence_level": "full", "operator_notes": ""},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    return {
        "precheck_report": str(precheck_report),
        "prepare_report": str(prepare_report),
        "post_verify_report": str(post_verify_report),
        "recovery_report": str(recovery_report),
    }


def _stage_payload(tmp_path: Path, prefix: str, *, ok: bool = True, failed_steps: list[str] | None = None) -> dict[str, object]:
    report_path = _write_report_fixture(
        tmp_path,
        prefix,
        {
            "evidence": {"drill_kind": "formal", "evidence_level": "full", "operator_notes": ""},
            "measurements": {"rto_seconds": 120.0, "estimated_rpo_seconds": 0.0},
            "gate_stats": {"failed": 0, "manual_intervention": 0},
        },
    )
    return {
        "ok": ok,
        "status": "passed" if ok else "failed",
        "failed_steps": list(failed_steps or []),
        "artifacts": {
            "json_report": str(report_path),
            "markdown_report": str(report_path.with_suffix(".md")),
        },
    }


def test_run_package_dr_result_bundle_packages_formal_reports(tmp_path: Path) -> None:
    reports = _build_four_reports(tmp_path, drill_kind="formal")
    archive_dir = tmp_path / "archives"

    payload = run_package_dr_result_bundle(
        **reports,
        exercise_id="dr-formal-001",
        archive_dir=str(archive_dir),
        operator_notes="formal drill passed",
        write_report=True,
    )

    assert payload["ok"] is True
    assert payload["status"] == "packaged"
    assert payload["required_drill_kind"] == "formal"
    assert payload["exercise_id"] == "dr-formal-001"
    assert payload["bundle"]["report_count"] == 4
    assert payload["gate"]["failed_steps"] == []
    assert payload["archive_manifest"]["archive_complete"] is True
    assert len(payload["archive_manifest"]["items"]) >= 12

    artifacts = payload["artifacts"]
    assert Path(artifacts["json_report"]).exists()
    assert Path(artifacts["markdown_report"]).exists()
    archive_artifacts = payload["archive_manifest"]["artifacts"]
    assert Path(archive_artifacts["json_report"]).exists()
    assert Path(archive_artifacts["markdown_report"]).exists()
    bundle_artifacts = payload["archive_manifest"]["bundle_artifacts"]
    assert Path(bundle_artifacts["json_report"]).exists()
    assert Path(bundle_artifacts["markdown_report"]).exists()


def test_run_package_dr_result_bundle_blocks_smoke_by_default(tmp_path: Path) -> None:
    reports = _build_four_reports(tmp_path, drill_kind="smoke")
    archive_dir = tmp_path / "archives"

    payload = run_package_dr_result_bundle(
        **reports,
        exercise_id="dr-smoke-001",
        archive_dir=str(archive_dir),
        write_report=False,
    )

    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert "formal_drill_kind_required" in payload["gate"]["failed_steps"]
    assert payload["gate"]["report_drill_kinds"]["precheck"] == "smoke"


def test_run_package_dr_result_bundle_persists_operator_metadata(tmp_path: Path) -> None:
    reports = _build_four_reports(tmp_path, drill_kind="formal")
    archive_dir = tmp_path / "archives"

    payload = run_package_dr_result_bundle(
        **reports,
        exercise_id="exercise-meta-20260415",
        archive_dir=str(archive_dir),
        operator_notes="operator: alice, observer: bob",
        write_report=True,
    )

    assert payload["operator_notes"] == "operator: alice, observer: bob"
    assert payload["exercise_id"] == "exercise-meta-20260415"
    assert payload["archive_manifest"]["archive_dir"].endswith("exercise-meta-20260415")

    manifest_json = Path(payload["archive_manifest"]["artifacts"]["json_report"])
    manifest_payload = json.loads(manifest_json.read_text(encoding="utf-8"))
    assert manifest_payload["archive_complete"] is True
    assert len(manifest_payload["items"]) >= 12


def test_run_package_dr_result_bundle_can_orchestrate_formal_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bundle_module, "run_dr_precheck", lambda **kwargs: _stage_payload(tmp_path, "dr_precheck"))
    monkeypatch.setattr(bundle_module, "run_failover_prepare", lambda **kwargs: _stage_payload(tmp_path, "failover_prepare"))
    monkeypatch.setattr(
        bundle_module,
        "run_post_failover_verify",
        lambda **kwargs: _stage_payload(tmp_path, "post_failover_verify"),
    )
    monkeypatch.setattr(
        bundle_module,
        "run_external_tentacle_recovery",
        lambda **kwargs: _stage_payload(tmp_path, "external_tentacle_recovery"),
    )

    payload = run_package_dr_result_bundle(
        orchestrate=True,
        exercise_id="dr-orchestrated-001",
        archive_dir=str(tmp_path / "archives"),
        write_report=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "packaged"
    assert payload["bundle"]["report_count"] == 4
    assert payload["orchestration"]["ok"] is True
    assert [item["key"] for item in payload["orchestration"]["stages"]] == [
        "precheck",
        "prepare",
        "post_verify",
        "recovery",
    ]
    assert all(item["source"] == "generated" for item in payload["orchestration"]["stages"])


def test_run_package_dr_result_bundle_blocks_when_orchestrated_stage_fails(monkeypatch, tmp_path: Path) -> None:
    call_state = {"prepare_called": False}

    monkeypatch.setattr(
        bundle_module,
        "run_dr_precheck",
        lambda **kwargs: _stage_payload(tmp_path, "dr_precheck", ok=False, failed_steps=["runbook_present"]),
    )

    def _unexpected_prepare(**kwargs):
        call_state["prepare_called"] = True
        return _stage_payload(tmp_path, "failover_prepare")

    monkeypatch.setattr(bundle_module, "run_failover_prepare", _unexpected_prepare)

    payload = run_package_dr_result_bundle(
        orchestrate=True,
        exercise_id="dr-orchestrated-failed",
        archive_dir=str(tmp_path / "archives"),
        write_report=False,
    )

    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert payload["orchestration"]["failed_stage"] == "precheck"
    assert payload["gate"]["failed_steps"] == ["orchestration:precheck"]
    assert call_state["prepare_called"] is False
