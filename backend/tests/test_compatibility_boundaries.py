from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_checker_module():
    backend_root = Path(__file__).resolve().parents[1]
    script_path = backend_root / "scripts" / "check_compatibility_boundaries.py"
    spec = importlib.util.spec_from_file_location("check_compatibility_boundaries", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detects_brain_core_importing_compat_layer(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    brain_dir = backend_root / "app" / "brain_core" / "routing"
    brain_dir.mkdir(parents=True)
    (brain_dir / "x.py").write_text(
        "from app.services.workflow_execution_service import create_workflow_run_for_task\n",
        encoding="utf-8",
    )

    violations = checker.find_brain_core_compat_import_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.workflow_execution_service"


def test_detects_entrypoint_decision_residue(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    service_dir = backend_root / "app" / "services"
    service_dir.mkdir(parents=True)
    (service_dir / "message_ingestion_service.py").write_text(
        "from app.brain_core.routing.rules import dispatch_intent\n",
        encoding="utf-8",
    )

    violations = checker.find_entrypoint_decision_residue(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.brain_core.routing.rules"
    assert violations[0]["reason"] == "entrypoint_imports_routing_rules_directly"


def test_detects_execution_gateway_bypass_candidate(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    service_dir = backend_root / "app" / "services"
    service_dir.mkdir(parents=True)
    (service_dir / "workflow_execution_service.py").write_text(
        "from app.services.mcp_runtime_service import mcp_runtime_service\n",
        encoding="utf-8",
    )

    violations = checker.find_execution_gateway_bypass_candidates(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.mcp_runtime_service"
    assert violations[0]["reason"] == "service_imports_runtime_outside_execution_gateway_allowlist"


def test_ignores_non_execution_catalog_runtime_touchpoint(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    service_dir = backend_root / "app" / "services"
    service_dir.mkdir(parents=True)
    (service_dir / "tool_catalog_service.py").write_text(
        "from app.services.mcp_runtime_service import mcp_runtime_service\n",
        encoding="utf-8",
    )

    violations = checker.find_execution_gateway_bypass_candidates(backend_root)
    assert violations == []


def test_collects_legacy_alias_references(tmp_path: Path) -> None:
    checker = _load_checker_module()
    scan_root = tmp_path / "scan"
    scan_root.mkdir(parents=True)
    (scan_root / "a.py").write_text(
        'ROUTING = "workflow_or_direct_agent_fallback"\n',
        encoding="utf-8",
    )

    references = checker.find_legacy_alias_references(scan_root)
    assert len(references) == 1
    assert references[0]["reference"] == "direct_agent_fallback"


def test_categorizes_legacy_alias_references() -> None:
    checker = _load_checker_module()

    assert (
        checker.categorize_legacy_alias_reference(
            {
                "file": "/tmp/backend/app/services/workflow_execution_service.py",
                "line": "1",
                "reference": "direct_agent_fallback",
                "snippet": 'LEGACY_DIRECT_AGENT_FALLBACK_MODE = "direct_agent_fallback"',
            }
        )
        == "constant_alias"
    )
    assert (
        checker.categorize_legacy_alias_reference(
            {
                "file": "/tmp/backend/app/brain_core/routing/service.py",
                "line": "2",
                "reference": "direct_agent_fallback",
                "snippet": 'mode = "direct_agent_fallback"',
            }
        )
        == "string_literal"
    )
    assert (
        checker.categorize_legacy_alias_reference(
            {
                "file": "/tmp/backend/tests/test_routing.py",
                "line": "3",
                "reference": "direct_agent_dispatch",
                "snippet": 'assert dispatch_type == "direct_agent_dispatch"',
            }
        )
        == "test_wrapper"
    )
    assert (
        checker.categorize_legacy_alias_reference(
            {
                "file": "/tmp/backend/app/brain_core/coordinator/service.py",
                "line": "4",
                "reference": "direct_agent_dispatch",
                "snippet": "dispatch = plan.direct_agent_dispatch",
            }
        )
        == "property_alias"
    )
    assert (
        checker.categorize_legacy_alias_reference(
            {
                "file": "/tmp/backend/app/services/workflow_execution_service.py",
                "line": "5",
                "reference": "direct_agent_run_for_task",
                "snippet": "return create_direct_agent_run_for_task(task)",
            }
        )
        == "wrapper_alias"
    )


def test_groups_legacy_alias_references_by_category() -> None:
    checker = _load_checker_module()
    grouped = checker.group_legacy_alias_references_by_category(
        [
            {
                "file": "/tmp/backend/tests/test_routing.py",
                "line": "1",
                "reference": "direct_agent_dispatch",
                "snippet": 'assert mode == "direct_agent_dispatch"',
            },
            {
                "file": "/tmp/backend/app/brain_core/routing/service.py",
                "line": "2",
                "reference": "direct_agent_fallback",
                "snippet": 'mode = "direct_agent_fallback"',
            },
        ]
    )
    assert len(grouped["test_wrapper"]) == 1
    assert len(grouped["string_literal"]) == 1
    assert grouped["property_alias"] == []


def test_detects_unexpected_production_legacy_alias_growth() -> None:
    checker = _load_checker_module()
    references = [
        {
            "file": "/tmp/backend/app/brain_core/orchestration/service.py",
            "line": "1",
            "reference": "direct_agent_dispatch",
            "snippet": "direct_agent_dispatch = True",
        },
        {
            "file": "/tmp/backend/app/brain_core/orchestration/service.py",
            "line": "2",
            "reference": "direct_agent_dispatch",
            "snippet": "agent_dispatch = bool(direct_agent_dispatch)",
        },
        {
            "file": "/tmp/backend/app/brain_core/orchestration/service.py",
            "line": "3",
            "reference": "direct_agent_dispatch",
            "snippet": "return direct_agent_dispatch",
        },
        {
            "file": "/tmp/backend/app/brain_core/orchestration/service.py",
            "line": "4",
            "reference": "direct_agent_dispatch",
            "snippet": "another_direct_agent_dispatch = direct_agent_dispatch",
        },
    ]

    unexpected = checker.find_unexpected_production_legacy_alias_growth(
        references,
        scan_root=Path("/tmp/backend"),
    )

    assert len(unexpected) == 4
    assert {item["relative_file"] for item in unexpected} == {
        "app/brain_core/orchestration/service.py"
    }
    assert {item["category"] for item in unexpected} == {"identifier_alias"}
    assert {item["allowed_count"] for item in unexpected} == {"0"}
    assert {item["observed_count"] for item in unexpected} == {"4"}


def test_strict_mode_fails_when_required_compat_inventory_missing(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    (backend_root / "app" / "services").mkdir(parents=True)
    (backend_root / "app" / "services" / "master_bot_service.py").write_text("", encoding="utf-8")
    (backend_root / "app" / "services" / "message_ingestion_service.py").write_text("", encoding="utf-8")

    exit_code = checker.main(["--root", str(backend_root), "--strict"])
    assert exit_code == 1


def test_strict_mode_fails_when_unexpected_legacy_alias_growth_detected(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    (backend_root / "app" / "services").mkdir(parents=True)
    (backend_root / "app" / "brain_core").mkdir(parents=True)
    (backend_root / "app" / "services" / "master_bot_service.py").write_text("", encoding="utf-8")
    (backend_root / "app" / "services" / "message_ingestion_service.py").write_text("", encoding="utf-8")
    (backend_root / "app" / "services" / "workflow_execution_service.py").write_text("", encoding="utf-8")
    (backend_root / "app" / "brain_core" / "x.py").write_text(
        'ROUTING = "workflow_or_direct_agent_fallback"\n',
        encoding="utf-8",
    )

    exit_code = checker.main(["--root", str(backend_root), "--scan-root", str(backend_root), "--strict"])
    assert exit_code == 1
