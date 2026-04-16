from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    backend_root = Path(__file__).resolve().parents[1]
    script_path = backend_root / "scripts" / "check_memory_governance.py"
    spec = importlib.util.spec_from_file_location("check_memory_governance", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_governance_script_reports_repo_local_policy_snapshot() -> None:
    module = _load_script_module()

    payload = module.run_check()

    assert payload["ok"] is True
    assert payload["summary"]["failed_checks"] == 0
    whitelist = payload["governance"]["long_term_whitelist"]
    assert {item["memory_type"] for item in whitelist} >= {
        "session_summary",
        "user_preference",
        "agent_decision",
        "task_result",
        "event_digest",
    }
    assert payload["checks"]["external_long_term_write_blocked"]["ok"] is True
    assert payload["checks"]["local_only_filtering_active"]["ok"] is True
    assert payload["checks"]["tenant_scope_isolation"]["ok"] is True
    assert payload["checks"]["global_scope_fallback"]["ok"] is True
    assert payload["checks"]["lifecycle_archive_active"]["ok"] is True


def test_memory_governance_script_strict_mode_returns_zero_when_checks_pass() -> None:
    module = _load_script_module()
    assert module.main(["--strict"]) == 0
