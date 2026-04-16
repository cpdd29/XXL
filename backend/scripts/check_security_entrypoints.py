from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


def _function_call_names(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls_by_function: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        calls: set[str] = set()
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            name = _dotted_name(inner.func)
            if name:
                calls.add(name)
        calls_by_function[node.name] = calls
    return calls_by_function


def _check_function(
    *,
    file_path: Path,
    function_name: str,
    required_calls: tuple[str, ...],
) -> dict[str, Any]:
    call_map = _function_call_names(file_path)
    observed_calls = call_map.get(function_name, set())
    missing_calls = [name for name in required_calls if name not in observed_calls]
    return {
        "file": str(file_path.relative_to(REPO_ROOT)),
        "function": function_name,
        "ok": not missing_calls,
        "required_calls": list(required_calls),
        "observed_calls": sorted(observed_calls),
        "missing_calls": missing_calls,
    }


def run_security_entrypoint_check(*, repo_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = (repo_root or REPO_ROOT).resolve()
    messages_path = resolved_repo_root / "backend/app/api/routes/messages.py"
    webhooks_path = resolved_repo_root / "backend/app/api/routes/webhooks.py"
    checks = [
        _check_function(
            file_path=messages_path,
            function_name="ingest_message_route",
            required_calls=("ingest_unified_message",),
        ),
        _check_function(
            file_path=webhooks_path,
            function_name="_ingest_channel_webhook_route",
            required_calls=(
                "enforce_webhook_rate_limit",
                "enforce_webhook_payload_size",
                "_validate_channel_secret",
                "ingest_channel_webhook",
            ),
        ),
        _check_function(
            file_path=webhooks_path,
            function_name="telegram_webhook_route",
            required_calls=(
                "enforce_webhook_rate_limit",
                "enforce_webhook_payload_size",
                "ingest_telegram_webhook",
            ),
        ),
        _check_function(
            file_path=webhooks_path,
            function_name="workflow_webhook_route",
            required_calls=(
                "enforce_webhook_rate_limit",
                "enforce_webhook_payload_size",
                "security_gateway_service.inspect_text_entrypoint",
                "trigger_workflow_webhook",
            ),
        ),
    ]
    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "summary": {
            "total_checks": len(checks),
            "failed_checks": len([item for item in checks if not item["ok"]]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check external ingress entrypoints keep security coverage.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_security_entrypoint_check(repo_root=Path(args.repo_root))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
