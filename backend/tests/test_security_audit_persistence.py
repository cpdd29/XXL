from __future__ import annotations

from scripts.check_security_audit_persistence import run_security_audit_persistence_check


def test_security_audit_persistence_check_passes_and_keeps_metadata(tmp_path) -> None:
    payload = run_security_audit_persistence_check(
        database_path=tmp_path / "security-audit-persistence.db"
    )

    assert payload["ok"] is True
    check_by_key = {item["key"]: item for item in payload["checks"]}
    assert check_by_key["security_gateway_emit_all_audit_actions"]["ok"] is True
    assert check_by_key["runtime_store_has_audits"]["ok"] is True
    assert check_by_key["audit_logs_persisted_to_truth_source"]["ok"] is True
    assert check_by_key["truth_source_survives_runtime_reset"]["ok"] is True
    assert check_by_key["persisted_audit_metadata_integrity"]["ok"] is True

    metadata_actions = check_by_key["persisted_audit_metadata_integrity"]["summary"]["actions"]
    by_action = {item["action"]: item for item in metadata_actions}
    assert by_action["安全网关放行"]["summary"]["has_trace_id"] is True
    assert by_action["安全网关改写放行"]["summary"]["has_rewrite_diffs"] is True
    assert by_action["安全网关拦截:prompt_injection"]["summary"]["has_prompt_injection_assessment"] is True
