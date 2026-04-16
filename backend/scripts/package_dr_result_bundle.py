from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import shutil
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.dr_common import REPORTS_ROOT, load_json, write_drill_report  # noqa: E402
from scripts.dr_precheck import run_dr_precheck  # noqa: E402
from scripts.dr_result_gate import run_dr_result_gate  # noqa: E402
from scripts.external_tentacle_recovery import run_external_tentacle_recovery  # noqa: E402
from scripts.failover_prepare import run_failover_prepare  # noqa: E402
from scripts.post_failover_verify import run_post_failover_verify  # noqa: E402


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_exercise_id(value: str | None) -> str:
    cleaned = str(value or "").strip()
    if cleaned:
        return cleaned
    return f"dr_exercise_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"


def _resolve_archive_dir(archive_dir: str | None) -> Path:
    if archive_dir:
        return Path(archive_dir).expanduser().resolve()
    return (REPORTS_ROOT / "dr_result_archives").resolve()


def _report_artifact_paths(report_paths: list[Path]) -> list[Path]:
    artifacts: list[Path] = []
    for path in report_paths:
        resolved = path.expanduser().resolve()
        artifacts.append(resolved)
        markdown_path = resolved.with_suffix(".md")
        if markdown_path.exists():
            artifacts.append(markdown_path.resolve())
    return artifacts


def _json_artifact_path(payload: dict[str, Any], *, stage_key: str) -> str:
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    report_path = artifacts.get("json_report")
    if isinstance(report_path, str) and report_path.strip():
        return str(Path(report_path).expanduser().resolve())
    raise RuntimeError(f"{stage_key} did not produce a json_report artifact")


