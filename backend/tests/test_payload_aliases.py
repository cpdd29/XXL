from __future__ import annotations

from app.platform.contracts.payload_aliases import (
    alias_bool,
    alias_dict,
    alias_text,
    dispatch_context_from_run,
    execution_plan_from_payload,
    execution_plan_from_route_decision,
    route_decision_from_run,
    route_decision_from_task,
)


def test_alias_helpers_support_snake_and_camel_case() -> None:
    payload = {
        "workflowMode": "chat",
        "approvalRequired": True,
        "executionPlan": {"steps": []},
    }

    assert alias_text(payload, "workflow_mode", "workflowMode") == "chat"
    assert alias_bool(payload, "approval_required", "approvalRequired") is True
    assert alias_dict(payload, "execution_plan", "executionPlan") == {"steps": []}


def test_route_decision_helpers_resolve_task_and_run_payloads() -> None:
    task = {"routeDecision": {"intent": "help", "workflowMode": "chat"}}
    run = {
        "dispatchContext": {
            "routeDecision": {
                "intent": "write",
                "executionPlan": {"steps": [{"id": "step-1"}]},
            }
        }
    }

    assert route_decision_from_task(task) == {"intent": "help", "workflowMode": "chat"}
    assert dispatch_context_from_run(run) == {
        "routeDecision": {
            "intent": "write",
            "executionPlan": {"steps": [{"id": "step-1"}]},
        }
    }
    assert route_decision_from_run(run) == {
        "intent": "write",
        "executionPlan": {"steps": [{"id": "step-1"}]},
    }
    assert execution_plan_from_payload(route_decision_from_run(run)) == {"steps": [{"id": "step-1"}]}
    assert execution_plan_from_route_decision(route_decision_from_run(run)) == {"steps": [{"id": "step-1"}]}
