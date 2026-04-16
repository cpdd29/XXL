from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Callable
from urllib import request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.http_evidence import json_request, login_access_token, parse_key_value_specs  # noqa: E402
from scripts.package_t_common import render_markdown_report, write_json_report  # noqa: E402


DEFAULT_ENDPOINT_PATHS = {
    "metrics": "/api/dashboard/metrics",
    "dashboard_stats": "/api/dashboard/stats",
    "alerts": "/api/alerts",
}
DEFAULT_ENDPOINTS = {
    name: f"http://127.0.0.1:8080{path}"
    for name, path in DEFAULT_ENDPOINT_PATHS.items()
}
DEFAULT_REQUIRED = ("metrics", "dashboard_stats", "alerts")


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_endpoint_specs(specs: list[str]) -> dict[str, str]:
    return parse_key_value_specs(specs, lower_keys=True)


def _decode_excerpt(text: str, *, limit: int = 240) -> str:
    return str(text or "").strip()[:limit]


def _default_endpoints(backend_base_url: str) -> dict[str, str]:
    normalized_base = str(backend_base_url or "http://127.0.0.1:8080").rstrip("/")
    return {
        name: f"{normalized_base}{path}"
        for name, path in DEFAULT_ENDPOINT_PATHS.items()
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


def _probe_headers(
    *,
    name: str,
    access_token: str | None,
    metrics_token: str | None,
    base_headers: dict[str, str],
) -> dict[str, str]:
    headers = dict(base_headers)
    if name == "metrics" and str(metrics_token or "").strip():
        headers["X-WorkBot-Metrics-Token"] = str(metrics_token).strip()
        return headers
    if str(access_token or "").strip():
        headers["Authorization"] = f"Bearer {str(access_token).strip()}"
    return headers


def probe_endpoint(
    *,
    name: str,
    url: str,
    timeout_seconds: float,
    access_token: str | None,
    metrics_token: str | None,
    base_headers: dict[str, str],
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    response = json_request(
        url=url,
        method="GET",
        headers=_probe_headers(
            name=name,
            access_token=access_token,
            metrics_token=metrics_token,
            base_headers=base_headers,
        ),
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    return {
        "name": name,
        "url": url,
        "ok": bool(response["ok"]),
        "status_code": int(response["status_code"]),
        "checked_at": utc_now_iso(),
        "error": response["error"],
        "body_excerpt": _decode_excerpt(response["text"]),
        "auth_mode": (
            "metrics_scrape_token"
            if name == "metrics" and str(metrics_token or "").strip()
            else "bearer"
            if str(access_token or "").strip()
            else "anonymous"
        ),
    }


def collect_monitoring_alerting_evidence(
    *,
    endpoints: dict[str, str] | None = None,
    required_keys: tuple[str, ...] = DEFAULT_REQUIRED,
    timeout_seconds: float = 3.0,
    backend_base_url: str = "http://127.0.0.1:8080",
    access_token: str | None = None,
    metrics_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    headers: dict[str, str] | None = None,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    targets = _default_endpoints(backend_base_url)
    if endpoints:
        targets.update(endpoints)

    resolved_access_token, auth_details = _resolve_access_token(
        backend_base_url=backend_base_url,
        access_token=access_token,
        email=email,
        password=password,
        login_path=login_path,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )

    probes = [
        probe_endpoint(
            name=name,
            url=url,
            timeout_seconds=timeout_seconds,
            access_token=resolved_access_token,
            metrics_token=metrics_token,
            base_headers=dict(headers or {}),
            opener=opener,
        )
        for name, url in targets.items()
    ]
    probe_map = {item["name"]: item for item in probes}
    missing_required = sorted(key for key in required_keys if key not in probe_map)
    failed_required = sorted(
        key for key in required_keys if key in probe_map and not bool(probe_map[key]["ok"])
    )
    succeeded = sum(1 for item in probes if item["ok"])

    checks = [
        {
            "key": "required_endpoints_present",
            "ok": not missing_required,
            "details": {"required": list(required_keys), "missing": missing_required},
        },
        {
            "key": "required_endpoints_reachable",
            "ok": not failed_required and not missing_required,
            "details": {"failed_required": failed_required},
        },
        {
            "key": "metrics_auth_configured",
            "ok": bool(str(metrics_token or "").strip()) or bool(str(resolved_access_token or "").strip()),
            "details": {
                "metrics_token_present": bool(str(metrics_token or "").strip()),
                "access_token_present": bool(str(resolved_access_token or "").strip()),
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
        "summary": {
            "total_endpoints": len(probes),
            "reachable_endpoints": succeeded,
            "unreachable_endpoints": len(probes) - succeeded,
            "required_endpoints": list(required_keys),
            "backend_base_url": backend_base_url.rstrip("/"),
        },
        "auth": {
            "used_access_token": bool(str(resolved_access_token or "").strip()),
            "used_metrics_scrape_token": bool(str(metrics_token or "").strip()),
            "login": auth_details,
        },
        "probes": probes,
    }


def write_evidence_bundle(
    *,
    payload: dict[str, Any],
    output_dir: Path,
    report_prefix: str = "monitoring_alerting_evidence",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{report_prefix}_{stamp}.json"
    md_path = output_dir / f"{report_prefix}_{stamp}.md"
    write_json_report(json_path, payload)
    markdown = render_markdown_report(
        "Monitoring + Alerting Evidence",
        [
            ("Status", {"ok": payload["ok"], "status": payload["status"], "checked_at": payload["checked_at"]}),
            ("Auth", payload["auth"]),
            ("Checks", {"checks": payload["checks"], "failed_steps": payload["failed_steps"]}),
            ("Summary", payload["summary"]),
            ("Probe Results", {"probes": payload["probes"]}),
        ],
    )
    md_path.write_text(markdown, encoding="utf-8")
    return {"json_report": str(json_path), "markdown_report": str(md_path)}


def run_monitoring_alerting_evidence(
    *,
    endpoint_specs: list[str] | None = None,
    header_specs: list[str] | None = None,
    timeout_seconds: float = 3.0,
    backend_base_url: str = "http://127.0.0.1:8080",
    access_token: str | None = None,
    metrics_token: str | None = None,
    email: str | None = None,
    password: str | None = None,
    login_path: str = "/api/auth/login",
    output_dir: str | None = None,
    report_prefix: str = "monitoring_alerting_evidence",
    write_report: bool = True,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    parsed_endpoints = parse_endpoint_specs(endpoint_specs or [])
    parsed_headers = parse_key_value_specs(header_specs or [])
    payload = collect_monitoring_alerting_evidence(
        endpoints=parsed_endpoints,
        timeout_seconds=timeout_seconds,
        backend_base_url=backend_base_url,
        access_token=access_token,
        metrics_token=metrics_token,
        email=email,
        password=password,
        login_path=login_path,
        headers=parsed_headers,
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
    parser = argparse.ArgumentParser(
        description="Collect monitoring+alerting rollout-window evidence via authenticated endpoint reachability probes."
    )
    parser.add_argument("--endpoint", action="append", default=[], help="Endpoint override in the format name=url.")
    parser.add_argument("--header", action="append", default=[], help="Extra header in the format key=value.")
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--access-token", default="")
    parser.add_argument("--metrics-token", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--login-path", default="/api/auth/login")
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--output-dir", help="Evidence output directory, default backend/docs")
    parser.add_argument("--report-prefix", default="monitoring_alerting_evidence")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_monitoring_alerting_evidence(
        endpoint_specs=args.endpoint,
        header_specs=args.header,
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        backend_base_url=str(args.backend_base_url or "http://127.0.0.1:8080").strip(),
        access_token=str(args.access_token or "").strip() or None,
        metrics_token=str(args.metrics_token or "").strip() or None,
        email=str(args.email or "").strip() or None,
        password=str(args.password or "").strip() or None,
        login_path=str(args.login_path or "/api/auth/login").strip() or "/api/auth/login",
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
