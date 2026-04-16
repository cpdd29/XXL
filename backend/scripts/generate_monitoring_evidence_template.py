from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = BACKEND_ROOT / "docs" / "monitoring_evidence_template.json"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_monitoring_evidence_template(
    *,
    environment: str = "production",
    window_start: str = "",
    window_end: str = "",
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    return {
        "template_version": "1.0",
        "generated_at": generated_at,
        "status": "pending",
        "environment": str(environment or "production"),
        "window": {
            "start_at": str(window_start or ""),
            "end_at": str(window_end or ""),
            "timezone": "Asia/Shanghai",
        },
        "owners": {
            "primary_oncall": "",
            "secondary_oncall": "",
            "sre_reviewer": "",
        },
        "services": [
            {
                "service": "backend-api",
                "dashboard_urls": [],
                "alert_rule_ids": [],
                "slo": "",
            }
        ],
        "checklist": [
            {"key": "metrics_pipeline_healthy", "done": False, "notes": ""},
            {"key": "critical_alerts_armed", "done": False, "notes": ""},
            {"key": "dashboard_queries_healthy", "done": False, "notes": ""},
        ],
        "evidence_records": [
            {
                "title": "Dashboard snapshot",
                "source": "grafana",
                "captured_at": "",
                "path_or_url": "",
                "notes": "",
            },
            {
                "title": "Alert rules export",
                "source": "alertmanager",
                "captured_at": "",
                "path_or_url": "",
                "notes": "",
            },
        ],
        "signoff": {
            "prepared_by": "",
            "reviewed_by": "",
            "approved_by": "",
            "approved_at": "",
        },
        "notes": "",
    }


def write_template(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_generate_monitoring_evidence_template(
    *,
    output_path: str | None = None,
    environment: str = "production",
    window_start: str = "",
    window_end: str = "",
    write_output: bool = True,
) -> dict[str, Any]:
    payload = build_monitoring_evidence_template(
        environment=environment,
        window_start=window_start,
        window_end=window_end,
    )
    if write_output:
        target = Path(output_path).expanduser().resolve() if output_path else DEFAULT_OUTPUT_PATH
        write_template(target, payload)
        payload["artifact"] = {"template_path": str(target)}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a monitoring evidence template JSON file.")
    parser.add_argument("--output-path", help="Output file path. Default: backend/docs/monitoring_evidence_template.json")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--window-start", default="")
    parser.add_argument("--window-end", default="")
    args = parser.parse_args()

    payload = run_generate_monitoring_evidence_template(
        output_path=args.output_path,
        environment=args.environment,
        window_start=args.window_start,
        window_end=args.window_end,
        write_output=True,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
