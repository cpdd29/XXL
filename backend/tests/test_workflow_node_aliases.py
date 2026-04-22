from app.brain_core.routing.service import _workflow_has_deferred_execution_target
from app.services.workflow_execution_service import (
    _derive_workflow_binding,
    _normalize_workflow_node_type,
    _selected_branch_node,
)


def test_workflow_node_aliases_normalize_to_workflow() -> None:
    assert _normalize_workflow_node_type("workflow") == "workflow"
    assert _normalize_workflow_node_type("sub_workflow") == "workflow"
    assert _normalize_workflow_node_type("trigger_workflow") == "workflow"


def test_derive_workflow_binding_supports_alias_fields_and_config() -> None:
    assert _derive_workflow_binding({"workflowId": "workflow-a"}) == "workflow-a"
    assert _derive_workflow_binding({"subWorkflowId": "workflow-b"}) == "workflow-b"
    assert _derive_workflow_binding({"targetWorkflowId": "workflow-c"}) == "workflow-c"
    assert _derive_workflow_binding({"config": {"sub_workflow_id": "workflow-d"}}) == "workflow-d"
    assert _derive_workflow_binding({"config": {"targetWorkflowId": "workflow-e"}}) == "workflow-e"


def test_selected_branch_node_accepts_sub_workflow_alias_node() -> None:
    workflow = {
        "nodes": [
            {"id": "trigger", "type": "trigger", "label": "触发"},
            {"id": "sub", "type": "sub_workflow", "label": "子流程", "sub_workflow_id": "workflow-child"},
        ]
    }
    selected = _selected_branch_node(workflow, intent=None)
    assert selected is not None
    assert selected["id"] == "sub"


def test_routing_detects_deferred_target_for_alias_workflow_nodes() -> None:
    workflow = {
        "nodes": [
            {"id": "sub", "type": "sub_workflow", "sub_workflow_id": "workflow-child"},
            {"id": "trigger-child", "type": "trigger_workflow", "target_workflow_id": "workflow-target"},
        ]
    }
    assert _workflow_has_deferred_execution_target(workflow) is True
