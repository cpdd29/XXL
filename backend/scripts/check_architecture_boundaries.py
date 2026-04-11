from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Iterable


FORBIDDEN_IMPORT_PREFIXES = (
    "app.tentacle_adapters",
)
ALLOWED_BUILTIN_SKILL_NAMES = {
    "task_status_skill",
    "task_list_skill",
}
ALLOWED_BUILTIN_SKILL_HANDLERS = {
    "_task_status_skill",
    "_task_list_skill",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check architecture import boundaries.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Backend project root (default: backend/)",
    )
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    violations = [*find_violations(project_root), *find_builtin_skill_violations(project_root)]
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
