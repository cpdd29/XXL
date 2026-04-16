from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.dr_common import load_drill_report, write_drill_report  # noqa: E402


def _load_optional_report(report_path: str | None, *, default_prefix: str) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    try:
        path, payload = load_drill_report(report_path, default_prefix=default_prefix)
        return path, payload, None
    except FileNotFoundError as exc:
        return None, None, str(exc)


def _has_gate_stats(payload: dict[str, Any]) -> bool:
    gate_stats = payload.get("gate_stats") if isinstance(payload.get("gate_stats"), dict) else {}
    failed = gate_stats.get("failed")
    manual_intervention = gate_stats.get("manual_intervention")
    return isinstance(failed, int) and isinstance(manual_intervention, int)


def _drill_kind(payload: dict[str, Any]) -> str:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    raw = str(evidence.get("drill_kind") or payload.get("drill_kind") or "").strip().lower()
    return raw or "unknown"


def run_dr_result_gate(
    *,
    precheck_report: str | None = None,
    prepare_report: str | None = None,
    post_verify_report: str | None = None,
    recovery_report: str | None = None,
    allow_smoke: bool = False,
    report_prefix: str = "dr_result_gate",
    write_report: bool = True,
) -> dict[str, Any]:
    report_specs = {
        "precheck": {"input": precheck_report, "prefix": "dr_precheck"},
        "prepare": {"input": prepare_report, "prefix": "failover_prepare"},
        "post_verify": {"input": post_verify_report, "prefix": "post_failover_verify"},
        "recovery": {"input": recovery_report, "prefix": "external_tentacle_recovery"},
    }
    resolved_reports: dict[str, dict[str, Any]] = {}
    missing_reports: dict[str, str] = {}
    for name, spec in report_specs.items():
        path, payload, error = _load_optional_report(spec["input"], default_prefix=str(spec["prefix"]))
        if path is None or payload is None:
            missing_reports[name] = error or "report not found"
            continue
        resolved_reports[name] = {"path": str(path), "payload": payload}

    post_verify_payload = (resolved_reports.get("post_verify") or {}).get("payload")
    measurements = post_verify_payload.get("measurements") if isinstance(post_verify_payload, dict) else {}
    has_rto_rpo = (
        isinstance(measurements, dict)
        and "rto_seconds" in measurements
        and "estimated_rpo_seconds" in measurements
    )
    reports_for_stats = [
        (resolved_reports.get("precheck") or {}).get("payload"),
        (resolved_reports.get("prepare") or {}).get("payload"),
        (resolved_reports.get("post_verify") or {}).get("payload"),
        (resolved_reports.get("recovery") or {}).get("payload"),
    ]
    has_gate_stats = all(isinstance(payload, dict) and _has_gate_stats(payload) for payload in reports_for_stats)
    report_drill_kinds = {
        name: _drill_kind(value["payload"])
        for name, value in resolved_reports.items()
    }
    non_formal_reports = {
        name: kind
        for name, kind in report_drill_kinds.items()
        if kind != "formal"
    }
    has_required_drill_kind = allow_smoke or not non_formal_reports
    aggregated_gate_stats = {
        "failed": sum(
            int(((payload or {}).get("gate_stats") or {}).get("failed") or 0)
            for payload in reports_for_stats
            if isinstance(payload, dict)
        ),
        "manual_intervention": sum(
            int(((payload or {}).get("gate_stats") or {}).get("manual_intervention") or 0)
            for payload in reports_for_stats
            if isinstance(payload, dict)
        ),
    }
    checks = [
        {
            "key": "required_reports_present",
            "ok": not missing_reports,
            "details": {
                "expected": list(report_specs.keys()),
                "missing": missing_reports,
                "resolved": {name: value["path"] for name, value in resolved_reports.items()},
            },
        },
        {
            "key": "rto_rpo_fields_present",
            "ok": has_rto_rpo,
            "details": {
                "required_fields": ["measurements.rto_seconds", "measurements.estimated_rpo_seconds"],
                "post_verify_report": (resolved_reports.get("post_verify") or {}).get("path"),
            },
        },
        {
            "key": "failed_manual_intervention_stats_present",
            "ok": has_gate_stats,
            "details": {
                "required_fields": ["gate_stats.failed", "gate_stats.manual_intervention"],
            },
        },
        {
            "key": "formal_drill_kind_required",
            "ok": has_required_drill_kind,
            "details": {
                "allow_smoke": allow_smoke,
                "required_kind": "formal",
                "report_drill_kinds": report_drill_kinds,
                "non_formal_reports": non_formal_reports,
            },
        },
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    payload: dict[str, Any] = {
        "ok": not failed_steps,
        "status": "passed" if not failed_steps else "failed",
        "checks": checks,
        "failed_steps": failed_steps,
        "reports": {name: value["path"] for name, value in resolved_reports.items()},
        "missing_reports": missing_reports,
        "allow_smoke": allow_smoke,
        "report_drill_kinds": report_drill_kinds,
        "gate_stats": aggregated_gate_stats,
    }
    if write_report:
        json_path, md_path = write_drill_report(
            prefix=report_prefix,
            title="DR Result Gate",
            payload=payload,
            sections=[
                ("Gate Checks", {"status": payload["status"], "checks": checks}),
                ("Reports", {"resolved": payload["reports"], "missing": missing_reports}),
                ("Aggregated Stats", aggregated_gate_stats),
            ],
        )
        payload["artifacts"] = {"json_report": str(json_path), "markdown_report": str(md_path)}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate DR result package by required report artifacts and fields.")
    parser.add_argument("--precheck-report")
    parser.add_argument("--prepare-report")
    parser.add_argument("--post-verify-report")
    parser.add_argument("--recovery-report")
    parser.add_argument("--report-prefix", default="dr_result_gate")
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_dr_result_gate(
        precheck_report=args.precheck_report,
        prepare_report=args.prepare_report,
        post_verify_report=args.post_verify_report,
        recovery_report=args.recovery_report,
        allow_smoke=args.allow_smoke,
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
