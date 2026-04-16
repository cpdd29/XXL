from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Callable
from urllib import request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_external_ingress_bypass import run_external_ingress_bypass_check  # noqa: E402
from scripts.check_security_audit_persistence import run_security_audit_persistence_check  # noqa: E402
from scripts.check_security_controls import run_security_control_check  # noqa: E402
from scripts.check_security_entrypoints import run_security_entrypoint_check  # noqa: E402
from scripts.http_evidence import json_request, login_access_token, parse_key_value_specs  # noqa: E402
from scripts.package_t_common import render_markdown_report, write_json_report  # noqa: E402


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _resolve_access_token(
    *,
    backend_base_url: str,
    access_token: str | None,
    email: str | None,
    password: str | None,
    login_path: str,
    timeout_seconds: float,
    opener: Callable[..., Any],
) -> tuple[str | None, dict[str, Any] | None]:
    resolved_token = str(access_token or "").strip()
    if resolved_token:
        return resolved_token, None
    normalized_email = str(email or "").strip()
    normalized_password = str(password or "").strip()
    if not normalized_email or not normalized_password:
        return None, None
    resolved_token = login_access_token(
        base_url=backend_base_url,
        email=normalized_email,
        password=normalized_password,
        timeout_seconds=timeout_seconds,
        login_path=login_path,
        opener=opener,
    )
    return resolved_token, {
        "used_login": True,
        "email": normalized_email,
        "login_path": login_path,
    }


def _snapshot_summary(response: dict[str, Any]) -> dict[str, Any]:
    payload = response["json"] if isinstance(response.get("json"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return {
        "ok": bool(response["ok"]),
        "status_code": int(response["status_code"]),
        "error": response["error"],
        "keys": sorted(payload.keys()),
        "total": int(payload.get("total") or len(items) or 0),
        "items_sample": items[:5],
        "body_excerpt": str(response.get("text") or "")[:240],
    }


def collect_security_acceptance_evidence(
    *,
    repo_root: Path = REPO_ROOT,
    backend_base_url: str = "http://127.0.0.1:8080",
    access_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    header_specs: list[str] | None = None,
    timeout_seconds: float = 5.0,
    database_path: Path | None = None,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    entrypoints = run_security_entrypoint_check(repo_root=repo_root)
    controls = run_security_control_check()
    audit_persistence = run_security_audit_persistence_check(database_path=database_path)
    bypass = run_external_ingress_bypass_check(repo_root=repo_root)

    resolved_access_token, auth_details = _resolve_access_token(
        backend_base_url=backend_base_url,
        access_token=access_token,
        email=email,
        password=password,
        login_path=login_path,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    headers = parse_key_value_specs(header_specs or [])
    control_plane_snapshots: dict[str, Any] = {}
    snapshot_attempted = False
    if resolved_access_token:
        headers["Authorization"] = f"Bearer {resolved_access_token}"
        normalized_base_url = str(backend_base_url or "http://127.0.0.1:8080").rstrip("/")
        snapshot_attempted = True
        for key, path in {
            "security_report": "/api/security/report",
            "dashboard_logs": "/api/dashboard/logs?limit=20",
        }.items():
            control_plane_snapshots[key] = _snapshot_summary(
                json_request(
                    url=f"{normalized_base_url}{path}",
                    method="GET",
                    headers=headers,
                    timeout_seconds=timeout_seconds,
                    opener=opener,
                )
            )

    checks = [
        {
            "key": "security_entrypoints_ready",
            "ok": bool(entrypoints["ok"]),
            "details": entrypoints["summary"],
        },
        {
            "key": "security_controls_ready",
            "ok": bool(controls["ok"]),
            "details": controls["summary"],
        },
        {
            "key": "security_audit_persistence_ready",
            "ok": bool(audit_persistence["ok"]),
            "details": audit_persistence["summary"],
        },
        {
            "key": "external_ingress_bypass_ready",
            "ok": bool(bypass["ok"]),
            "details": bypass["summary"],
        },
        {
            "key": "security_control_plane_snapshots_reachable",
            "ok": True if not snapshot_attempted else all(item["ok"] for item in control_plane_snapshots.values()),
            "details": {
                "attempted": snapshot_attempted,
                "snapshots": {key: value["status_code"] for key, value in control_plane_snapshots.items()},
            },
        },
    ]
    failed_steps = [item["key"] for item in checks if not item["ok"]]
    return {
        "ok": not failed_steps,
        "status": "passed" if not failed_steps else "failed",
        "checked_at": utc_now_iso(),
        "checks": checks,
        "failed_steps": failed_steps,
        "auth": {
            "used_access_token": bool(resolved_access_token),
            "login": auth_details,
            "snapshot_attempted": snapshot_attempted,
        },
        "entrypoints": entrypoints,
        "controls": controls,
        "audit_persistence": audit_persistence,
        "external_ingress_bypass": bypass,
        "control_plane_snapshots": control_plane_snapshots,
    }


def write_evidence_bundle(
    *,
    payload: dict[str, Any],
    output_dir: Path,
    report_prefix: str = "security_acceptance_evidence",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{report_prefix}_{stamp}.json"
    md_path = output_dir / f"{report_prefix}_{stamp}.md"
    write_json_report(json_path, payload)
    markdown = render_markdown_report(
        "Security Acceptance Evidence",
        [
            ("Status", {"ok": payload["ok"], "status": payload["status"], "checked_at": payload["checked_at"]}),
            ("Checks", {"checks": payload["checks"], "failed_steps": payload["failed_steps"]}),
            ("Entry Points", payload["entrypoints"]),
            ("Controls", payload["controls"]),
            ("Audit Persistence", payload["audit_persistence"]),
            ("Ingress Bypass", payload["external_ingress_bypass"]),
            ("Control Plane Snapshots", payload["control_plane_snapshots"]),
        ],
    )
    md_path.write_text(markdown, encoding="utf-8")
    return {"json_report": str(json_path), "markdown_report": str(md_path)}


def run_collect_security_acceptance_evidence(
    *,
    backend_base_url: str = "http://127.0.0.1:8080",
    access_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    header_specs: list[str] | None = None,
    timeout_seconds: float = 5.0,
    database_path: str | None = None,
    output_dir: str | None = None,
    report_prefix: str = "security_acceptance_evidence",
    write_report: bool = True,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    payload = collect_security_acceptance_evidence(
        repo_root=REPO_ROOT,
        backend_base_url=backend_base_url,
        access_token=access_token,
        email=email,
        password=password,
        login_path=login_path,
        header_specs=header_specs,
        timeout_seconds=timeout_seconds,
        database_path=Path(database_path).expanduser().resolve() if database_path else None,
        opener=opener,
    )
    if write_report:
        report_root = Path(output_dir).expanduser().resolve() if output_dir else BACKEND_ROOT / "docs"
        payload["artifacts"] = write_evidence_bundle(
            payload=payload,
            output_dir=report_root,
            report_prefix=report_prefix,
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect security acceptance evidence bundle.")
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--access-token", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--login-path", default="/api/auth/login")
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--database-path", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--report-prefix", default="security_acceptance_evidence")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_collect_security_acceptance_evidence(
        backend_base_url=args.backend_base_url,
        access_token=str(args.access_token or "").strip() or None,
        email=str(args.email or "").strip() or None,
        password=str(args.password or "").strip() or None,
        login_path=str(args.login_path or "/api/auth/login").strip() or "/api/auth/login",
        header_specs=args.header,
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        database_path=args.database_path,
        output_dir=args.output_dir,
        report_prefix=args.report_prefix,
        write_report=True,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
