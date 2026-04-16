from __future__ import annotations

from pathlib import Path

from scripts.check_scheduler_runtime_pg_acceptance import run_check


def test_scheduler_runtime_pg_acceptance_passes_on_sqlite(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'scheduler-acceptance.db'}"

    payload = run_check(database_url=database_url, probe_prefix="scheduler_probe_test")

    assert payload["ok"] is True
    assert payload["checks"]["service_a_initialized"]["ok"] is True
    assert payload["checks"]["service_b_initialized"]["ok"] is True
    assert payload["checks"]["runtime_methods"]["ok"] is True
    assert payload["checks"]["dispatch_job_claim_cycle"]["ok"] is True
    assert payload["checks"]["workflow_execution_job_claim_cycle"]["ok"] is True
    assert payload["checks"]["agent_execution_job_claim_cycle"]["ok"] is True
    assert payload["checks"]["workflow_run_claim_cycle"]["ok"] is True
    assert payload["checks"]["dispatch_guard_runtime"]["ok"] is True
    assert payload["checks"]["workflow_guard_runtime"]["ok"] is True
    assert payload["checks"]["agent_guard_runtime"]["ok"] is True
    assert payload["checks"]["reopen_visibility"]["ok"] is True