def _orchestration_stage(
    *,
    key: str,
    source: str,
    report: str | None = None,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    stage: dict[str, Any] = {
        "key": key,
        "source": source,
        "report": report,
        "status": str((payload or {}).get("status") or source),
        "ok": bool((payload or {}).get("ok")) if payload is not None else source == "provided",
        "failed_steps": list((payload or {}).get("failed_steps") or []),
    }
    if reason:
        stage["reason"] = reason
    return stage


def _orchestrate_formal_reports(
    *,
    precheck_report: str | None,
    prepare_report: str | None,
    post_verify_report: str | None,
    recovery_report: str | None,
) -> dict[str, Any]:
    resolved_reports = {
        "precheck_report": precheck_report,
        "prepare_report": prepare_report,
        "post_verify_report": post_verify_report,
        "recovery_report": recovery_report,
    }
    stages: list[dict[str, Any]] = []
    failed_stage: str | None = None

    if resolved_reports["precheck_report"]:
        stages.append(
            _orchestration_stage(
                key="precheck",
                source="provided",
                report=resolved_reports["precheck_report"],
            )
        )
    else:
        precheck_payload = run_dr_precheck(write_report=True)
        resolved_reports["precheck_report"] = _json_artifact_path(precheck_payload, stage_key="precheck")
        stages.append(
            _orchestration_stage(
                key="precheck",
                source="generated",
                report=resolved_reports["precheck_report"],
                payload=precheck_payload,
            )
        )
        if not precheck_payload.get("ok"):
            failed_stage = "precheck"

    if resolved_reports["prepare_report"]:
        stages.append(
            _orchestration_stage(
                key="prepare",
                source="provided",
                report=resolved_reports["prepare_report"],
            )
        )
    elif failed_stage is None:
        prepare_payload = run_failover_prepare(write_report=True)
        resolved_reports["prepare_report"] = _json_artifact_path(prepare_payload, stage_key="prepare")
        stages.append(
            _orchestration_stage(
                key="prepare",
                source="generated",
                report=resolved_reports["prepare_report"],
                payload=prepare_payload,
            )
        )
        if not prepare_payload.get("ok"):
            failed_stage = "prepare"
    else:
        stages.append(
            _orchestration_stage(
                key="prepare",
                source="skipped",
                reason=f"blocked_by:{failed_stage}",
            )
        )

    prepare_baseline = resolved_reports["prepare_report"]
    if resolved_reports["post_verify_report"]:
        stages.append(
            _orchestration_stage(
                key="post_verify",
                source="provided",
                report=resolved_reports["post_verify_report"],
            )
        )
    elif failed_stage is None and prepare_baseline:
        post_verify_payload = run_post_failover_verify(
            baseline_report=prepare_baseline,
            write_report=True,
        )
        resolved_reports["post_verify_report"] = _json_artifact_path(
            post_verify_payload,
            stage_key="post_verify",
        )
        stages.append(
            _orchestration_stage(
                key="post_verify",
                source="generated",
                report=resolved_reports["post_verify_report"],
                payload=post_verify_payload,
            )
        )
        if not post_verify_payload.get("ok"):
            failed_stage = "post_verify"
    else:
        stages.append(
            _orchestration_stage(
                key="post_verify",
                source="skipped",
                reason=f"blocked_by:{failed_stage or 'missing_prepare_report'}",
            )
        )

    if resolved_reports["recovery_report"]:
        stages.append(
            _orchestration_stage(
                key="recovery",
                source="provided",
                report=resolved_reports["recovery_report"],
            )
        )
    elif failed_stage is None and prepare_baseline:
        recovery_payload = run_external_tentacle_recovery(
            baseline_report=prepare_baseline,
            write_report=True,
        )
        resolved_reports["recovery_report"] = _json_artifact_path(
            recovery_payload,
            stage_key="recovery",
        )
        stages.append(
            _orchestration_stage(
                key="recovery",
                source="generated",
                report=resolved_reports["recovery_report"],
                payload=recovery_payload,
            )
        )
        if not recovery_payload.get("ok"):
            failed_stage = "recovery"
    else:
        stages.append(
            _orchestration_stage(
                key="recovery",
                source="skipped",
                reason=f"blocked_by:{failed_stage or 'missing_prepare_report'}",
            )
        )

    reports_complete = all(bool(value) for value in resolved_reports.values())
    if failed_stage is None and not reports_complete:
        failed_stage = "reports_incomplete"

    return {
        "ok": failed_stage is None,
        "failed_stage": failed_stage,
        "reports": resolved_reports,
        "stages": stages,
    }


def _copy_into_archive(
    *,
    source_paths: list[Path],
    archive_root: Path,
) -> list[dict[str, Any]]:
    archive_root.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict[str, Any]] = []
    for source in source_paths:
        target = archive_root / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        manifest_items.append(
            {
                "name": source.name,
                "source": str(source),
                "archived": str(target),
                "size_bytes": int(target.stat().st_size),
                "sha256": _content_sha256(target),
            }
        )
    return manifest_items


