from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


ROUTE_FILES = (
    "backend/app/modules/reception/api/messages.py",
    "backend/app/modules/reception/api/webhooks.py",
    "backend/app/api/routes/external_connections.py",
)

PUBLIC_PROTECTION_RULES = (
    ("secret_or_signature", ("_require_external_auth", "verify_external_request", "_validate_channel_secret")),
    ("rate_limit", ("enforce_webhook_rate_limit",)),
    ("payload_size", ("enforce_webhook_payload_size",)),
    (
        "security_gateway",
        (
            "security_gateway_service.inspect_text_entrypoint",
            "ingest_unified_message",
        ),
    ),
    ("authenticated_user", ("require_authenticated_user",)),
)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return None


def _is_router_decorator(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "router"


def _decorator_path(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return None


def _decorator_dependencies(node: ast.Call) -> set[str]:
    deps: set[str] = set()
    for keyword in node.keywords:
        if keyword.arg != "dependencies":
            continue
        if not isinstance(keyword.value, ast.List):
            continue
        for item in keyword.value.elts:
            if not isinstance(item, ast.Call):
                continue
            if _dotted_name(item.func) != "Depends":
                continue
            if not item.args:
                continue
            dep_name = _dotted_name(item.args[0])
            if dep_name:
                deps.add(dep_name)
    return deps


def _function_call_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    calls: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            name = _dotted_name(inner.func)
            if name:
                calls.add(name)
    return calls


def _function_param_dependency_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for argument in node.args.args:
        default_node: ast.AST | None = None
        if node.args.defaults and argument in node.args.args[-len(node.args.defaults) :]:
            offset = node.args.args.index(argument) - (len(node.args.args) - len(node.args.defaults))
            default_node = node.args.defaults[offset]
        if not isinstance(default_node, ast.Call):
            continue
        if _dotted_name(default_node.func) != "Depends":
            continue
        if not default_node.args:
            continue
        dep_name = _dotted_name(default_node.args[0])
        if dep_name:
            names.add(dep_name)
    return names


def _route_records_for_file(path: Path) -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    local_functions = {node.name: node for node in function_nodes}

    call_graph: dict[str, set[str]] = {name: _function_call_names(node) for name, node in local_functions.items()}
    param_dependencies: dict[str, set[str]] = {
        name: _function_param_dependency_names(node) for name, node in local_functions.items()
    }

    def call_closure(function_name: str) -> set[str]:
        visited: set[str] = set()
        accumulated: set[str] = set()
        stack = [function_name]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            direct_calls = call_graph.get(current, set())
            accumulated.update(direct_calls)
            for called in direct_calls:
                if called in local_functions:
                    stack.append(called)
        return accumulated

    routes: list[dict[str, Any]] = []
    for node in function_nodes:
        decorators = [item for item in node.decorator_list if _is_router_decorator(item)]
        if not decorators:
            continue
        for decorator in decorators:
            assert isinstance(decorator, ast.Call)
            method = decorator.func.attr.lower()
            route_path = _decorator_path(decorator) or ""
            decorator_deps = _decorator_dependencies(decorator)
            closure_calls = call_closure(node.name)
            dependency_names = decorator_deps | param_dependencies.get(node.name, set())
            routes.append(
                {
                    "file": str(path.relative_to(REPO_ROOT)),
                    "function": node.name,
                    "method": method,
                    "path": route_path,
                    "calls": sorted(closure_calls),
                    "dependencies": sorted(dependency_names),
                }
            )
    return routes


def _classify_route(route: dict[str, Any]) -> str:
    dependency_names = set(route["dependencies"])
    if "require_authenticated_user" in dependency_names:
        return "authenticated_control_plane"
    return "public_external_ingress"


def _protection_summary(route: dict[str, Any]) -> dict[str, Any]:
    observed = set(route["calls"]) | set(route["dependencies"])
    matched: list[str] = []
    missing: list[str] = []
    matched_details: dict[str, list[str]] = {}
    for key, candidates in PUBLIC_PROTECTION_RULES:
        selected = [candidate for candidate in candidates if candidate in observed]
        if selected:
            matched.append(key)
            matched_details[key] = selected
        else:
            missing.append(key)
            matched_details[key] = []
    return {
        "matched": matched,
        "missing": missing,
        "matched_details": matched_details,
        "is_protected": bool(matched),
    }


def run_external_ingress_bypass_check(*, repo_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = (repo_root or REPO_ROOT).resolve()
    routes: list[dict[str, Any]] = []
    for relative in ROUTE_FILES:
        routes.extend(_route_records_for_file(resolved_repo_root / relative))

    annotated: list[dict[str, Any]] = []
    public_failed: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    for route in routes:
        route_type = _classify_route(route)
        protection = _protection_summary(route)
        row = {
            **route,
            "route_type": route_type,
            "protection_summary": protection,
        }
        annotated.append(row)
        if route_type == "public_external_ingress" and not protection["is_protected"]:
            public_failed.append(
                {
                    "file": row["file"],
                    "function": row["function"],
                    "method": row["method"],
                    "path": row["path"],
                    "reason": "missing_baseline_protection",
                    "missing_protections": protection["missing"],
                }
            )
        if route_type == "public_external_ingress":
            manual_review.append(
                {
                    "file": row["file"],
                    "function": row["function"],
                    "method": row["method"],
                    "path": row["path"],
                    "matched_protections": protection["matched"],
                    "reason": "static_check_only_needs_runtime_verification",
                }
            )

    return {
        "ok": not public_failed,
        "summary": {
            "total_routes": len(annotated),
            "public_external_ingress_routes": len([r for r in annotated if r["route_type"] == "public_external_ingress"]),
            "authenticated_control_plane_routes": len(
                [r for r in annotated if r["route_type"] == "authenticated_control_plane"]
            ),
            "failed_public_routes": len(public_failed),
            "manual_review_required": len(manual_review),
        },
        "routes": annotated,
        "failed_public_routes": public_failed,
        "manual_review_required": manual_review,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check external ingress bypass risks with static route scan.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_external_ingress_bypass_check(repo_root=Path(args.repo_root))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
