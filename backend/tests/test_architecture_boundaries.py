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


def test_detects_brain_core_importing_master_bot_compat_layer(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    brain_dir = backend_root / "app" / "brain_core" / "routing"
    brain_dir.mkdir(parents=True)
    (brain_dir / "x.py").write_text(
        "from app.services.master_bot_service import dispatch_intent\n",
        encoding="utf-8",
    )

    violations = checker.find_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.master_bot_service"


def test_detects_brain_core_importing_workflow_execution_service(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    brain_dir = backend_root / "app" / "brain_core" / "routing"
    brain_dir.mkdir(parents=True)
    (brain_dir / "x.py").write_text(
        "from app.services.workflow_execution_service import resolve_workflow_execution_agent\n",
        encoding="utf-8",
    )

    violations = checker.find_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.workflow_execution_service"


def test_detects_brain_core_importing_workflow_execution_service_from_services_package(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    brain_dir = backend_root / "app" / "brain_core" / "routing"
    brain_dir.mkdir(parents=True)
    (brain_dir / "x.py").write_text(
        "from app.services import workflow_execution_service\n",
        encoding="utf-8",
    )

    violations = checker.find_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.workflow_execution_service"


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


def test_detects_tentacle_importing_brain_core(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    tentacle_dir = backend_root / "app" / "tentacle_adapters"
    tentacle_dir.mkdir(parents=True)
    (tentacle_dir / "x.py").write_text(
        "from app.brain_core.routing.service import RoutingService\n",
        encoding="utf-8",
    )

    violations = checker.find_tentacle_boundary_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.brain_core.routing.service"
    assert violations[0]["reason"] == "tentacle_imports_brain_or_stateful_core"


def test_detects_tentacle_importing_stateful_service(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    tentacle_dir = backend_root / "app" / "tentacle_adapters"
    tentacle_dir.mkdir(parents=True)
    (tentacle_dir / "x.py").write_text(
        "from app.services.memory_service import memory_service\n",
        encoding="utf-8",
    )

    violations = checker.find_tentacle_boundary_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.memory_service"
    assert violations[0]["reason"] == "tentacle_imports_brain_or_stateful_core"


def test_detects_execution_gateway_importing_stateful_service(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    gateway_dir = backend_root / "app" / "execution_gateway"
    gateway_dir.mkdir(parents=True)
    (gateway_dir / "x.py").write_text(
        "from app.services.workflow_execution_service import create_workflow_run_for_task\n",
        encoding="utf-8",
    )

    violations = checker.find_execution_gateway_boundary_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.workflow_execution_service"
    assert violations[0]["reason"] == "execution_gateway_imports_brain_or_stateful_core"


def test_detects_stateful_core_usage_from_tentacle_adapter(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    tentacle_dir = backend_root / "app" / "tentacle_adapters"
    tentacle_dir.mkdir(parents=True)
    (tentacle_dir / "x.py").write_text(
        "def run():\n    return store.tasks\n",
        encoding="utf-8",
    )

    violations = checker.find_stateful_core_usage_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "store.tasks"
    assert violations[0]["reason"] == "execution_or_tentacle_references_stateful_core"


def test_detects_stateful_core_usage_from_execution_gateway(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    gateway_dir = backend_root / "app" / "execution_gateway"
    gateway_dir.mkdir(parents=True)
    (gateway_dir / "x.py").write_text(
        "def run():\n    return persistence_service.persist_runtime_state()\n",
        encoding="utf-8",
    )

    violations = checker.find_stateful_core_usage_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "persistence_service.persist_runtime_state"
    assert violations[0]["reason"] == "execution_or_tentacle_references_stateful_core"


def test_current_repository_tentacle_boundaries_pass() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_tentacle_boundary_violations(backend_root)
    assert violations == []


def test_current_repository_execution_gateway_boundaries_pass() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_execution_gateway_boundary_violations(backend_root)
    assert violations == []


def test_current_repository_stateful_core_usage_boundaries_pass() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_stateful_core_usage_violations(backend_root)
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


def test_detects_master_bot_compat_import_from_module_path(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    app_services_dir = backend_root / "app" / "services"
    app_services_dir.mkdir(parents=True)
    (app_services_dir / "master_bot_service.py").write_text(
        "class MasterBotService:\n    pass\n",
        encoding="utf-8",
    )
    app_core_dir = backend_root / "app" / "brain_core" / "routing"
    app_core_dir.mkdir(parents=True)
    (app_core_dir / "x.py").write_text(
        "from app.services.master_bot_service import master_bot_service\n",
        encoding="utf-8",
    )

    violations = checker.find_master_bot_compat_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.master_bot_service"
    assert violations[0]["reason"] == "brain_core_imports_master_bot_compat_layer"


def test_detects_master_bot_compat_import_from_services_package(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    app_services_dir = backend_root / "app" / "services"
    app_services_dir.mkdir(parents=True)
    (app_services_dir / "master_bot_service.py").write_text(
        "class MasterBotService:\n    pass\n",
        encoding="utf-8",
    )
    app_core_dir = backend_root / "app" / "brain_core" / "routing"
    app_core_dir.mkdir(parents=True)
    (app_core_dir / "x.py").write_text(
        "from app.services import master_bot_service\n",
        encoding="utf-8",
    )

    violations = checker.find_master_bot_compat_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.master_bot_service"
    assert violations[0]["reason"] == "brain_core_imports_master_bot_compat_layer"


def test_detects_new_core_layer_importing_master_bot_compat_layer(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    app_services_dir = backend_root / "app" / "services"
    app_services_dir.mkdir(parents=True)
    (app_services_dir / "master_bot_service.py").write_text(
        "class MasterBotService:\n    pass\n",
        encoding="utf-8",
    )
    gateway_dir = backend_root / "app" / "execution_gateway" / "runner"
    gateway_dir.mkdir(parents=True)
    (gateway_dir / "x.py").write_text(
        "from app.services.master_bot_service import master_bot_service\n",
        encoding="utf-8",
    )

    violations = checker.find_master_bot_compat_violations(backend_root)
    assert len(violations) == 1
    assert violations[0]["target"] == "app.services.master_bot_service"
    assert violations[0]["reason"] == "new_core_layer_imports_master_bot_compat_layer"


def test_allows_non_core_layer_importing_master_bot_compat_layer(tmp_path: Path) -> None:
    checker = _load_checker_module()
    backend_root = tmp_path / "backend"
    app_services_dir = backend_root / "app" / "services"
    app_services_dir.mkdir(parents=True)
    (app_services_dir / "master_bot_service.py").write_text(
        "class MasterBotService:\n    pass\n",
        encoding="utf-8",
    )
    api_dir = backend_root / "app" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "legacy.py").write_text(
        "from app.services.master_bot_service import master_bot_service\n",
        encoding="utf-8",
    )

    violations = checker.find_master_bot_compat_violations(backend_root)
    assert violations == []


def test_current_repository_master_bot_compat_boundary_passes() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_master_bot_compat_violations(backend_root)
    assert violations == []


def test_current_repository_brain_core_passes() -> None:
    checker = _load_checker_module()
    backend_root = Path(__file__).resolve().parents[1]
    violations = checker.find_violations(backend_root)
    assert violations == []
