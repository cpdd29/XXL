from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_checker_module():
    backend_root = Path(__file__).resolve().parents[1]
    script_path = backend_root / "scripts" / "check_architecture_boundaries.py"
    spec = importlib.util.spec_from_file_location("check_architecture_boundaries", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detects_forbidden_tentacle_import(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    brain_dir = backend_root / "app" / "brain_core" / "routing"
    brain_dir.mkdir(parents=True)
    (brain_dir / "x.py").write_text(
        "import app.tentacle_adapters.search_adapter\n",
        encoding="utf-8",
    )

    violations = checker.find_violations(backend_root)
    assert len(violations) == 1
    assert "app.tentacle_adapters.search_adapter" == violations[0]["target"]


def test_allows_execution_gateway_import(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    brain_dir = backend_root / "app" / "brain_core" / "routing"
    brain_dir.mkdir(parents=True)
    (brain_dir / "x.py").write_text(
        "from app.execution_gateway.contracts import ExecutionRequest\n",
        encoding="utf-8",
    )

    violations = checker.find_violations(backend_root)
    assert violations == []


def test_detects_non_allowlisted_builtin_skill_handler(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    service_dir = backend_root / "app" / "services"
    service_dir.mkdir(parents=True)
    (service_dir / "free_workflow_service.py").write_text(
        """
class FreeWorkflowService:
    def _browser_automation_skill(self, payload, context, ability):
        return {}
""".strip(),
        encoding="utf-8",
    )

    violations = checker.find_builtin_skill_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "_browser_automation_skill"
    assert violations[0]["reason"] == "builtin_skill_handler_not_allowlisted"


def test_detects_non_allowlisted_builtin_skill_registration(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    service_dir = backend_root / "app" / "services"
    service_dir.mkdir(parents=True)
    (service_dir / "free_workflow_service.py").write_text(
        """
class FreeWorkflowService:
    def _register_builtin_skills(self):
        skills = [
            {"name": "browser_automation_skill", "handler": self._browser_automation_skill},
        ]
        return skills
""".strip(),
        encoding="utf-8",
    )

    violations = checker.find_builtin_skill_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "browser_automation_skill"
    assert violations[0]["reason"] == "builtin_skill_registration_not_allowlisted"


def test_current_repository_builtin_skill_allowlist_passes() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_builtin_skill_violations(backend_root)
    assert violations == []


def test_current_repository_brain_core_passes() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_violations(backend_root)
    assert violations == []
