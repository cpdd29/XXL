from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable
from uuid import uuid4


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.agent_protocol import build_protocol_envelope
from app.core.event_subjects import (
    AGENT_EXECUTION_CLAIMED_SUBJECT,
    WORKFLOW_EXECUTION_CLAIMED_SUBJECT,
)
from app.core.nats_event_bus import NatsEventBus
from app.core.agent_protocol import protocol_from_message
from app.services.agent_execution_worker_service import AGENT_EXECUTION_QUEUE, AGENT_EXECUTION_SUBJECT
from app.services.workflow_dispatcher_service import WORKFLOW_DISPATCH_QUEUE, WORKFLOW_DISPATCH_SUBJECT
from app.services.workflow_execution_worker_service import (
    WORKFLOW_EXECUTION_QUEUE,
    WORKFLOW_EXECUTION_SUBJECT,
)


BusFactory = Callable[[], NatsEventBus]


def _wait_until(predicate: Callable[[], bool], *, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _build_probe_envelope(
    *,
    message_name: str,
    message_type: str,
    payload: dict[str, Any],
    probe_id: str,
) -> dict[str, Any]:
    envelope, _ = build_protocol_envelope(
        message_name=message_name,
        message_type=message_type,
        payload=payload,
        run_id=str(payload.get("run_id") or payload.get("task_id") or probe_id),
        source={"kind": "nats_roundtrip_probe", "id": probe_id},
        target={"kind": "nats_roundtrip_probe", "id": probe_id},
    )
    return envelope


def _probe_subject(base_subject: str, probe_id: str) -> str:
    return f"{base_subject}.probe.{probe_id}"


def _default_bus_factory(*, nats_url: str, operation_timeout_seconds: float) -> BusFactory:
    return lambda: NatsEventBus(
        nats_url=nats_url,
        retry_interval_seconds=0.0,
        operation_timeout_seconds=operation_timeout_seconds,
    )


def run_check(
    *,
    nats_url: str,
    message_count: int = 3,
    operation_timeout_seconds: float = 0.5,
    bus_factory: BusFactory | None = None,
) -> dict[str, Any]:
    resolved_factory = bus_factory or _default_bus_factory(
        nats_url=nats_url,
        operation_timeout_seconds=operation_timeout_seconds,
    )
    probe_id = uuid4().hex[:12]
    buses: list[NatsEventBus] = []

    def create_bus() -> NatsEventBus:
        bus = resolved_factory()
        buses.append(bus)
        return bus

    try:
        connect_bus = create_bus()
        connected = connect_bus.initialize()
        connect_snapshot = connect_bus.connection_snapshot()
        connect_ok = bool(connected) and bool(connect_snapshot.get("connected")) and not bool(
            connect_snapshot.get("fallback_mode")
        )

        roundtrip_subject = f"brain.probe.roundtrip.{probe_id}"
        roundtrip_bus = create_bus()
        publisher_bus = create_bus()
        roundtrip_hits: list[dict[str, Any]] = []
        roundtrip_bus.subscribe(
            roundtrip_subject,
            lambda subject, payload: roundtrip_hits.append(
                {
                    "subject": subject,
                    "message_type": protocol_from_message(payload).get("message_type"),
                    "probe_id": str(payload.get("probe_id") or "").strip(),
                }
            ),
        )
        roundtrip_initialized = roundtrip_bus.initialize() and publisher_bus.initialize()
        publisher_bus.publish_json(
            roundtrip_subject,
            _build_probe_envelope(
                message_name="brain.probe.roundtrip",
                message_type="event",
                payload={"probe_id": probe_id},
                probe_id=probe_id,
            ),
        )
        roundtrip_received = _wait_until(lambda: len(roundtrip_hits) == 1)

        dispatch_subject = _probe_subject(WORKFLOW_DISPATCH_SUBJECT, probe_id)
        dispatch_a = create_bus()
        dispatch_b = create_bus()
        dispatch_pub = create_bus()
        dispatch_hits = {"a": 0, "b": 0}
        dispatch_a.subscribe(
            dispatch_subject,
            lambda _subject, _payload: dispatch_hits.__setitem__("a", dispatch_hits["a"] + 1),
            queue_group=WORKFLOW_DISPATCH_QUEUE,
        )
        dispatch_b.subscribe(
            dispatch_subject,
            lambda _subject, _payload: dispatch_hits.__setitem__("b", dispatch_hits["b"] + 1),
            queue_group=WORKFLOW_DISPATCH_QUEUE,
        )
        dispatch_initialized = dispatch_a.initialize() and dispatch_b.initialize() and dispatch_pub.initialize()
        for index in range(message_count):
            dispatch_pub.publish_json(
                dispatch_subject,
                {
                    "run_id": f"{probe_id}-dispatch-{index}",
                    "step_delay": 0.0,
                },
            )
        dispatch_received = _wait_until(lambda: dispatch_hits["a"] + dispatch_hits["b"] == message_count)

        workflow_subject = _probe_subject(WORKFLOW_EXECUTION_SUBJECT, probe_id)
        workflow_a = create_bus()
        workflow_b = create_bus()
        workflow_pub = create_bus()
        workflow_hits = {"command": 0, "ignored": 0, "a": 0, "b": 0}

        def _workflow_handler(slot: str):
            def _consume(_subject: str, payload: dict[str, Any]) -> None:
                message_type = protocol_from_message(payload).get("message_type")
                if message_type and message_type != "command":
                    workflow_hits["ignored"] += 1
                    return
                workflow_hits["command"] += 1
                workflow_hits[slot] += 1

            return _consume

        workflow_a.subscribe(
            workflow_subject,
            _workflow_handler("a"),
            queue_group=WORKFLOW_EXECUTION_QUEUE,
        )
        workflow_b.subscribe(
            workflow_subject,
            _workflow_handler("b"),
            queue_group=WORKFLOW_EXECUTION_QUEUE,
        )
        workflow_initialized = workflow_a.initialize() and workflow_b.initialize() and workflow_pub.initialize()
        workflow_pub.publish_json(
            workflow_subject,
            _build_probe_envelope(
                message_name="workflow.execution.request",
                message_type="command",
                payload={"run_id": f"{probe_id}-workflow-command", "step_delay": 0.0},
                probe_id=probe_id,
            ),
        )
        workflow_pub.publish_json(
            workflow_subject,
            _build_probe_envelope(
                message_name="workflow.execution.claimed",
                message_type="event",
                payload={"run_id": f"{probe_id}-workflow-event"},
                probe_id=probe_id,
            ),
        )
        workflow_received = _wait_until(
            lambda: workflow_hits["command"] == 1 and workflow_hits["ignored"] == 1
        )

        agent_subject = _probe_subject(AGENT_EXECUTION_SUBJECT, probe_id)
        agent_a = create_bus()
        agent_b = create_bus()
        agent_pub = create_bus()
        agent_hits = {"command": 0, "ignored": 0, "a": 0, "b": 0}

        def _agent_handler(slot: str):
            def _consume(_subject: str, payload: dict[str, Any]) -> None:
                message_type = protocol_from_message(payload).get("message_type")
                if message_type and message_type != "command":
                    agent_hits["ignored"] += 1
                    return
                agent_hits["command"] += 1
                agent_hits[slot] += 1

            return _consume

        agent_a.subscribe(
            agent_subject,
            _agent_handler("a"),
            queue_group=AGENT_EXECUTION_QUEUE,
        )
        agent_b.subscribe(
            agent_subject,
            _agent_handler("b"),
            queue_group=AGENT_EXECUTION_QUEUE,
        )
        agent_initialized = agent_a.initialize() and agent_b.initialize() and agent_pub.initialize()
        agent_pub.publish_json(
            agent_subject,
            _build_probe_envelope(
                message_name="agent.execution.request",
                message_type="command",
                payload={
                    "run_id": f"{probe_id}-agent-command",
                    "task_id": f"{probe_id}-agent-task",
                    "workflow_id": "__agent_dispatch__",
                    "execution_agent_id": "probe-agent",
                    "step_delay": 0.0,
                },
                probe_id=probe_id,
            ),
        )
        agent_pub.publish_json(
            agent_subject,
            _build_probe_envelope(
                message_name="agent.execution.claimed",
                message_type="event",
                payload={
                    "run_id": f"{probe_id}-agent-event",
                    "task_id": f"{probe_id}-agent-task",
                    "workflow_id": "__agent_dispatch__",
                },
                probe_id=probe_id,
            ),
        )
        agent_received = _wait_until(lambda: agent_hits["command"] == 1 and agent_hits["ignored"] == 1)

        phases = {
            "connect": {
                "ok": connect_ok,
                "summary": connect_snapshot,
            },
            "roundtrip": {
                "ok": roundtrip_initialized and roundtrip_received,
                "summary": {
                    "subject": roundtrip_subject,
                    "received": len(roundtrip_hits),
                    "hits": roundtrip_hits,
                },
            },
            "dispatch_queue": {
                "ok": dispatch_initialized
                and dispatch_received
                and dispatch_hits["a"] + dispatch_hits["b"] == message_count
                and max(dispatch_hits.values()) <= message_count,
                "summary": {
                    "subject": dispatch_subject,
                    "base_subject": WORKFLOW_DISPATCH_SUBJECT,
                    "queue_group": WORKFLOW_DISPATCH_QUEUE,
                    "message_count": message_count,
                    "hits": dispatch_hits,
                },
            },
            "workflow_queue_and_filter": {
                "ok": workflow_initialized
                and workflow_received
                and workflow_hits["command"] == 1
                and workflow_hits["ignored"] == 1
                and workflow_hits["a"] + workflow_hits["b"] == 1,
                "summary": {
                    "subject": workflow_subject,
                    "base_subject": WORKFLOW_EXECUTION_SUBJECT,
                    "command_subject": workflow_subject,
                    "event_subject": WORKFLOW_EXECUTION_CLAIMED_SUBJECT,
                    "queue_group": WORKFLOW_EXECUTION_QUEUE,
                    "hits": workflow_hits,
                },
            },
            "agent_queue_and_filter": {
                "ok": agent_initialized
                and agent_received
                and agent_hits["command"] == 1
                and agent_hits["ignored"] == 1
                and agent_hits["a"] + agent_hits["b"] == 1,
                "summary": {
                    "subject": agent_subject,
                    "base_subject": AGENT_EXECUTION_SUBJECT,
                    "command_subject": agent_subject,
                    "event_subject": AGENT_EXECUTION_CLAIMED_SUBJECT,
                    "queue_group": AGENT_EXECUTION_QUEUE,
                    "hits": agent_hits,
                },
            },
        }
        return {
            "ok": all(bool(item["ok"]) for item in phases.values()),
            "nats_url": nats_url,
            "probe_id": probe_id,
            "phases": phases,
        }
    finally:
        for bus in reversed(buses):
            try:
                bus.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real NATS roundtrip, queue-group and handler-filter acceptance checks.")
    parser.add_argument("--nats-url", required=True)
    parser.add_argument("--message-count", type=int, default=3)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = run_check(
        nats_url=args.nats_url,
        message_count=max(int(args.message_count), 1),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
