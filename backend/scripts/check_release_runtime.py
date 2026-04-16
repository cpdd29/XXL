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

from scripts.check_brain_prelaunch import run_brain_prelaunch_check  # noqa: E402
from scripts.check_memory_governance import run_check as run_memory_governance_check  # noqa: E402
from scripts.check_persistence_contract import run_persistence_contract_check  # noqa: E402
from scripts.check_release_preflight import run_preflight  # noqa: E402
from scripts.external_tentacle_recovery import run_external_tentacle_recovery  # noqa: E402
from scripts.http_evidence import json_request, login_access_token, parse_key_value_specs  # noqa: E402
from scripts.package_t_common import render_markdown_report, write_json_report  # noqa: E402


DEFAULT_RUNTIME_ENDPOINTS = {
    "health": "/health",
    "dashboard_stats": "/api/dashboard/stats",
    "tools_health": "/api/tools/health?refresh=true",
    "external_health": "/api/external-connections/health",
}
SCENARIOS = ("postdeploy", "rollback", "recovery")


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


def _scenario_list(value: str) -> list[str]:
    normalized = str(value or "all").strip().lower()
    if normalized in {"", "all"}:
        return list(SCENARIOS)
    if normalized not in SCENARIOS:
        raise ValueError(f"Unsupported scenario: {value}")
    return [normalized]


def _load_snapshot_inventory(snapshot_root: Path, *, snapshot_name: str | None = None) -> dict[str, Any]:
    candidates = sorted(path.name for path in snapshot_root.iterdir() if path.is_dir()) if snapshot_root.exists() else []
    selected_snapshot = str(snapshot_name or "").strip() or (candidates[-1] if candidates else None)
    selected_path = snapshot_root / selected_snapshot if selected_snapshot else None
    selected_exists = bool(selected_path and selected_path.exists() and selected_path.is_dir())
    selected_files = (
        sorted(path.name for path in selected_path.iterdir())
        if selected_exists and selected_path is not None
        else []
    )
    return {
        "snapshot_root": str(snapshot_root),
        "total_snapshots": len(candidates),
        "available_snapshots": candidates,
        "selected_snapshot": selected_snapshot,
        "selected_exists": selected_exists,
        "selected_files": selected_files,
    }


def _probe_runtime_endpoints(
    *,
    backend_base_url: str,
    access_token: str | None,
    email: str | None,
    password: str | None,
    login_path: str,
    header_specs: list[str] | None,
    timeout_seconds: float,
    require_control_plane: bool,
    opener: Callable[..., Any],
) -> dict[str, Any]:
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
    normalized_base_url = str(backend_base_url or "http://127.0.0.1:8080").rstrip("/")
    probes: list[dict[str, Any]] = []
    for name, path in DEFAULT_RUNTIME_ENDPOINTS.items():
        request_headers = dict(headers)
        if name != "health" and resolved_access_token:
            request_headers["Authorization"] = f"Bearer {resolved_access_token}"
        response = json_request(
            url=f"{normalized_base_url}{path}",
            method="GET",
            headers=request_headers,
            timeout_seconds=timeout_seconds,
            opener=opener,
        )
        probes.append(
            {
                "name": name,
                "url": f"{normalized_base_url}{path}",
                "ok": bool(response["ok"]),
                "status_code": int(response["status_code"]),
                "error": response["error"],
                "auth_used": "bearer" if name != "health" and resolved_access_token else "anonymous",
                "body_excerpt": str(response.get("text") or "")[:240],
            }
        )
    probe_map = {item["name"]: item for item in probes}
    required = ["health"]
    if require_control_plane or resolved_access_token:
        required.extend(["dashboard_stats", "tools_health", "external_health"])
    failed_required = [name for name in required if not bool(probe_map.get(name, {}).get("ok"))]
    checks = [
        {
            "key": "health_endpoint_reachable",
            "ok": bool(probe_map.get("health", {}).get("ok")),
            "details": {"status_code": probe_map.get("health", {}).get("status_code")},
        },
        {
            "key": "control_plane_auth_available",
            "ok": (not require_control_plane) or bool(resolved_access_token),
            "details": {
                "require_control_plane": require_control_plane,
                "used_access_token": bool(resolved_access_token),
            },
        },
        {
            "key": "required_runtime_endpoints_reachable",
            "ok": not failed_required,
            "details": {"required": required, "failed_required": failed_required},
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
            "require_control_plane": require_control_plane,
        },
        "summary": {
            "backend_base_url": normalized_base_url,
            "required_endpoints": required,
            "reachable_required_endpoints": len(required) - len(failed_required),
        },
        "probes": probes,
    }


