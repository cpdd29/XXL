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
    drill_gate_stats,
    external_recovery_manifest,
    platform_readiness,
    runbook_step_plan,
    truth_source_snapshot,
    utc_now_iso,
    write_drill_report,
)


def run_failover_prepare(
    *,
    drill_name: str = "brain_failover_drill",
    scenario: str = "level2_brain_failover",
    failover_started_at: str | None = None,
    report_prefix: str = "failover_prepare",
    write_report: bool = True,
) -> dict[str, Any]:
    readiness = platform_readiness()
    truth_sources = truth_source_snapshot()
    external_manifest = external_recovery_manifest()
    step_plan = runbook_step_plan()
    payload = build_drill_result_template(
        drill_name=drill_name,
        scenario=scenario,
        failover_started_at=failover_started_at or utc_now_iso(),
        baseline_truth_sources=truth_sources,
        baseline_external_manifest=external_manifest,
    )
    checks = [
        {
            "key": "baseline_truth_sources_captured",
            "ok": bool(truth_sources.get("captured_at")),
            "details": {
                "tasks_total": int((truth_sources.get("tasks") or {}).get("total") or 0),
                "runs_total": int((truth_sources.get("runs") or {}).get("total") or 0),
                "audit_total": int((truth_sources.get("audit") or {}).get("total") or 0),
                "security_rule_total": int((truth_sources.get("security") or {}).get("rule_total") or 0),
            },
        },
        {
            "key": "baseline_external_manifest_captured",
            "ok": bool(external_manifest.get("captured_at")),
            "details": dict(external_manifest.get("summary") or {}),
        },
        {
            "key": "nats_or_fallback_ready",
            "ok": bool(readiness.get("nats_connected")) or bool(readiness.get("fallback_event_bus_available")),
            "details": {
                "nats_connected": bool(readiness.get("nats_connected")),
                "fallback_event_bus_available": bool(readiness.get("fallback_event_bus_available")),
            },
        },
        {
            "key": "runbook_alignment_loaded",
            "ok": bool(readiness.get("runbook_exists")) and len(step_plan) >= 9,
            "details": {
                "runbook_exists": bool(readiness.get("runbook_exists")),
                "step_total": len(step_plan),
            },
        },
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    payload["checks"] = checks
    payload["failed_steps"] = failed_steps
    payload["status"] = "prepared" if not failed_steps else "blocked"
    payload["ok"] = not failed_steps
    payload["readiness"] = readiness
    payload["step_plan"] = step_plan
    payload["gate_stats"] = drill_gate_stats(
        failed_steps=failed_steps,
        step_plan=step_plan,
    )
    payload["operator_handoff"] = {
        "next_checks": [
            "python backend/scripts/post_failover_verify.py --baseline-report <prepare_report.json>",
            "python backend/scripts/external_tentacle_recovery.py --baseline-report <prepare_report.json>",
        ]
    }
    if write_report:
        json_path, md_path = write_drill_report(
            prefix=report_prefix,
            title="Failover Prepare",
            payload=payload,
            sections=[
                ("Readiness", readiness),
                ("Baseline Truth Sources", truth_sources),
                ("Baseline External Manifest", external_manifest),
                ("Step Plan", {"steps": step_plan}),
                ("Prepare Summary", {"status": payload["status"], "checks": checks}),
            ],
        )
        payload["artifacts"] = {"json_report": str(json_path), "markdown_report": str(md_path)}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture baseline state before brain failover drill.")
    parser.add_argument("--drill-name", default="brain_failover_drill")
    parser.add_argument("--scenario", default="level2_brain_failover")
    parser.add_argument("--failover-started-at")
    parser.add_argument("--report-prefix", default="failover_prepare")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_failover_prepare(
        drill_name=args.drill_name,
        scenario=args.scenario,
        failover_started_at=args.failover_started_at,
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
