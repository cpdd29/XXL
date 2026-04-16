from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.dr_common import (  # noqa: E402
    drill_gate_stats,
    external_recovery_manifest,
    platform_readiness,
    runbook_step_plan,
    truth_source_snapshot,
    write_drill_report,
)


def run_dr_precheck(
    *,
    drill_name: str = "brain_dr_precheck",
    scenario: str = "brain_failover_precheck",
    report_prefix: str = "dr_precheck",
    write_report: bool = True,
) -> dict[str, Any]:
    readiness = platform_readiness()
    truth_sources = truth_source_snapshot()
    external_manifest = external_recovery_manifest()
    step_plan = runbook_step_plan()
    checks = [
        {
            "key": "runbook_present",
            "ok": bool(readiness.get("runbook_exists")),
            "details": {"runbook_exists": bool(readiness.get("runbook_exists"))},
        },
        {
            "key": "result_template_present",
            "ok": bool(readiness.get("result_template_exists")),
            "details": {"result_template_exists": bool(readiness.get("result_template_exists"))},
        },
        {
            "key": "truth_sources_snapshot_ready",
            "ok": bool(truth_sources.get("captured_at")),
            "details": {
                "tasks_total": int((truth_sources.get("tasks") or {}).get("total") or 0),
                "runs_total": int((truth_sources.get("runs") or {}).get("total") or 0),
                "audit_total": int((truth_sources.get("audit") or {}).get("total") or 0),
                "security_rules": int((truth_sources.get("security") or {}).get("rule_total") or 0),
            },
        },
        {
            "key": "external_registry_snapshot_ready",
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
            "key": "runbook_step_plan_loaded",
            "ok": len(step_plan) >= 9,
            "details": {"step_total": len(step_plan)},
        },
    ]
    ok = all(item["ok"] for item in checks)
    payload = {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "drill_name": drill_name,
        "scenario": scenario,
        "evidence": {
            "drill_kind": "formal",
            "evidence_level": "precheck",
            "operator_notes": "",
        },
        "readiness": readiness,
        "baseline": {
            "truth_sources": truth_sources,
            "external_manifest": external_manifest,
        },
        "step_plan": step_plan,
        "checks": checks,
        "failed_steps": [item["key"] for item in checks if not item["ok"]],
    }
    payload["gate_stats"] = drill_gate_stats(
        failed_steps=payload["failed_steps"],
        step_plan=step_plan,
    )
    if write_report:
        json_path, md_path = write_drill_report(
            prefix=report_prefix,
            title="DR Precheck",
            payload=payload,
            sections=[
                ("Readiness", readiness),
                ("Truth Sources", truth_sources),
                ("External Manifest", external_manifest),
                ("Checks", {"status": payload["status"], "checks": checks}),
            ],
        )
        payload["artifacts"] = {"json_report": str(json_path), "markdown_report": str(md_path)}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DR readiness precheck for the brain control plane.")
    parser.add_argument("--drill-name", default="brain_dr_precheck")
    parser.add_argument("--scenario", default="brain_failover_precheck")
    parser.add_argument("--report-prefix", default="dr_precheck")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_dr_precheck(
        drill_name=args.drill_name,
        scenario=args.scenario,
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
