from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Iterable


FORBIDDEN_IMPORT_PREFIXES = (
    "app.tentacle_adapters",
    "app.services.master_bot_service",
    "app.services.workflow_execution_service",
)
FORBIDDEN_TENTACLE_IMPORT_PREFIXES = (
    "app.brain_core",
    "app.services.memory_service",
    "app.services.message_ingestion_service",
    "app.services.persistence_service",
    "app.services.security_gateway_service",
    "app.services.task_service",
    "app.services.workflow_execution_service",
    "app.services.master_bot_service",
    "app.services.store",
    "app.db",
)
FORBIDDEN_EXECUTION_GATEWAY_IMPORT_PREFIXES = (
    "app.brain_core",
    "app.services.memory_service",
    "app.services.message_ingestion_service",
    "app.services.persistence_service",
    "app.services.security_gateway_service",
    "app.services.task_service",
    "app.services.workflow_execution_service",
    "app.services.master_bot_service",
    "app.services.store",
    "app.db",
)
FORBIDDEN_STATEFUL_SYMBOLS = {
    "store": {
        "tasks",
        "task_steps",
        "workflow_runs",
        "users",
        "user_profiles",
        "audit_logs",
    },
    "memory_service": None,
    "persistence_service": None,
}
ALLOWED_BUILTIN_SKILL_NAMES = {
    "task_status_skill",
    "task_list_skill",
}
ALLOWED_BUILTIN_SKILL_HANDLERS = {
    "_task_status_skill",
    "_task_list_skill",
}
MASTER_BOT_COMPAT_LAYER_MODULE = "app.services.master_bot_service"
MASTER_BOT_COMPAT_GUARDED_ROOTS = (
    ("brain_core", "brain_core_imports_master_bot_compat_layer"),
    ("execution_gateway", "new_core_layer_imports_master_bot_compat_layer"),
    ("tentacle_adapters", "new_core_layer_imports_master_bot_compat_layer"),
)
FORBIDDEN_BRAIN_SERVICE_PACKAGE_IMPORTS = {
    "master_bot_service": "app.services.master_bot_service",
    "workflow_execution_service": "app.services.workflow_execution_service",
}


def _iter_python_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in root.rglob("*.py"):
        if path.is_file():
            yield path


