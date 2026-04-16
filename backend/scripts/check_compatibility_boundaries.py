from __future__ import annotations

import argparse
import ast
from collections import Counter
import re
from pathlib import Path
from typing import Iterable

REQUIRED_COMPAT_SHELL_FILES = (
    "app/services/master_bot_service.py",
    "app/services/message_ingestion_service.py",
    "app/services/workflow_execution_service.py",
)
ENTRYPOINT_COMPAT_SHELL_FILES = (
    "app/services/master_bot_service.py",
    "app/services/message_ingestion_service.py",
)
COMPAT_IMPORT_MODULES = {
    "master_bot_service": "app.services.master_bot_service",
    "message_ingestion_service": "app.services.message_ingestion_service",
    "workflow_execution_service": "app.services.workflow_execution_service",
}
ENTRYPOINT_DECISION_MODULE = "app.brain_core.routing.rules"
EXECUTION_RUNTIME_MODULES = {
    "app.services.mcp_runtime_service",
    "app.services.skill_runtime_service",
}
EXECUTION_BYPASS_SCAN_FILES = (
    "app/services/message_ingestion_service.py",
    "app/services/workflow_execution_service.py",
    "app/services/agent_execution_service.py",
    "app/brain_core/orchestration/service.py",
)
LEGACY_ALIAS_PATTERN = re.compile(r"direct_agent_[A-Za-z0-9_]*")
LEGACY_ALIAS_CATEGORIES = (
    "constant_alias",
    "string_literal",
    "test_wrapper",
    "property_alias",
    "wrapper_alias",
    "identifier_alias",
)
SCAN_FILE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
}
DEFAULT_SCAN_EXCLUDE_FILES = {
    "scripts/check_compatibility_boundaries.py",
    "tests/test_compatibility_boundaries.py",
}
FROZEN_PRODUCTION_RESIDUE_BASELINE = {
    ("app/services/workflow_execution_service.py", "direct_agent_fallback__", "constant_alias"): 1,
    ("app/services/workflow_execution_service.py", "direct_agent_dispatch", "constant_alias"): 1,
    ("app/services/workflow_execution_service.py", "direct_agent_fallback", "constant_alias"): 1,
    ("app/brain_core/routing/service.py", "direct_agent_fallback", "constant_alias"): 1,
}


