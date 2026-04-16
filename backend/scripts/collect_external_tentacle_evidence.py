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

from scripts.http_evidence import json_request, login_access_token, parse_key_value_specs  # noqa: E402
from scripts.package_t_common import render_markdown_report, write_json_report  # noqa: E402


DEFAULT_REGISTRY_PATH = REPO_ROOT / "deploy" / "external-registry" / "workbot_external_sources.local.json"
DEFAULT_ENDPOINTS = {
    "external_health": "/api/external-connections/health",
    "external_governance": "/api/external-connections/governance",
    "tool_sources": "/api/tool-sources?refresh=true",
    "tools_health": "/api/tools/health?refresh=true",
}
DEFAULT_REQUIRED = tuple(DEFAULT_ENDPOINTS.keys())


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _load_registry_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "source_ids": [],
            "tool_ids": [],
            "source_count": 0,
            "tool_count": 0,
            "sources_by_kind": {},
            "error": "registry_file_missing",
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        return {
            "exists": True,
            "path": str(path),
            "source_ids": [],
            "tool_ids": [],
            "source_count": 0,
            "tool_count": 0,
            "sources_by_kind": {},
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    top_level_tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    source_ids: list[str] = []
    tool_ids: list[str] = []
    sources_by_kind: dict[str, int] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "").strip()
        source_kind = str(source.get("kind") or "unknown").strip() or "unknown"
        if source_id:
            source_ids.append(source_id)
        sources_by_kind[source_kind] = sources_by_kind.get(source_kind, 0) + 1
        for tool in source.get("tools") if isinstance(source.get("tools"), list) else []:
            if not isinstance(tool, dict):
                continue
            tool_id = str(tool.get("id") or tool.get("name") or "").strip()
            if tool_id:
                tool_ids.append(tool_id)
    for tool in top_level_tools:
        if not isinstance(tool, dict):
            continue
        tool_id = str(tool.get("id") or tool.get("name") or "").strip()
        if tool_id:
            tool_ids.append(tool_id)

    deduped_source_ids = sorted(dict.fromkeys(source_ids))
    deduped_tool_ids = sorted(dict.fromkeys(tool_ids))
    return {
        "exists": True,
        "path": str(path),
        "source_ids": deduped_source_ids,
        "tool_ids": deduped_tool_ids,
        "source_count": len(deduped_source_ids),
        "tool_count": len(deduped_tool_ids),
        "sources_by_kind": dict(sorted(sources_by_kind.items())),
        "error": None,
    }


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


