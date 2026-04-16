from __future__ import annotations

from scripts.check_security_controls import run_security_control_check


def test_security_control_check_passes_smoke_suite() -> None:
    payload = run_security_control_check()

    assert payload["ok"] is True
    check_by_key = {item["key"]: item for item in payload["checks"]}
    assert check_by_key["allow_and_audit"]["ok"] is True
    assert check_by_key["redaction_and_audit"]["ok"] is True
    assert check_by_key["prompt_injection_block"]["ok"] is True
    assert check_by_key["auth_scope_block"]["ok"] is True
    assert check_by_key["rate_limit_block"]["ok"] is True
    assert check_by_key["message_ingest_redaction_side_effects"]["ok"] is True
    assert check_by_key["blocked_message_no_orchestration_side_effects"]["ok"] is True
    assert check_by_key["message_ingest_auth_scope_route_block"]["ok"] is True
    assert check_by_key["message_ingest_rate_limit_route_block"]["ok"] is True
    assert check_by_key["workflow_webhook_block_no_orchestration_side_effects"]["ok"] is True
