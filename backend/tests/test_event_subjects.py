from __future__ import annotations

from app.core import event_subjects


def test_event_subject_constants_cover_brain_domains() -> None:
    values = {
        event_subjects.WORKFLOW_RUN_CREATED_SUBJECT,
        event_subjects.WORKFLOW_RUN_UPDATED_SUBJECT,
        event_subjects.WORKFLOW_RUN_COMPLETED_SUBJECT,
        event_subjects.WORKFLOW_RUN_FAILED_SUBJECT,
        event_subjects.WORKFLOW_RUN_SNAPSHOT_SUBJECT,
        event_subjects.WORKFLOW_RUN_KEEPALIVE_SUBJECT,
        event_subjects.WORKFLOW_EXECUTION_CLAIMED_SUBJECT,
        event_subjects.WORKFLOW_EXECUTION_STARTED_SUBJECT,
        event_subjects.WORKFLOW_EXECUTION_COMPLETED_SUBJECT,
        event_subjects.WORKFLOW_EXECUTION_FAILED_SUBJECT,
        event_subjects.AGENT_EXECUTION_REQUEST_SUBJECT,
        event_subjects.AGENT_EXECUTION_CLAIMED_SUBJECT,
        event_subjects.AGENT_EXECUTION_STARTED_SUBJECT,
        event_subjects.AGENT_EXECUTION_COMPLETED_SUBJECT,
        event_subjects.AGENT_EXECUTION_FAILED_SUBJECT,
        event_subjects.INTERNAL_EVENT_DELIVERY_REQUESTED_SUBJECT,
        event_subjects.INTERNAL_EVENT_DELIVERY_CLAIMED_SUBJECT,
        event_subjects.INTERNAL_EVENT_DELIVERY_COMPLETED_SUBJECT,
        event_subjects.INTERNAL_EVENT_DELIVERY_FAILED_SUBJECT,
        event_subjects.INTERNAL_EVENT_DELIVERY_RETRIED_SUBJECT,
    }

    assert len(values) == 20
    assert all(value.startswith("brain.") for value in values)
    assert event_subjects.WORKFLOW_RUN_SNAPSHOT_SUBJECT.endswith(".snapshot")
    assert event_subjects.WORKFLOW_RUN_KEEPALIVE_SUBJECT.endswith(".keepalive")
    assert event_subjects.WORKFLOW_EXECUTION_CLAIMED_SUBJECT == "brain.workflow.execution.claimed"
    assert event_subjects.AGENT_EXECUTION_REQUEST_SUBJECT == "brain.agent.execution.request"
    assert event_subjects.INTERNAL_EVENT_DELIVERY_RETRIED_SUBJECT == (
        "brain.internal_event.delivery.retried"
    )