def run_package_dr_result_bundle(
    *,
    precheck_report: str | None = None,
    prepare_report: str | None = None,
    post_verify_report: str | None = None,
    recovery_report: str | None = None,
    operator_notes: str = "",
    exercise_id: str | None = None,
    archive_dir: str | None = None,
    report_prefix: str = "dr_result_bundle_formal",
    gate_report_prefix: str = "dr_result_gate_formal",
    orchestrate: bool = False,
    write_report: bool = True,
) -> dict[str, Any]:
    resolved_exercise_id = _normalize_exercise_id(exercise_id)
    orchestration: dict[str, Any] | None = None
    resolved_reports = {
        "precheck_report": precheck_report,
        "prepare_report": prepare_report,
        "post_verify_report": post_verify_report,
        "recovery_report": recovery_report,
    }
    if orchestrate:
        orchestration = _orchestrate_formal_reports(**resolved_reports)
        resolved_reports = dict(orchestration["reports"])

    if orchestrate and orchestration is not None and not orchestration.get("ok"):
        available_report_paths = [
            Path(path).expanduser().resolve()
            for path in resolved_reports.values()
            if isinstance(path, str) and path.strip()
        ]
        report_details = [
            {
                "name": path.name,
                "path": str(path),
                "markdown_path": str(path.with_suffix(".md")) if path.with_suffix(".md").exists() else None,
                "drill_kind": str(((load_json(path).get("evidence") or {}).get("drill_kind") or "unknown")).strip().lower()
                or "unknown",
                "gate_stats": dict((load_json(path).get("gate_stats") or {})),
            }
            for path in available_report_paths
        ]
        payload: dict[str, Any] = {
            "ok": False,
            "status": "blocked",
            "generated_at": _utc_now_iso(),
            "exercise_id": resolved_exercise_id,
            "operator_notes": str(operator_notes or "").strip(),
            "required_drill_kind": "formal",
            "orchestration": orchestration,
            "gate": {
                "status": "blocked",
                "failed_steps": [f"orchestration:{orchestration.get('failed_stage') or 'unknown'}"],
                "checks": [],
                "gate_stats": {"failed": 1, "manual_intervention": 0},
                "report_drill_kinds": {},
            },
            "bundle": {
                "reports": report_details,
                "report_count": len(report_details),
            },
            "archive_manifest": {
                "archive_dir": str(_resolve_archive_dir(archive_dir) / resolved_exercise_id),
                "archive_complete": False,
                "items": [],
            },
        }
        if write_report:
            json_path, md_path = write_drill_report(
                prefix=report_prefix,
                title="DR Formal Result Bundle",
                payload=payload,
                sections=[
                    ("Orchestration", orchestration),
                    ("Bundle Reports", payload["bundle"]),
                    ("Gate", payload["gate"]),
                ],
            )
            payload["artifacts"] = {"json_report": str(json_path), "markdown_report": str(md_path)}
        return payload

    gate_payload = run_dr_result_gate(
        precheck_report=resolved_reports["precheck_report"],
        prepare_report=resolved_reports["prepare_report"],
        post_verify_report=resolved_reports["post_verify_report"],
        recovery_report=resolved_reports["recovery_report"],
        allow_smoke=False,
        report_prefix=gate_report_prefix,
        write_report=write_report,
    )

    report_paths = [
        Path(path).expanduser().resolve()
        for path in (gate_payload.get("reports") or {}).values()
        if str(path).strip()
    ]
    report_artifact_paths = _report_artifact_paths(report_paths)
    report_details = [
        {
            "name": path.name,
            "path": str(path),
            "markdown_path": str(path.with_suffix(".md")) if path.with_suffix(".md").exists() else None,
            "drill_kind": str(((load_json(path).get("evidence") or {}).get("drill_kind") or "unknown")).strip().lower()
            or "unknown",
            "gate_stats": dict((load_json(path).get("gate_stats") or {})),
        }
        for path in report_paths
    ]

    artifacts = gate_payload.get("artifacts") if isinstance(gate_payload.get("artifacts"), dict) else {}
    gate_json = artifacts.get("json_report")
    gate_md = artifacts.get("markdown_report")
    gate_artifact_paths = [
        Path(path).expanduser().resolve()
        for path in [gate_json, gate_md]
        if isinstance(path, str) and path.strip()
    ]

    archive_root = _resolve_archive_dir(archive_dir) / resolved_exercise_id
    copied = _copy_into_archive(source_paths=[*report_artifact_paths, *gate_artifact_paths], archive_root=archive_root)
    copied_names = {item["name"] for item in copied}
    source_name_set = {path.name for path in [*report_artifact_paths, *gate_artifact_paths]}
    archive_complete = copied_names == source_name_set

    payload: dict[str, Any] = {
        "ok": bool(gate_payload.get("ok")),
        "status": "packaged" if bool(gate_payload.get("ok")) else "blocked",
        "generated_at": _utc_now_iso(),
        "exercise_id": resolved_exercise_id,
        "operator_notes": str(operator_notes or "").strip(),
        "required_drill_kind": "formal",
        "gate": {
            "status": str(gate_payload.get("status") or "unknown"),
            "failed_steps": list(gate_payload.get("failed_steps") or []),
            "checks": list(gate_payload.get("checks") or []),
            "gate_stats": dict(gate_payload.get("gate_stats") or {}),
            "report_drill_kinds": dict(gate_payload.get("report_drill_kinds") or {}),
        },
        "bundle": {
            "reports": report_details,
            "report_count": len(report_details),
        },
        "archive_manifest": {
            "archive_dir": str(archive_root),
            "archive_complete": archive_complete,
            "items": copied,
        },
    }
    if orchestration is not None:
        payload["orchestration"] = orchestration

    if write_report:
        json_path, md_path = write_drill_report(
            prefix=report_prefix,
            title="DR Formal Result Bundle",
            payload=payload,
            sections=[
                ("Bundle Summary", {"status": payload["status"], "exercise_id": resolved_exercise_id}),
                ("Gate", payload["gate"]),
                ("Bundle Reports", payload["bundle"]),
                ("Archive Manifest", payload["archive_manifest"]),
            ],
        )
        payload["artifacts"] = {"json_report": str(json_path), "markdown_report": str(md_path)}
        bundle_copied = _copy_into_archive(
            source_paths=[json_path.resolve(), md_path.resolve()],
            archive_root=archive_root,
        )
        payload["archive_manifest"]["items"].extend(bundle_copied)
        archived_names = {item["name"] for item in payload["archive_manifest"]["items"]}
        expected_names = {
            path.name
            for path in [
                *report_artifact_paths,
                *gate_artifact_paths,
                json_path.resolve(),
                md_path.resolve(),
            ]
        }
        payload["archive_manifest"]["archive_complete"] = archived_names == expected_names
        payload["archive_manifest"]["bundle_artifacts"] = {
            "json_report": str(archive_root / json_path.name),
            "markdown_report": str(archive_root / md_path.name),
        }

        archive_json = archive_root / "archive_manifest.json"
        archive_md = archive_root / "archive_manifest.md"
        archive_json.write_text(json.dumps(payload["archive_manifest"], ensure_ascii=False, indent=2), encoding="utf-8")
        archive_md.write_text(
            "\n".join(
                [
                    "# DR Archive Manifest",
                    "",
                    f"- generated_at: {payload['generated_at']}",
                    f"- exercise_id: {resolved_exercise_id}",
                    f"- archive_dir: {payload['archive_manifest']['archive_dir']}",
                    f"- archive_complete: {payload['archive_manifest']['archive_complete']}",
                    "",
                    "## Items",
                    "",
                    *[
                        f"- {item['name']} | sha256={item['sha256']} | size={item['size_bytes']} | source={item['source']}"
                        for item in payload["archive_manifest"]["items"]
                    ],
                    "",
                ]
            ),
            encoding="utf-8",
        )
        payload["archive_manifest"]["artifacts"] = {
            "json_report": str(archive_json),
            "markdown_report": str(archive_md),
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Package DR reports into a formal result bundle and archive manifest.")
    parser.add_argument("--precheck-report")
    parser.add_argument("--prepare-report")
    parser.add_argument("--post-verify-report")
    parser.add_argument("--recovery-report")
    parser.add_argument("--operator-notes", default="")
    parser.add_argument("--exercise-id")
    parser.add_argument("--archive-dir")
    parser.add_argument("--report-prefix", default="dr_result_bundle_formal")
    parser.add_argument("--gate-report-prefix", default="dr_result_gate_formal")
    parser.add_argument("--orchestrate", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_package_dr_result_bundle(
        precheck_report=args.precheck_report,
        prepare_report=args.prepare_report,
        post_verify_report=args.post_verify_report,
        recovery_report=args.recovery_report,
        operator_notes=args.operator_notes,
        exercise_id=args.exercise_id,
        archive_dir=args.archive_dir,
        report_prefix=args.report_prefix,
        gate_report_prefix=args.gate_report_prefix,
        orchestrate=args.orchestrate,
        write_report=True,
    )
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    archive_artifacts = (
        payload.get("archive_manifest", {}).get("artifacts")
        if isinstance(payload.get("archive_manifest"), dict)
        else {}
    )
    if artifacts.get("json_report"):
        print(artifacts["json_report"])
    if artifacts.get("markdown_report"):
        print(artifacts["markdown_report"])
    if isinstance(archive_artifacts, dict) and archive_artifacts.get("json_report"):
        print(archive_artifacts["json_report"])
    if isinstance(archive_artifacts, dict) and archive_artifacts.get("markdown_report"):
        print(archive_artifacts["markdown_report"])
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
