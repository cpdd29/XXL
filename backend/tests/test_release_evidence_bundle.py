from __future__ import annotations

from pathlib import Path

import scripts.package_release_evidence_bundle as bundle_module


def _write_report_artifacts(root: Path, prefix: str) -> dict[str, str]:
    json_path = root / f"{prefix}.json"
    md_path = root / f"{prefix}.md"
    json_path.write_text("{}", encoding="utf-8")
    md_path.write_text(f"# {prefix}\n", encoding="utf-8")
    return {
        "json_report": str(json_path),
        "markdown_report": str(md_path),
    }


def test_run_package_release_evidence_bundle_packages_component_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        bundle_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": True,
            "database_url": "postgresql+psycopg://db.prod.internal:5432/workbot",
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_preflight",
        lambda *_args, **_kwargs: {"ok": True, "status": "passed", "checks": {}},
    )
    monkeypatch.setattr(
        bundle_module,
        "run_brain_prelaunch_check",
        lambda **_kwargs: {
            "ok": True,
            "production_ready": True,
            "status": "production_ready",
            "summary": {"strict_failed_keys": []},
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "collect_compatibility_boundary_snapshot",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "checks": [],
            "summary": {"unexpected_growth": 0},
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_memory_governance_check",
        lambda: {"ok": True, "status": "passed", "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        bundle_module,
        "run_release_runtime_check",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "scenarios": {},
            "failed_steps": [],
            "artifacts": _write_report_artifacts(tmp_path, "runtime"),
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_monitoring_alerting_evidence",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "artifacts": _write_report_artifacts(tmp_path, "monitoring"),
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_collect_external_tentacle_evidence",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "artifacts": _write_report_artifacts(tmp_path, "external"),
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_collect_security_acceptance_evidence",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "artifacts": _write_report_artifacts(tmp_path, "security"),
        },
    )

    payload = bundle_module.run_package_release_evidence_bundle(
        output_dir=str(tmp_path / "bundle"),
        write_report=True,
    )

    assert payload["ok"] is True
    assert payload["status"] == "packaged"
    assert Path(payload["artifacts"]["json_report"]).exists()
    assert Path(payload["artifacts"]["markdown_report"]).exists()
    assert Path(payload["archive_manifest"]["artifacts"]["json_report"]).exists()
    assert Path(payload["archive_manifest"]["artifacts"]["markdown_report"]).exists()
    assert len(payload["archive_manifest"]["items"]) >= 10
    assert {item["key"] for item in payload["checks"]} >= {
        "release_preflight",
        "brain_prelaunch",
        "compatibility_boundaries",
        "memory_governance",
        "release_runtime",
        "monitoring_alerting",
        "external_tentacles",
        "security_acceptance",
    }


def test_run_package_release_evidence_bundle_marks_bundle_blocked_when_component_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bundle_module,
        "run_persistence_contract_check",
        lambda: {
            "ok": False,
            "database_url": "",
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_preflight",
        lambda *_args, **_kwargs: {"ok": True, "status": "passed", "checks": {}},
    )
    monkeypatch.setattr(
        bundle_module,
        "run_brain_prelaunch_check",
        lambda **_kwargs: {
            "ok": False,
            "production_ready": False,
            "status": "degraded_startable",
            "summary": {"strict_failed_keys": ["persistent_truth_source_ready"]},
            "failed_steps": ["persistent_truth_source_ready"],
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "collect_compatibility_boundary_snapshot",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "checks": [],
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_memory_governance_check",
        lambda: {"ok": True, "status": "passed", "summary": {"failed_checks": 0}},
    )
    monkeypatch.setattr(
        bundle_module,
        "run_release_runtime_check",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "scenarios": {},
            "failed_steps": [],
            "artifacts": _write_report_artifacts(tmp_path, "runtime_ok"),
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_monitoring_alerting_evidence",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "artifacts": _write_report_artifacts(tmp_path, "monitoring_ok"),
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_collect_external_tentacle_evidence",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "artifacts": _write_report_artifacts(tmp_path, "external_ok"),
        },
    )
    monkeypatch.setattr(
        bundle_module,
        "run_collect_security_acceptance_evidence",
        lambda **_kwargs: {
            "ok": True,
            "status": "passed",
            "artifacts": _write_report_artifacts(tmp_path, "security_ok"),
        },
    )

    payload = bundle_module.run_package_release_evidence_bundle(
        output_dir=str(tmp_path / "bundle"),
        write_report=True,
    )

    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert "brain_prelaunch" in payload["failed_steps"]
    assert Path(payload["artifacts"]["json_report"]).exists()