def _endpoint_summary(response: dict[str, Any]) -> dict[str, Any]:
    payload = response["json"] if isinstance(response.get("json"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "ok": bool(response["ok"]),
        "status_code": int(response["status_code"]),
        "error": response["error"],
        "summary": summary,
        "total": int(payload.get("total") or len(items) or 0),
        "items_sample": items[:5],
        "body_excerpt": str(response.get("text") or "")[:240],
    }


def collect_external_tentacle_evidence(
    *,
    backend_base_url: str = "http://127.0.0.1:8080",
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    access_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    header_specs: list[str] | None = None,
    timeout_seconds: float = 5.0,
    scan_sources: bool = False,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    registry_summary = _load_registry_summary(registry_path)
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
    if resolved_access_token:
        headers["Authorization"] = f"Bearer {resolved_access_token}"

    normalized_base_url = str(backend_base_url or "http://127.0.0.1:8080").rstrip("/")
    scan_response = None
    if scan_sources and resolved_access_token:
        scan_response = json_request(
            url=f"{normalized_base_url}/api/tool-sources/scan",
            method="POST",
            headers=headers,
            timeout_seconds=timeout_seconds,
            opener=opener,
        )

    endpoint_results: dict[str, dict[str, Any]] = {}
    for key, path in DEFAULT_ENDPOINTS.items():
        response = json_request(
            url=f"{normalized_base_url}{path}",
            method="GET",
            headers=headers,
            timeout_seconds=timeout_seconds,
            opener=opener,
        )
        endpoint_results[key] = _endpoint_summary(response)

    tool_source_payload = endpoint_results["tool_sources"]
    tool_source_items = tool_source_payload["items_sample"]
    tool_source_response = json_request(
        url=f"{normalized_base_url}{DEFAULT_ENDPOINTS['tool_sources']}",
        method="GET",
        headers=headers,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    tool_source_full_payload = (
        tool_source_response["json"] if isinstance(tool_source_response.get("json"), dict) else {}
    )
    listed_source_ids = sorted(
        str(item.get("id") or "").strip()
        for item in tool_source_full_payload.get("items", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    )

    tools_health_response = json_request(
        url=f"{normalized_base_url}{DEFAULT_ENDPOINTS['tools_health']}",
        method="GET",
        headers=headers,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    tools_health_payload = tools_health_response["json"] if isinstance(tools_health_response.get("json"), dict) else {}
    health_total = int(tools_health_payload.get("total") or 0)

    missing_sources = [
        source_id for source_id in registry_summary["source_ids"] if source_id not in set(listed_source_ids)
    ]
    checks = [
        {
            "key": "registry_file_present",
            "ok": bool(registry_summary["exists"]) and not registry_summary["error"],
            "details": {"path": registry_summary["path"], "error": registry_summary["error"]},
        },
        {
            "key": "required_endpoints_reachable",
            "ok": all(endpoint_results[key]["ok"] for key in DEFAULT_REQUIRED),
            "details": {key: endpoint_results[key]["status_code"] for key in DEFAULT_REQUIRED},
        },
        {
            "key": "registry_sources_loaded_in_control_plane",
            "ok": not missing_sources,
            "details": {
                "registry_source_ids": registry_summary["source_ids"],
                "listed_source_ids": listed_source_ids,
                "missing_source_ids": missing_sources,
            },
        },
        {
            "key": "registry_tools_visible_in_tools_health",
            "ok": health_total >= int(registry_summary["tool_count"] or 0),
            "details": {
                "registry_tool_count": registry_summary["tool_count"],
                "tools_health_total": health_total,
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
        },
        "registry": registry_summary,
        "scan_sources": {
            "requested": bool(scan_sources),
            "ok": bool(scan_response and scan_response["ok"]),
            "status_code": int(scan_response["status_code"]) if scan_response else None,
            "error": scan_response["error"] if scan_response else None,
        },
        "endpoints": endpoint_results,
        "summary": {
            "registry_source_count": registry_summary["source_count"],
            "registry_tool_count": registry_summary["tool_count"],
            "listed_source_count": len(listed_source_ids),
            "tools_health_total": health_total,
            "backend_base_url": normalized_base_url,
            "tool_sources_sample_count": len(tool_source_items),
        },
    }


def write_evidence_bundle(
    *,
    payload: dict[str, Any],
    output_dir: Path,
    report_prefix: str = "external_tentacle_evidence",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{report_prefix}_{stamp}.json"
    md_path = output_dir / f"{report_prefix}_{stamp}.md"
    write_json_report(json_path, payload)
    markdown = render_markdown_report(
        "External Tentacle Evidence",
        [
            ("Status", {"ok": payload["ok"], "status": payload["status"], "checked_at": payload["checked_at"]}),
            ("Registry", payload["registry"]),
            ("Checks", {"checks": payload["checks"], "failed_steps": payload["failed_steps"]}),
            ("Summary", payload["summary"]),
            ("Endpoints", payload["endpoints"]),
        ],
    )
    md_path.write_text(markdown, encoding="utf-8")
    return {"json_report": str(json_path), "markdown_report": str(md_path)}


def run_collect_external_tentacle_evidence(
    *,
    backend_base_url: str = "http://127.0.0.1:8080",
    registry_path: str | None = None,
    access_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    header_specs: list[str] | None = None,
    timeout_seconds: float = 5.0,
    scan_sources: bool = False,
    output_dir: str | None = None,
    report_prefix: str = "external_tentacle_evidence",
    write_report: bool = True,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    payload = collect_external_tentacle_evidence(
        backend_base_url=backend_base_url,
        registry_path=Path(registry_path).expanduser().resolve() if registry_path else DEFAULT_REGISTRY_PATH,
        access_token=access_token,
        email=email,
        password=password,
        login_path=login_path,
        header_specs=header_specs,
        timeout_seconds=timeout_seconds,
        scan_sources=scan_sources,
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
    parser = argparse.ArgumentParser(description="Collect external tentacle control-plane evidence.")
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--access-token", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--login-path", default="/api/auth/login")
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--scan-sources", action="store_true")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--report-prefix", default="external_tentacle_evidence")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_collect_external_tentacle_evidence(
        backend_base_url=args.backend_base_url,
        registry_path=args.registry_path,
        access_token=str(args.access_token or "").strip() or None,
        email=str(args.email or "").strip() or None,
        password=str(args.password or "").strip() or None,
        login_path=str(args.login_path or "/api/auth/login").strip() or "/api/auth/login",
        header_specs=args.header,
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        scan_sources=bool(args.scan_sources),
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