def _scenario_payload(
    *,
    scenario: str,
    repo_root: Path,
    backend_base_url: str,
    access_token: str | None,
    email: str | None,
    password: str | None,
    login_path: str,
    header_specs: list[str] | None,
    timeout_seconds: float,
    snapshot_root: Path,
    snapshot_name: str | None,
    require_production_ready: bool,
    require_control_plane: bool,
    opener: Callable[..., Any],
) -> dict[str, Any]:
    persistence_contract = run_persistence_contract_check()
    live_database_url = str(persistence_contract.get("database_url") or "").strip() or None
    release_preflight = run_preflight(
        repo_root,
        database_url=live_database_url,
        include_live_database=bool(persistence_contract.get("ok")) and bool(live_database_url),
    )
    brain_prelaunch = run_brain_prelaunch_check(repo_root=repo_root)
    runtime_endpoints = _probe_runtime_endpoints(
        backend_base_url=backend_base_url,
        access_token=access_token,
        email=email,
        password=password,
        login_path=login_path,
        header_specs=header_specs,
        timeout_seconds=timeout_seconds,
        require_control_plane=require_control_plane,
        opener=opener,
    )
    components: dict[str, Any] = {
        "persistence_contract": persistence_contract,
        "release_preflight": release_preflight,
        "brain_prelaunch": brain_prelaunch,
        "runtime_endpoints": runtime_endpoints,
    }
    runtime_check_map = {
        str(item.get("key") or ""): item
        for item in (runtime_endpoints.get("checks") or [])
        if isinstance(item, dict)
    }
    checks = [
        {
            "key": "release_preflight_ready",
            "ok": bool(release_preflight.get("ok")),
            "details": {"include_live_database": bool(live_database_url)},
        },
        {
            "key": "brain_runtime_ready",
            "ok": bool(
                brain_prelaunch.get("production_ready")
                if require_production_ready
                else brain_prelaunch.get("ok")
            ),
            "details": {
                "require_production_ready": require_production_ready,
                "startup_ready": bool(brain_prelaunch.get("startup_ready")),
                "production_ready": bool(brain_prelaunch.get("production_ready")),
                "status": brain_prelaunch.get("status"),
            },
        },
        {
            "key": "runtime_control_plane_auth_ready",
            "ok": bool(
                (runtime_check_map.get("control_plane_auth_available") or {}).get("ok", True)
            ),
            "details": (runtime_check_map.get("control_plane_auth_available") or {}).get("details", {}),
        },
        {
            "key": "runtime_endpoints_ready",
            "ok": bool(
                (runtime_check_map.get("required_runtime_endpoints_reachable") or {}).get("ok", False)
            ),
            "details": (runtime_check_map.get("required_runtime_endpoints_reachable") or {}).get("details", {}),
        },
    ]

    if scenario == "rollback":
        snapshot_inventory = _load_snapshot_inventory(snapshot_root, snapshot_name=snapshot_name)
        components["snapshot_inventory"] = snapshot_inventory
        checks.insert(
            0,
            {
                "key": "rollback_snapshot_available",
                "ok": bool(snapshot_inventory.get("selected_exists"))
                and "docker-compose.yml" in set(snapshot_inventory.get("selected_files") or []),
                "details": snapshot_inventory,
            },
        )

    if scenario == "recovery":
        external_recovery = run_external_tentacle_recovery(write_report=False)
        memory_governance = run_memory_governance_check()
        components["external_tentacle_recovery"] = external_recovery
        components["memory_governance"] = memory_governance
        checks.append(
            {
                "key": "external_tentacle_recovered",
                "ok": bool(external_recovery.get("ok")),
                "details": {
                    "status": external_recovery.get("status"),
                    "failed_steps": list(external_recovery.get("failed_steps") or []),
                },
            }
        )
        checks.append(
            {
                "key": "memory_governance_stable",
                "ok": bool(memory_governance.get("ok")),
                "details": {
                    "status": memory_governance.get("status"),
                    "failed_steps": list(memory_governance.get("failed_steps") or []),
                },
            }
        )

    failed_steps = [item["key"] for item in checks if not item["ok"]]
    return {
        "ok": not failed_steps,
        "status": "passed" if not failed_steps else "failed",
        "scenario": scenario,
        "checked_at": utc_now_iso(),
        "checks": checks,
        "failed_steps": failed_steps,
        "components": components,
    }