def _is_test_file(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    filename = normalized.rsplit("/", maxsplit=1)[-1]
    return "/tests/" in normalized or filename.startswith("test_")


def _is_constant_assignment(snippet: str) -> bool:
    return bool(re.match(r"^\s*[A-Z][A-Z0-9_]*\s*=", snippet))


def _contains_string_literal_reference(snippet: str, reference: str) -> bool:
    escaped = re.escape(reference)
    return bool(re.search(rf"""["'][^"'\n]*{escaped}[^"'\n]*["']""", snippet))


def _contains_property_reference(snippet: str, reference: str) -> bool:
    return bool(re.search(rf"\.{re.escape(reference)}\b", snippet))


def _contains_wrapper_reference(snippet: str, reference: str) -> bool:
    escaped = re.escape(reference)
    return bool(re.search(rf"\b[A-Za-z_][A-Za-z0-9_]*{escaped}\s*\(", snippet))


def categorize_legacy_alias_reference(reference: dict[str, str]) -> str:
    file_path = reference.get("file", "")
    snippet = reference.get("snippet", "")
    alias = reference.get("reference", "")

    if _is_test_file(file_path):
        return "test_wrapper"
    if _is_constant_assignment(snippet):
        return "constant_alias"
    if _contains_string_literal_reference(snippet, alias):
        return "string_literal"
    if _contains_property_reference(snippet, alias):
        return "property_alias"
    if _contains_wrapper_reference(snippet, alias):
        return "wrapper_alias"
    return "identifier_alias"


def group_legacy_alias_references_by_category(
    references: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for category in LEGACY_ALIAS_CATEGORIES:
        grouped[category] = []

    for item in references:
        category = categorize_legacy_alias_reference(item)
        grouped.setdefault(category, []).append(item)
    return grouped


def partition_legacy_alias_references(
    references: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    production_residue: list[dict[str, str]] = []
    compat_test_residue: list[dict[str, str]] = []
    for item in references:
        if _is_test_file(item.get("file", "")):
            compat_test_residue.append(item)
        else:
            production_residue.append(item)
    return production_residue, compat_test_residue


def _relative_reference_file(scan_root: Path, file_path: str) -> str:
    try:
        return Path(file_path).resolve().relative_to(scan_root.resolve()).as_posix()
    except ValueError:
        return Path(file_path).as_posix()


def _legacy_reference_key(
    reference: dict[str, str],
    *,
    scan_root: Path,
) -> tuple[str, str, str]:
    return (
        _relative_reference_file(scan_root, reference.get("file", "")),
        str(reference.get("reference") or "").strip(),
        categorize_legacy_alias_reference(reference),
    )


def summarize_production_legacy_alias_counts(
    references: list[dict[str, str]],
    *,
    scan_root: Path,
) -> Counter[tuple[str, str, str]]:
    production_residue, _compat_test_residue = partition_legacy_alias_references(references)
    counts: Counter[tuple[str, str, str]] = Counter()
    for item in production_residue:
        counts[_legacy_reference_key(item, scan_root=scan_root)] += 1
    return counts


def find_unexpected_production_legacy_alias_growth(
    references: list[dict[str, str]],
    *,
    scan_root: Path,
) -> list[dict[str, str]]:
    observed_counts = summarize_production_legacy_alias_counts(references, scan_root=scan_root)
    unexpected: list[dict[str, str]] = []
    for item in references:
        if _is_test_file(item.get("file", "")):
            continue
        key = _legacy_reference_key(item, scan_root=scan_root)
        allowed_count = int(FROZEN_PRODUCTION_RESIDUE_BASELINE.get(key, 0))
        if allowed_count <= 0:
            unexpected.append(
                {
                    **item,
                    "category": key[2],
                    "relative_file": key[0],
                    "allowed_count": "0",
                    "observed_count": str(observed_counts.get(key, 0)),
                }
            )
            continue
        remaining = observed_counts.get(key, 0)
        if remaining <= allowed_count:
            continue
        observed_counts[key] = remaining - 1
        unexpected.append(
            {
                **item,
                "category": key[2],
                "relative_file": key[0],
                "allowed_count": str(allowed_count),
                "observed_count": str(remaining),
            }
        )
    return unexpected


def _iter_python_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in root.rglob("*.py"):
        if path.is_file():
            yield path


def _iter_scannable_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in SCAN_FILE_EXTENSIONS:
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


def _iter_normalized_imports(file_path: Path, app_root: Path) -> Iterable[dict[str, str]]:
    source = file_path.read_text(encoding="utf-8")
    module_path = _module_path_from_file(app_root, file_path)
    tree = ast.parse(source, filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                normalized = str(alias.name or "").strip()
                if normalized:
                    yield {
                        "file": str(file_path),
                        "line": str(getattr(node, "lineno", 0)),
                        "target": normalized,
                    }
        elif isinstance(node, ast.ImportFrom):
            resolved = str(_resolve_from_import(module_path, node) or "").strip()
            if resolved:
                yield {
                    "file": str(file_path),
                    "line": str(getattr(node, "lineno", 0)),
                    "target": resolved,
                }
            if resolved == "app.brain_core.routing":
                for alias in node.names:
                    if str(alias.name or "").strip() != "rules":
                        continue
                    yield {
                        "file": str(file_path),
                        "line": str(getattr(node, "lineno", 0)),
                        "target": ENTRYPOINT_DECISION_MODULE,
                    }
            if resolved == "app.services":
                for alias in node.names:
                    alias_name = str(alias.name or "").strip()
                    if alias_name not in {"mcp_runtime_service", "skill_runtime_service"}:
                        continue
                    yield {
                        "file": str(file_path),
                        "line": str(getattr(node, "lineno", 0)),
                        "target": f"app.services.{alias_name}",
                    }


def collect_compat_shell_inventory(project_root: Path) -> dict[str, list[str]]:
    existing: list[str] = []
    missing: list[str] = []
    for relative_path in REQUIRED_COMPAT_SHELL_FILES:
        full_path = project_root / relative_path
        if full_path.exists():
            existing.append(relative_path)
        else:
            missing.append(relative_path)
    return {"existing": existing, "missing": missing}


def find_brain_core_compat_import_violations(project_root: Path) -> list[dict[str, str]]:
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
                for alias in node.names:
                    imported = str(alias.name or "").strip()
                    if imported in COMPAT_IMPORT_MODULES.values():
                        violations.append(
                            {
                                "file": str(file_path),
                                "line": str(getattr(node, "lineno", 0)),
                                "target": imported,
                            }
                        )
            elif isinstance(node, ast.ImportFrom):
                resolved = str(_resolve_from_import(module_path, node) or "").strip()
                if resolved in COMPAT_IMPORT_MODULES.values():
                    violations.append(
                        {
                            "file": str(file_path),
                            "line": str(getattr(node, "lineno", 0)),
                            "target": resolved,
                        }
                    )
                    continue
                if resolved == "app.services":
                    for alias in node.names:
                        alias_name = str(alias.name or "").strip()
                        target = COMPAT_IMPORT_MODULES.get(alias_name)
                        if not target:
                            continue
                        violations.append(
                            {
                                "file": str(file_path),
                                "line": str(getattr(node, "lineno", 0)),
                                "target": target,
                            }
                        )
    return violations


def find_entrypoint_decision_residue(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    residues: list[dict[str, str]] = []
    for relative_path in ENTRYPOINT_COMPAT_SHELL_FILES:
        file_path = project_root / relative_path
        if not file_path.exists():
            continue
        for item in _iter_normalized_imports(file_path, app_root):
            if item["target"] != ENTRYPOINT_DECISION_MODULE:
                continue
            residues.append(
                {
                    **item,
                    "reason": "entrypoint_imports_routing_rules_directly",
                }
            )
    return residues


def find_execution_gateway_bypass_candidates(project_root: Path) -> list[dict[str, str]]:
    app_root = project_root / "app"
    violations: list[dict[str, str]] = []
    for relative_path in EXECUTION_BYPASS_SCAN_FILES:
        file_path = project_root / relative_path
        if not file_path.exists():
            continue
        for item in _iter_normalized_imports(file_path, app_root):
            if item["target"] not in EXECUTION_RUNTIME_MODULES:
                continue
            violations.append(
                {
                    **item,
                    "reason": "service_imports_runtime_outside_execution_gateway_allowlist",
                }
            )
    return violations


def find_legacy_alias_references(scan_root: Path) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for file_path in _iter_scannable_files(scan_root):
        relative_path = file_path.relative_to(scan_root).as_posix()
        if relative_path in DEFAULT_SCAN_EXCLUDE_FILES:
            continue
        try:
            source = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(source.splitlines(), start=1):
            matches = sorted(set(LEGACY_ALIAS_PATTERN.findall(line)))
            for match in matches:
                references.append(
                    {
                        "file": str(file_path),
                        "line": str(line_number),
                        "reference": match,
                        "snippet": line.strip(),
                    }
                )
    return references


def _print_inventory(
    project_root: Path,
    scan_root: Path,
) -> tuple[
    dict[str, list[str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    inventory = collect_compat_shell_inventory(project_root)
    compat_import_violations = find_brain_core_compat_import_violations(project_root)
    legacy_alias_references = find_legacy_alias_references(scan_root)
    entrypoint_decision_residue = find_entrypoint_decision_residue(project_root)
    execution_gateway_bypass_candidates = find_execution_gateway_bypass_candidates(project_root)
    unexpected_legacy_alias_growth = find_unexpected_production_legacy_alias_growth(
        legacy_alias_references,
        scan_root=scan_root,
    )

    print("compatibility-boundaries-inventory:")
    print("compat-shell-files-existing:")
    if inventory["existing"]:
        for relative_path in inventory["existing"]:
            print(f"- {relative_path}")
    else:
        print("- <none>")

    print("compat-shell-files-missing:")
    if inventory["missing"]:
        for relative_path in inventory["missing"]:
            print(f"- {relative_path}")
    else:
        print("- <none>")

    print("brain-core-direct-imports-to-compat-layer:")
    if compat_import_violations:
        for item in compat_import_violations:
            print(f"- {item['file']}:{item['line']} imports {item['target']}")
    else:
        print("- <none>")

    print("entrypoint-decision-residue:")
    if entrypoint_decision_residue:
        for item in entrypoint_decision_residue:
            print(f"- {item['file']}:{item['line']} imports {item['target']}")
    else:
        print("- <none>")

    print("execution-gateway-bypass-candidates:")
    if execution_gateway_bypass_candidates:
        for item in execution_gateway_bypass_candidates:
            print(f"- {item['file']}:{item['line']} imports {item['target']}")
    else:
        print("- <none>")

    print("legacy-direct-agent-references:")
    production_residue, compat_test_residue = partition_legacy_alias_references(legacy_alias_references)
    print(
        "  note: production residue indicates non-test files; compat test residue indicates intentional test coverage."
    )
    print(f"- production-residue-total: {len(production_residue)}")
    if production_residue:
        grouped = group_legacy_alias_references_by_category(production_residue)
        for category in LEGACY_ALIAS_CATEGORIES:
            items = grouped.get(category, [])
            if not items:
                continue
            print(f"  - {category} ({len(items)})")
            for item in items:
                print(f"    - {item['file']}:{item['line']} [{item['reference']}] {item['snippet']}")
    else:
        print("  - <none>")
    print(f"- compat-test-residue-total: {len(compat_test_residue)}")
    if compat_test_residue:
        grouped = group_legacy_alias_references_by_category(compat_test_residue)
        for category in LEGACY_ALIAS_CATEGORIES:
            items = grouped.get(category, [])
            if not items:
                continue
            print(f"  - {category} ({len(items)})")
            for item in items:
                print(f"    - {item['file']}:{item['line']} [{item['reference']}] {item['snippet']}")
    else:
        print("  - <none>")
    print(f"frozen-production-residue-baseline-total: {sum(FROZEN_PRODUCTION_RESIDUE_BASELINE.values())}")
    print("unexpected-production-residue-growth:")
    if unexpected_legacy_alias_growth:
        for item in unexpected_legacy_alias_growth:
            print(
                f"- {item['file']}:{item['line']} [{item['reference']}] "
                f"category={item['category']} observed={item['observed_count']} allowed={item['allowed_count']}"
            )
    else:
        print("- <none>")
    return (
        inventory,
        compat_import_violations,
        legacy_alias_references,
        entrypoint_decision_residue,
        execution_gateway_bypass_candidates,
        unexpected_legacy_alias_growth,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit compatibility shells and legacy direct_agent naming.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Backend project root (default: backend/)",
    )
    parser.add_argument(
        "--scan-root",
        default="",
        help="Root directory for legacy direct_agent_* reference scan (default: same as --root).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when brain_core imports compat layers directly or required compat shell inventory is missing.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.root).resolve()
    scan_root = Path(args.scan_root).resolve() if args.scan_root else project_root
    (
        inventory,
        compat_import_violations,
        _legacy_alias_references,
        entrypoint_decision_residue,
        execution_gateway_bypass_candidates,
        unexpected_legacy_alias_growth,
    ) = _print_inventory(project_root, scan_root)

    if not args.strict:
        return 0

    strict_failures: list[str] = []
    if inventory["missing"]:
        strict_failures.append("required_compat_shell_inventory_incomplete")
    if compat_import_violations:
        strict_failures.append("brain_core_imports_compat_layer_directly")
    if entrypoint_decision_residue:
        strict_failures.append("entrypoint_decision_residue_detected")
    if execution_gateway_bypass_candidates:
        strict_failures.append("execution_gateway_bypass_candidates_detected")
    if unexpected_legacy_alias_growth:
        strict_failures.append("unexpected_legacy_alias_growth_detected")

    if not strict_failures:
        print("compatibility-boundaries-strict: OK")
        return 0

    print("compatibility-boundaries-strict: FAILED")
    for item in strict_failures:
        print(f"- {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
