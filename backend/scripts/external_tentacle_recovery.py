from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.dr_common import (  # noqa: E402
    build_drill_result_template,
    compare_external_manifests,
    drill_baseline_external_manifest,
    drill_gate_stats,
    drill_baseline_truth_sources,
    drill_failover_started_at,
    elapsed_seconds,
    external_recovery_manifest,
    load_drill_report,
    write_drill_report,
)


def run_external_tentacle_recovery(
    *,
    baseline_report: str | None = None,
    drill_name: str = "brain_failover_drill",
    scenario: str = "level2_brain_failover",
    verified_at: str | None = None,
    report_prefix: str = "external_tentacle_recovery",
    write_report: bool = True,
) -> dict[str, Any]:
    baseline_path, baseline_payload = load_drill_report(
        baseline_report,
        default_prefix="failover_prepare",
    )
    baseline_external_manifest = drill_baseline_external_manifest(baseline_payload)
    baseline_truth_sources = drill_baseline_truth_sources(baseline_payload)
    failover_started_at = drill_failover_started_at(baseline_payload)
    current_external_manifest = external_recovery_manifest()
    comparison = compare_external_manifests(baseline_external_manifest, current_external_manifest)
    resolved_verified_at = verified_at or current_external_manifest.get("captured_at")
    payload = build_drill_result_template(
        drill_name=drill_name,
        scenario=scenario,
        failover_started_at=failover_started_at,
        baseline_truth_sources=baseline_truth_sources,
        baseline_external_manifest=baseline_external_manifest,
    )
    payload["timeline"]["verified_at"] = resolved_verified_at
    payload["post_state"]["external_manifest"] = current_external_manifest
    payload["checks"] = comparison["checks"]
    payload["failed_steps"] = comparison["failed_steps"]
    payload["measurements"]["external_recovery_rto_seconds"] = elapsed_seconds(
        failover_started_at,
        resolved_verified_at,
    )
    current_summary = current_external_manifest.get("summary") if isinstance(current_external_manifest.get("summary"), dict) else {}
    payload["tentacle_recovery_scope"] = {
        "agent": True,
        "skill": True,
        "mcp": any(key in current_summary for key in ("mcp_instances", "mcp_families")),
    }
    payload["status"] = "passed" if not payload["failed_steps"] else "failed"
    payload["ok"] = not payload["failed_steps"]
    payload["gate_stats"] = drill_gate_stats(failed_steps=payload["failed_steps"])
    payload["baseline_report"] = str(baseline_path)
    if write_report:
        json_path, md_path = write_drill_report(
            prefix=report_prefix,
            title="External Tentacle Recovery",
            payload=payload,
            sections=[
                ("External Recovery Comparison", comparison),
                ("Current External Manifest", current_external_manifest),
                (
                    "Result",
                    {
                        "status": payload["status"],
                        "failed_steps": payload["failed_steps"],
                        "measurements": payload["measurements"],
                    },
                ),
            ],
        )
        payload["artifacts"] = {"json_report": str(json_path), "markdown_report": str(md_path)}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify external tentacle re-registration after failover.")
    parser.add_argument("--baseline-report")
    parser.add_argument("--drill-name", default="brain_failover_drill")
    parser.add_argument("--scenario", default="level2_brain_failover")
    parser.add_argument("--verified-at")
    parser.add_argument("--report-prefix", default="external_tentacle_recovery")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_external_tentacle_recovery(
        baseline_report=args.baseline_report,
        drill_name=args.drill_name,
        scenario=args.scenario,
        verified_at=args.verified_at,
        report_prefix=args.report_prefix,
        write_report=True,
    )
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    if artifacts.get("json_report"):
        print(artifacts["json_report"])
    if artifacts.get("markdown_report"):
        print(artifacts["markdown_report"])
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