def _module_path_from_file(app_root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(app_root.parent).with_suffix("")
    return ".".join(relative.parts)


def _resolve_from_import(base_module: str, node: ast.ImportFrom) -> str:
    if node.level <= 0:
        return str(node.module or "")
    parts = base_module.split(".")
    if node.level > len(parts):
        return str(node.module or "")
    parent = parts[: -node.level]
    if node.module:
        parent.append(node.module)
    return ".".join(parent)


def find_violations(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    brain_core_root = app_root / "brain_core"
    violations: list[dict[str, str]] = []
    if not brain_core_root.exists():
        return violations

    for file_path in _iter_python_files(brain_core_root):
        source = file_path.read_text(encoding="utf-8")
        module_path = _module_path_from_file(app_root, file_path)
        tree = ast.parse(source, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                resolved = _resolve_from_import(module_path, node)
                targets = [resolved] if resolved else []
                if resolved == "app.services":
                    for alias in node.names:
                        alias_name = str(alias.name or "").strip()
                        target = FORBIDDEN_BRAIN_SERVICE_PACKAGE_IMPORTS.get(alias_name)
                        if not target:
                            continue
                        violations.append(
                            {
                                "file": str(file_path),
                                "line": str(getattr(node, "lineno", 0)),
                                "target": target,
                            }
                        )
            else:
                continue
            for target in targets:
                normalized = str(target or "").strip()
                if not normalized:
                    continue
                if any(
                    normalized == prefix or normalized.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(
                        {
                            "file": str(file_path),
                            "line": str(getattr(node, "lineno", 0)),
                            "target": normalized,
                        }
                    )
    return violations


def find_tentacle_boundary_violations(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    tentacle_root = app_root / "tentacle_adapters"
    violations: list[dict[str, str]] = []
    if not tentacle_root.exists():
        return violations

    for file_path in _iter_python_files(tentacle_root):
        source = file_path.read_text(encoding="utf-8")
        module_path = _module_path_from_file(app_root, file_path)
        tree = ast.parse(source, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                resolved = _resolve_from_import(module_path, node)
                targets = [resolved] if resolved else []
            else:
                continue
            for target in targets:
                normalized = str(target or "").strip()
                if not normalized:
                    continue
                if any(
                    normalized == prefix or normalized.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_TENTACLE_IMPORT_PREFIXES
                ):
                    violations.append(
                        {
                            "file": str(file_path),
                            "line": str(getattr(node, "lineno", 0)),
                            "target": normalized,
                            "reason": "tentacle_imports_brain_or_stateful_core",
                        }
                    )
    return violations


def find_execution_gateway_boundary_violations(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    gateway_root = app_root / "execution_gateway"
    violations: list[dict[str, str]] = []
    if not gateway_root.exists():
        return violations

    for file_path in _iter_python_files(gateway_root):
        source = file_path.read_text(encoding="utf-8")
        module_path = _module_path_from_file(app_root, file_path)
        tree = ast.parse(source, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                resolved = _resolve_from_import(module_path, node)
                targets = [resolved] if resolved else []
            else:
                continue
            for target in targets:
                normalized = str(target or "").strip()
                if not normalized:
                    continue
                if any(
                    normalized == prefix or normalized.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_EXECUTION_GATEWAY_IMPORT_PREFIXES
                ):
                    violations.append(
                        {
                            "file": str(file_path),
                            "line": str(getattr(node, "lineno", 0)),
                            "target": normalized,
                            "reason": "execution_gateway_imports_brain_or_stateful_core",
                        }
                    )
    return violations


def _iter_forbidden_stateful_symbol_violations(root: Path) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    if not root.exists():
        return violations

    for file_path in _iter_python_files(root):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name):
                continue
            base_name = str(node.value.id or "").strip()
            if base_name not in FORBIDDEN_STATEFUL_SYMBOLS:
                continue
            allowed_attrs = FORBIDDEN_STATEFUL_SYMBOLS[base_name]
            attribute_name = str(node.attr or "").strip()
            if allowed_attrs is not None and attribute_name not in allowed_attrs:
                continue
            violations.append(
                {
                    "file": str(file_path),
                    "line": str(getattr(node, "lineno", 0)),
                    "target": f"{base_name}.{attribute_name}",
                    "reason": "execution_or_tentacle_references_stateful_core",
                }
            )
    return violations


def find_stateful_core_usage_violations(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    return [
        *_iter_forbidden_stateful_symbol_violations(app_root / "execution_gateway"),
        *_iter_forbidden_stateful_symbol_violations(app_root / "tentacle_adapters"),
    ]


def find_builtin_skill_violations(project_root: Path) -> list[dict[str, str]]:
    service_path = project_root / "app" / "services" / "free_workflow_service.py"
    if not service_path.exists():
        return []

    source = service_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(service_path))
    violations: list[dict[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            function_name = str(node.name or "").strip()
            argument_names = [str(arg.arg or "").strip() for arg in node.args.args]
            looks_like_skill_handler = {"payload", "context", "ability"}.issubset(set(argument_names))
            if (
                function_name.startswith("_")
                and function_name.endswith("_skill")
                and looks_like_skill_handler
                and function_name not in ALLOWED_BUILTIN_SKILL_HANDLERS
            ):
                violations.append(
                    {
                        "file": str(service_path),
                        "line": str(getattr(node, "lineno", 0)),
                        "target": function_name,
                        "reason": "builtin_skill_handler_not_allowlisted",
                    }
                )
        elif isinstance(node, ast.Dict):
            keys = node.keys or []
            values = node.values or []
            for key, value in zip(keys, values):
                if not isinstance(key, ast.Constant) or key.value != "name":
                    continue
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                skill_name = str(value.value).strip()
                if skill_name.endswith("_skill") and skill_name not in ALLOWED_BUILTIN_SKILL_NAMES:
                    violations.append(
                        {
                            "file": str(service_path),
                            "line": str(getattr(value, "lineno", 0)),
                            "target": skill_name,
                            "reason": "builtin_skill_registration_not_allowlisted",
                        }
                    )
    return violations


def find_master_bot_compat_violations(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    service_path = app_root / "services" / "master_bot_service.py"
    violations: list[dict[str, str]] = []
    if not app_root.exists():
        return violations

    for relative_root, reason in MASTER_BOT_COMPAT_GUARDED_ROOTS:
        guarded_root = app_root / relative_root
        for file_path in _iter_python_files(guarded_root):
            if file_path == service_path:
                continue
            source = file_path.read_text(encoding="utf-8")
            module_path = _module_path_from_file(app_root, file_path)
            tree = ast.parse(source, filename=str(file_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        normalized = str(alias.name or "").strip()
                        if normalized == MASTER_BOT_COMPAT_LAYER_MODULE:
                            violations.append(
                                {
                                    "file": str(file_path),
                                    "line": str(getattr(node, "lineno", 0)),
                                    "target": normalized,
                                    "reason": reason,
                                }
                            )
                elif isinstance(node, ast.ImportFrom):
                    resolved = _resolve_from_import(module_path, node)
                    normalized = str(resolved or "").strip()
                    if normalized == MASTER_BOT_COMPAT_LAYER_MODULE:
                        violations.append(
                            {
                                "file": str(file_path),
                                "line": str(getattr(node, "lineno", 0)),
                                "target": normalized,
                                "reason": reason,
                            }
                        )
                    elif normalized == "app.services":
                        for alias in node.names:
                            if str(alias.name or "").strip() != "master_bot_service":
                                continue
                            violations.append(
                                {
                                    "file": str(file_path),
                                    "line": str(getattr(node, "lineno", 0)),
                                    "target": MASTER_BOT_COMPAT_LAYER_MODULE,
                                    "reason": reason,
                                }
                            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check architecture import boundaries.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Backend project root (default: backend/)",
    )
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    violations = [
        *find_violations(project_root),
        *find_tentacle_boundary_violations(project_root),
        *find_execution_gateway_boundary_violations(project_root),
        *find_stateful_core_usage_violations(project_root),
        *find_builtin_skill_violations(project_root),
        *find_master_bot_compat_violations(project_root),
    ]
    if not violations:
        print("architecture-boundary-check: OK")
        return 0

    print("architecture-boundary-check: FAILED")
    for item in violations:
        reason = str(item.get("reason") or "forbidden_import")
        if reason == "forbidden_import":
            print(f"- {item['file']}:{item['line']} imports forbidden module '{item['target']}'")
        else:
            print(f"- {item['file']}:{item['line']} violates {reason}: '{item['target']}'")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