def write_runtime_report(
    *,
    payload: dict[str, Any],
    output_dir: Path,
    report_prefix: str = "release_runtime_check",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{report_prefix}_{stamp}.json"
    md_path = output_dir / f"{report_prefix}_{stamp}.md"
    write_json_report(json_path, payload)
    markdown = render_markdown_report(
        "Release Runtime Verification",
        [
            (
                "Status",
                {
                    "ok": payload["ok"],
                    "status": payload["status"],
                    "checked_at": payload["checked_at"],
                    "scenario": payload["scenario"],
                    "failed_steps": payload["failed_steps"],
                },
            ),
            ("Summary", payload["summary"]),
            ("Scenarios", payload["scenarios"]),
        ],
    )
    md_path.write_text(markdown, encoding="utf-8")
    return {"json_report": str(json_path), "markdown_report": str(md_path)}


def run_release_runtime_check(
    *,
    repo_root: Path = REPO_ROOT,
    scenario: str = "all",
    backend_base_url: str = "http://127.0.0.1:8080",
    access_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    header_specs: list[str] | None = None,
    timeout_seconds: float = 5.0,
    snapshot_dir: str | None = None,
    snapshot_name: str | None = None,
    require_production_ready: bool = False,
    require_control_plane: bool = False,
    output_dir: str | None = None,
    report_prefix: str = "release_runtime_check",
    write_report: bool = True,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    resolved_repo_root = repo_root.resolve()
    resolved_snapshot_root = (
        Path(snapshot_dir).expanduser().resolve()
        if snapshot_dir
        else (BACKEND_ROOT / "data" / "release_snapshots").resolve()
    )
    scenario_names = _scenario_list(scenario)
    scenarios = {
        name: _scenario_payload(
            scenario=name,
            repo_root=resolved_repo_root,
            backend_base_url=backend_base_url,
            access_token=access_token,
            email=email,
            password=password,
            login_path=login_path,
            header_specs=header_specs,
            timeout_seconds=timeout_seconds,
            snapshot_root=resolved_snapshot_root,
            snapshot_name=snapshot_name,
            require_production_ready=require_production_ready,
            require_control_plane=require_control_plane,
            opener=opener,
        )
        for name in scenario_names
    }
    failed_steps = [
        f"{name}:{step}"
        for name, item in scenarios.items()
        for step in item.get("failed_steps") or []
    ]
    payload: dict[str, Any] = {
        "ok": not failed_steps,
        "status": "passed" if not failed_steps else "failed",
        "checked_at": utc_now_iso(),
        "scenario": scenario if scenario_names != list(SCENARIOS) else "all",
        "failed_steps": failed_steps,
        "summary": {
            "requested_scenarios": scenario_names,
            "passed_scenarios": [name for name, item in scenarios.items() if item.get("ok")],
            "failed_scenarios": [name for name, item in scenarios.items() if not item.get("ok")],
            "snapshot_root": str(resolved_snapshot_root),
            "backend_base_url": str(backend_base_url).rstrip("/"),
        },
        "scenarios": scenarios,
    }
    if write_report:
        report_root = Path(output_dir).expanduser().resolve() if output_dir else BACKEND_ROOT / "docs"
        payload["artifacts"] = write_runtime_report(
            payload=payload,
            output_dir=report_root,
            report_prefix=report_prefix,
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run postdeploy / rollback / recovery runtime verification.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--scenario", default="all", choices=("all", *SCENARIOS))
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--access-token", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--login-path", default="/api/auth/login")
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--snapshot-name", default=None)
    parser.add_argument("--require-production-ready", action="store_true")
    parser.add_argument("--require-control-plane", action="store_true")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--report-prefix", default="release_runtime_check")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_release_runtime_check(
        repo_root=Path(args.repo_root),
        scenario=args.scenario,
        backend_base_url=args.backend_base_url,
        access_token=str(args.access_token or "").strip() or None,
        email=str(args.email or "").strip() or None,
        password=str(args.password or "").strip() or None,
        login_path=str(args.login_path or "/api/auth/login").strip() or "/api/auth/login",
        header_specs=args.header,
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        snapshot_dir=args.snapshot_dir,
        snapshot_name=args.snapshot_name,
        require_production_ready=bool(args.require_production_ready),
        require_control_plane=bool(args.require_control_plane),
        output_dir=args.output_dir,
        report_prefix=args.report_prefix,
        write_report=True,
        opener=request.urlopen,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
