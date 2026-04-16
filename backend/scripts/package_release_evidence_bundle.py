from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import shutil
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_brain_prelaunch import run_brain_prelaunch_check  # noqa: E402
from scripts.check_compatibility_boundaries import (  # noqa: E402
    collect_compat_shell_inventory,
    find_brain_core_compat_import_violations,
    find_entrypoint_decision_residue,
    find_execution_gateway_bypass_candidates,
    find_legacy_alias_references,
    find_unexpected_production_legacy_alias_growth,
    group_legacy_alias_references_by_category,
    partition_legacy_alias_references,
)
from scripts.check_memory_governance import run_check as run_memory_governance_check  # noqa: E402
from scripts.check_persistence_contract import run_persistence_contract_check  # noqa: E402
from scripts.check_release_preflight import run_preflight  # noqa: E402
from scripts.check_release_runtime import run_release_runtime_check  # noqa: E402
from scripts.collect_external_tentacle_evidence import run_collect_external_tentacle_evidence  # noqa: E402
from scripts.collect_monitoring_alerting_evidence import run_monitoring_alerting_evidence  # noqa: E402
from scripts.collect_security_acceptance_evidence import (  # noqa: E402
    run_collect_security_acceptance_evidence,
)
from scripts.package_dr_result_bundle import run_package_dr_result_bundle  # noqa: E402
from scripts.package_t_common import render_markdown_report, write_json_report  # noqa: E402


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _bundle_id(value: str | None = None) -> str:
    cleaned = str(value or "").strip()
    if cleaned:
        return cleaned
    return f"release_evidence_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"


def _resolve_output_root(output_dir: str | None, bundle_id: str) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return (BACKEND_ROOT / "docs" / "release_evidence_archives" / bundle_id).resolve()


