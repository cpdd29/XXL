from __future__ import annotations

from pathlib import Path

from scripts.check_security_entrypoints import run_security_entrypoint_check


def test_security_entrypoints_cover_all_external_ingress() -> None:
    payload = run_security_entrypoint_check(repo_root=Path("/Users/xiaoyuge/Documents/XXL"))

    assert payload["ok"] is True
    check_by_name = {item["function"]: item for item in payload["checks"]}
    assert "workflow_webhook_route" in check_by_name
    assert (
        "security_gateway_service.inspect_text_entrypoint"
        in check_by_name["workflow_webhook_route"]["observed_calls"]
    )
    assert check_by_name["workflow_webhook_route"]["missing_calls"] == []
