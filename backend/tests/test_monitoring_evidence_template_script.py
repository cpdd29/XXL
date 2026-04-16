from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_monitoring_evidence_template import (
    build_monitoring_evidence_template,
    run_generate_monitoring_evidence_template,
)


def test_build_monitoring_evidence_template_contains_expected_sections(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.generate_monitoring_evidence_template.utc_now_iso",
        lambda: "2026-04-15T12:00:00+00:00",
    )
    payload = build_monitoring_evidence_template(
        environment="staging",
        window_start="2026-04-15T13:00:00+08:00",
        window_end="2026-04-15T15:00:00+08:00",
    )

    assert payload["template_version"] == "1.0"
    assert payload["generated_at"] == "2026-04-15T12:00:00+00:00"
    assert payload["environment"] == "staging"
    assert payload["window"]["start_at"] == "2026-04-15T13:00:00+08:00"
    assert payload["window"]["end_at"] == "2026-04-15T15:00:00+08:00"
    assert isinstance(payload["services"], list)
    assert isinstance(payload["checklist"], list)
    assert isinstance(payload["evidence_records"], list)
    assert isinstance(payload["signoff"], dict)


def test_run_generate_monitoring_evidence_template_writes_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "scripts.generate_monitoring_evidence_template.utc_now_iso",
        lambda: "2026-04-15T12:30:00+00:00",
    )
    output_path = tmp_path / "monitoring_evidence_template.json"

    payload = run_generate_monitoring_evidence_template(
        output_path=str(output_path),
        write_output=True,
    )

    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["generated_at"] == "2026-04-15T12:30:00+00:00"
    assert payload["artifact"]["template_path"] == str(output_path)