def _write_component_report(
    *,
    component: str,
    title: str,
    payload: dict[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{component}_{stamp}.json"
    md_path = output_dir / f"{component}_{stamp}.md"
    write_json_report(json_path, payload)
    markdown = render_markdown_report(
        title,
        [
            (
                "Status",
                {
                    "ok": bool(payload.get("ok")),
                    "status": payload.get("status"),
                    "generated_at": payload.get("generated_at") or payload.get("checked_at"),
                },
            ),
            ("Payload", payload),
        ],
    )
    md_path.write_text(markdown, encoding="utf-8")
    return {
        "json_report": str(json_path),
        "markdown_report": str(md_path),
    }


def _artifact_paths(payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    for key in ("json_report", "markdown_report"):
        value = artifacts.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(Path(value).expanduser().resolve())
    archive_manifest = payload.get("archive_manifest") if isinstance(payload.get("archive_manifest"), dict) else {}
    archive_artifacts = (
        archive_manifest.get("artifacts") if isinstance(archive_manifest.get("artifacts"), dict) else {}
    )
    for key in ("json_report", "markdown_report"):
        value = archive_artifacts.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(Path(value).expanduser().resolve())
    return paths


def _copy_into_archive(*, source_paths: list[Path], archive_root: Path) -> list[dict[str, Any]]:
    archive_root.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in source_paths:
        resolved = source.expanduser().resolve()
        if not resolved.exists():
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        target = archive_root / resolved.name
        if resolved != target:
            shutil.copy2(resolved, target)
        copied.append(
            {
                "name": target.name,
                "source": str(resolved),
                "archived": str(target),
                "size_bytes": int(target.stat().st_size),
            }
        )
    return copied


def collect_compatibility_boundary_snapshot(
    *,
    backend_root: Path = BACKEND_ROOT,
) -> dict[str, Any]:
    inventory = collect_compat_shell_inventory(backend_root)
    compat_import_violations = find_brain_core_compat_import_violations(backend_root)
    entrypoint_residue = find_entrypoint_decision_residue(backend_root)
    execution_bypass = find_execution_gateway_bypass_candidates(backend_root)
    legacy_alias_references = find_legacy_alias_references(backend_root)
    production_residue, compat_test_residue = partition_legacy_alias_references(legacy_alias_references)
    unexpected_growth = find_unexpected_production_legacy_alias_growth(
        legacy_alias_references,
        scan_root=backend_root,
    )

    checks = [
        {
            "key": "compat_shell_inventory_complete",
            "ok": not inventory["missing"],
            "details": inventory,
        },
        {
            "key": "brain_core_no_compat_imports",
            "ok": not compat_import_violations,
            "details": {"violations": compat_import_violations},
        },
        {
            "key": "entrypoint_no_decision_residue",
            "ok": not entrypoint_residue,
            "details": {"residue": entrypoint_residue},
        },
        {
            "key": "execution_gateway_no_bypass_candidates",
            "ok": not execution_bypass,
            "details": {"candidates": execution_bypass},
        },
        {
            "key": "legacy_alias_frozen_baseline_not_growing",
            "ok": not unexpected_growth,
            "details": {"unexpected_growth": unexpected_growth},
        },
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    return {
        "ok": not failed_steps,
        "status": "passed" if not failed_steps else "failed",
        "generated_at": _utc_now_iso(),
        "checks": checks,
        "failed_steps": failed_steps,
        "inventory": inventory,
        "legacy_aliases": {
            "production_total": len(production_residue),
            "compat_test_total": len(compat_test_residue),
            "production_grouped": {
                category: len(items)
                for category, items in group_legacy_alias_references_by_category(production_residue).items()
                if items
            },
            "compat_test_grouped": {
                category: len(items)
                for category, items in group_legacy_alias_references_by_category(compat_test_residue).items()
                if items
            },
        },
    }


def run_package_release_evidence_bundle(
    *,
    backend_base_url: str = "http://127.0.0.1:8080",
    access_token: str | None = None,
    metrics_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    header_specs: list[str] | None = None,
    timeout_seconds: float = 5.0,
    registry_path: str | None = None,
    database_path: str | None = None,
    bundle_id: str | None = None,
    output_dir: str | None = None,
    report_prefix: str = "release_evidence_bundle",
    include_monitoring: bool = True,
    include_external: bool = True,
    include_security: bool = True,
    include_dr_bundle: bool = False,
    orchestrate_dr: bool = False,
    dr_exercise_id: str | None = None,
    dr_archive_dir: str | None = None,
    operator_notes: str = "",
    write_report: bool = True,
) -> dict[str, Any]:
    resolved_bundle_id = _bundle_id(bundle_id)
    report_root = _resolve_output_root(output_dir, resolved_bundle_id)
    report_root.mkdir(parents=True, exist_ok=True)

    persistence_contract = run_persistence_contract_check()
    live_database_url = str(persistence_contract.get("database_url") or "").strip() or None
    release_preflight = run_preflight(
        REPO_ROOT,
        database_url=live_database_url,
        include_live_database=bool(persistence_contract.get("ok")) and bool(live_database_url),
    )
    release_preflight["generated_at"] = _utc_now_iso()
    release_preflight["artifacts"] = _write_component_report(
        component="release_preflight",
        title="Release Preflight",
        payload=release_preflight,
        output_dir=report_root,
    )

    brain_prelaunch = run_brain_prelaunch_check(repo_root=REPO_ROOT)
    brain_prelaunch["generated_at"] = _utc_now_iso()
    brain_prelaunch["artifacts"] = _write_component_report(
        component="brain_prelaunch",
        title="Brain Prelaunch",
        payload=brain_prelaunch,
        output_dir=report_root,
    )

    compatibility = collect_compatibility_boundary_snapshot()
    compatibility["artifacts"] = _write_component_report(
        component="compatibility_boundaries",
        title="Compatibility Boundaries",
        payload=compatibility,
        output_dir=report_root,
    )

    memory_governance = run_memory_governance_check()
    memory_governance["generated_at"] = _utc_now_iso()
    memory_governance["artifacts"] = _write_component_report(
        component="memory_governance",
        title="Memory Governance",
        payload=memory_governance,
        output_dir=report_root,
    )

    release_runtime = run_release_runtime_check(
        repo_root=REPO_ROOT,
        scenario="all",
        backend_base_url=backend_base_url,
        access_token=access_token,
        email=email,
        password=password,
        login_path=login_path,
        header_specs=header_specs,
        timeout_seconds=timeout_seconds,
        write_report=False,
    )
    release_runtime["generated_at"] = _utc_now_iso()
    release_runtime["artifacts"] = _write_component_report(
        component="release_runtime",
        title="Release Runtime Verification",
        payload=release_runtime,
        output_dir=report_root,
    )

    components: dict[str, dict[str, Any]] = {
        "release_preflight": release_preflight,
        "brain_prelaunch": brain_prelaunch,
        "compatibility_boundaries": compatibility,
        "memory_governance": memory_governance,
        "release_runtime": release_runtime,
    }

    if include_monitoring:
        components["monitoring_alerting"] = run_monitoring_alerting_evidence(
            backend_base_url=backend_base_url,
            access_token=access_token,
            metrics_token=metrics_token,
            email=email,
            password=password,
            login_path=login_path,
            header_specs=header_specs,
            timeout_seconds=timeout_seconds,
            output_dir=str(report_root),
            write_report=write_report,
        )

    if include_external:
        components["external_tentacles"] = run_collect_external_tentacle_evidence(
            backend_base_url=backend_base_url,
            registry_path=registry_path or "",
            access_token=access_token,
            email=email,
            password=password,
            login_path=login_path,
            header_specs=header_specs,
            timeout_seconds=timeout_seconds,
            output_dir=str(report_root),
            write_report=write_report,
            scan_sources=True,
        )

    if include_security:
        components["security_acceptance"] = run_collect_security_acceptance_evidence(
            backend_base_url=backend_base_url,
            access_token=access_token,
            email=email,
            password=password,
            login_path=login_path,
            header_specs=header_specs,
            timeout_seconds=timeout_seconds,
            database_path=database_path,
            output_dir=str(report_root),
            write_report=write_report,
        )

    if include_dr_bundle:
        components["dr_bundle"] = run_package_dr_result_bundle(
            exercise_id=dr_exercise_id,
            archive_dir=dr_archive_dir or str(report_root / "dr_bundle_archive"),
            operator_notes=operator_notes,
            orchestrate=orchestrate_dr,
            write_report=write_report,
        )

    checks = [
        {
            "key": name,
            "ok": bool(payload.get("ok")),
            "status": payload.get("status"),
            "failed_steps": list(payload.get("failed_steps") or []),
        }
        for name, payload in components.items()
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    payload: dict[str, Any] = {
        "ok": not failed_steps,
        "status": "packaged" if not failed_steps else "blocked",
        "generated_at": _utc_now_iso(),
        "bundle_id": resolved_bundle_id,
        "operator_notes": str(operator_notes or "").strip(),
        "checks": checks,
        "failed_steps": failed_steps,
        "components": components,
    }

    archive_items = _copy_into_archive(
        source_paths=[
            path
            for component_payload in components.values()
            for path in _artifact_paths(component_payload)
        ],
        archive_root=report_root,
    )
    payload["archive_manifest"] = {
        "archive_dir": str(report_root),
        "archive_complete": bool(archive_items),
        "items": archive_items,
    }

    if write_report:
        bundle_artifacts = _write_component_report(
            component=report_prefix,
            title="Release Evidence Bundle",
            payload=payload,
            output_dir=report_root,
        )
        payload["artifacts"] = bundle_artifacts
        bundle_archive_items = _copy_into_archive(
            source_paths=[Path(bundle_artifacts["json_report"]), Path(bundle_artifacts["markdown_report"])],
            archive_root=report_root,
        )
        payload["archive_manifest"]["items"].extend(bundle_archive_items)
        payload["archive_manifest"]["bundle_artifacts"] = {
            "json_report": str(report_root / Path(bundle_artifacts["json_report"]).name),
            "markdown_report": str(report_root / Path(bundle_artifacts["markdown_report"]).name),
        }
        archive_json = report_root / "archive_manifest.json"
        archive_md = report_root / "archive_manifest.md"
        archive_json.write_text(
            json.dumps(payload["archive_manifest"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        archive_md.write_text(
            "\n".join(
                [
                    "# Release Evidence Archive Manifest",
                    "",
                    f"- generated_at: {payload['generated_at']}",
                    f"- bundle_id: {resolved_bundle_id}",
                    f"- archive_dir: {payload['archive_manifest']['archive_dir']}",
                    f"- archive_complete: {payload['archive_manifest']['archive_complete']}",
                    "",
                    "## Items",
                    "",
                    *[
                        f"- {item['name']} | size={item['size_bytes']} | source={item['source']}"
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
    parser = argparse.ArgumentParser(description="Package release evidence and prelaunch acceptance artifacts.")
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--access-token", default="")
    parser.add_argument("--metrics-token", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--login-path", default="/api/auth/login")
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--registry-path", default=None)
    parser.add_argument("--database-path", default=None)
    parser.add_argument("--bundle-id", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--report-prefix", default="release_evidence_bundle")
    parser.add_argument("--skip-monitoring", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--skip-security", action="store_true")
    parser.add_argument("--include-dr-bundle", action="store_true")
    parser.add_argument("--orchestrate-dr", action="store_true")
    parser.add_argument("--dr-exercise-id", default=None)
    parser.add_argument("--dr-archive-dir", default=None)
    parser.add_argument("--operator-notes", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_package_release_evidence_bundle(
        backend_base_url=args.backend_base_url,
        access_token=str(args.access_token or "").strip() or None,
        metrics_token=str(args.metrics_token or "").strip() or None,
        email=str(args.email or "").strip() or None,
        password=str(args.password or "").strip() or None,
        login_path=str(args.login_path or "/api/auth/login").strip() or "/api/auth/login",
        header_specs=args.header,
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        registry_path=args.registry_path,
        database_path=args.database_path,
        bundle_id=args.bundle_id,
        output_dir=args.output_dir,
        report_prefix=args.report_prefix,
        include_monitoring=not bool(args.skip_monitoring),
        include_external=not bool(args.skip_external),
        include_security=not bool(args.skip_security),
        include_dr_bundle=bool(args.include_dr_bundle),
        orchestrate_dr=bool(args.orchestrate_dr),
        dr_exercise_id=args.dr_exercise_id,
        dr_archive_dir=args.dr_archive_dir,
        operator_notes=args.operator_notes,
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

    if args.strict and not bool(payload.get("ok")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
