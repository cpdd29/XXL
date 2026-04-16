from __future__ import annotations

from pathlib import Path

from scripts.check_external_ingress_bypass import run_external_ingress_bypass_check


REPO_ROOT = Path("/Users/xiaoyuge/Documents/XXL")


def _route_index(payload: dict) -> dict[str, dict]:
    return {item["function"]: item for item in payload["routes"]}


def test_external_ingress_bypass_scan_covers_required_entrypoints() -> None:
    payload = run_external_ingress_bypass_check(repo_root=REPO_ROOT)
    route_map = _route_index(payload)

    required_functions = {
        "ingest_message_route",
        "telegram_webhook_route",
        "wecom_webhook_route",
        "workflow_webhook_route",
        "register_external_agent_route",
        "external_agent_heartbeat_route",
        "report_external_agent_failure_route",
    }
    assert required_functions.issubset(route_map)


def test_external_ingress_bypass_scan_classifies_public_vs_control_plane() -> None:
    payload = run_external_ingress_bypass_check(repo_root=REPO_ROOT)
    route_map = _route_index(payload)

    assert route_map["register_external_agent_route"]["route_type"] == "public_external_ingress"
    assert route_map["external_skill_heartbeat_route"]["route_type"] == "public_external_ingress"
    assert route_map["report_external_agent_failure_route"]["route_type"] == "authenticated_control_plane"
    assert route_map["set_external_skill_rollout_policy_route"]["route_type"] == "authenticated_control_plane"


def test_external_ingress_bypass_scan_public_routes_have_baseline_protection() -> None:
    payload = run_external_ingress_bypass_check(repo_root=REPO_ROOT)
    route_map = _route_index(payload)

    assert payload["ok"] is True
    assert payload["summary"]["failed_public_routes"] == 0
    assert route_map["workflow_webhook_route"]["protection_summary"]["is_protected"] is True
    assert route_map["register_external_agent_route"]["protection_summary"]["is_protected"] is True
    assert route_map["ingest_message_route"]["protection_summary"]["is_protected"] is True
