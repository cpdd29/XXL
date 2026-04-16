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
    compare_truth_source_snapshots,
    drill_baseline_external_manifest,
    drill_gate_stats,
    drill_baseline_truth_sources,
    drill_failover_started_at,
    elapsed_seconds,
    load_drill_report,
    platform_readiness,
    truth_source_snapshot,
    utc_now_iso,
    write_drill_report,
)


def run_post_failover_verify(
    *,
    baseline_report: str | None = None,
    drill_name: str = "brain_failover_drill",
    scenario: str = "level2_brain_failover",
    verified_at: str | None = None,
    report_prefix: str = "post_failover_verify",
    write_report: bool = True,
) -> dict[str, Any]:
    baseline_path, baseline_payload = load_drill_report(
        baseline_report,
        default_prefix="failover_prepare",
    )
    baseline_truth_sources = drill_baseline_truth_sources(baseline_payload)
    baseline_external_manifest = drill_baseline_external_manifest(baseline_payload)
    failover_started_at = drill_failover_started_at(baseline_payload)
    current_truth_sources = truth_source_snapshot()
    readiness = platform_readiness()
    truth_comparison = compare_truth_source_snapshots(baseline_truth_sources, current_truth_sources)
    nats_check = {
        "key": "nats_or_fallback_ready",
        "ok": bool(readiness.get("nats_connected")) or bool(readiness.get("fallback_event_bus_available")),
        "details": {
            "nats_connected": bool(readiness.get("nats_connected")),
            "fallback_event_bus_available": bool(readiness.get("fallback_event_bus_available")),
        },
    }
    payload = build_drill_result_template(
        drill_name=drill_name,
        scenario=scenario,
        failover_started_at=failover_started_at,
        baseline_truth_sources=baseline_truth_sources,
        baseline_external_manifest=baseline_external_manifest,
    )
    resolved_verified_at = verified_at or utc_now_iso()
    payload["timeline"]["verified_at"] = resolved_verified_at
    payload["post_state"]["truth_sources"] = current_truth_sources
    payload["checks"] = [
        *truth_comparison["checks"],
        nats_check,
    ]
    payload["failed_steps"] = [
        *truth_comparison["failed_steps"],
        *([nats_check["key"]] if not nats_check["ok"] else []),
    ]
    payload["measurements"]["rto_seconds"] = elapsed_seconds(failover_started_at, resolved_verified_at)
    payload["measurements"]["estimated_rpo_seconds"] = truth_comparison["estimated_rpo_seconds"]
    payload["measurements"]["estimated_lost_records"] = truth_comparison["estimated_lost_records"]
    payload["status"] = "passed" if not payload["failed_steps"] else "failed"
    payload["ok"] = not payload["failed_steps"]
    payload["readiness"] = readiness
    payload["gate_stats"] = drill_gate_stats(failed_steps=payload["failed_steps"])
    payload["baseline_report"] = str(baseline_path)
    if write_report:
        json_path, md_path = write_drill_report(
            prefix=report_prefix,
            title="Post Failover Verify",
            payload=payload,
            sections=[
                ("Truth Comparison", truth_comparison),
                ("Current Truth Sources", current_truth_sources),
                ("Readiness", readiness),
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
    parser = argparse.ArgumentParser(description="Verify truth-source continuity after brain failover.")
    parser.add_argument("--baseline-report")
    parser.add_argument("--drill-name", default="brain_failover_drill")
    parser.add_argument("--scenario", default="level2_brain_failover")
    parser.add_argument("--verified-at")
    parser.add_argument("--report-prefix", default="post_failover_verify")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_post_failover_verify(
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
