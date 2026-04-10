from __future__ import annotations

import asyncio
from collections import defaultdict
from queue import Empty, Queue
from threading import Lock
from uuid import uuid4

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.nats_event_bus import nats_event_bus
from app.schemas.base import to_camel
from app.services.persistence_service import persistence_service
from app.services.store import store


WORKFLOW_RUNS_SUBJECT_PREFIX = "workflow.runs"
WORKFLOW_RUNS_SUBJECT_PATTERN = f"{WORKFLOW_RUNS_SUBJECT_PREFIX}.*"


class WorkflowRealtimeService:
    def __init__(self, *, event_bus=None) -> None:
        self._subscribers: dict[str, list[Queue]] = defaultdict(list)
        self._lock = Lock()
        self._instance_id = uuid4().hex
        self._event_bus = event_bus or nats_event_bus
        self._event_bus.subscribe(WORKFLOW_RUNS_SUBJECT_PATTERN, self._handle_event_bus_message)

    def _workflow_runs_snapshot(self, workflow_id: str) -> list[dict]:
        database_runs = persistence_service.list_workflow_runs(workflow_id=workflow_id)
        if database_runs is not None:
            return database_runs[:10]
        if getattr(persistence_service, "enabled", False):
            return []

        return store.clone(
            [run for run in store.workflow_runs if run["workflow_id"] == workflow_id][:10]
        )

    def _camelize(self, value: object) -> object:
        if isinstance(value, list):
            return [self._camelize(item) for item in value]
        if isinstance(value, dict):
            return {to_camel(str(key)): self._camelize(item) for key, item in value.items()}
        return value

    def build_snapshot(self, workflow_id: str) -> dict:
        payload = {
            "type": "workflow.runs.snapshot",
            "workflow_id": workflow_id,
            "timestamp": store.now_string(),
            "items": self._workflow_runs_snapshot(workflow_id),
            "run": None,
        }
        return self._camelize(payload)

    @staticmethod
    def _subject_for_workflow(workflow_id: str) -> str:
        return f"{WORKFLOW_RUNS_SUBJECT_PREFIX}.{workflow_id}"

    def _broadcast(self, workflow_id: str, payload: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(workflow_id, []))

        for subscriber in subscribers:
            subscriber.put(payload)

    def _handle_event_bus_message(self, subject: str, payload: dict) -> None:
        source_instance_id = payload.get("sourceInstanceId") or payload.get("source_instance_id")
        if source_instance_id == self._instance_id:
            return
        workflow_id = str(payload.get("workflowId") or subject.rsplit(".", maxsplit=1)[-1])
        self._broadcast(workflow_id, payload)

    def publish_run_event(self, run: dict, event_type: str) -> None:
        workflow_id = str(run["workflow_id"])
        payload = {
            "type": event_type,
            "workflow_id": workflow_id,
            "timestamp": store.now_string(),
            "items": self._workflow_runs_snapshot(workflow_id),
            "run": store.clone(run),
            "source_instance_id": self._instance_id,
        }
        serialized_payload = self._camelize(payload)
        self._broadcast(workflow_id, serialized_payload)
        self._event_bus.publish_json(self._subject_for_workflow(workflow_id), serialized_payload)

    def _subscribe(self, workflow_id: str) -> Queue:
        queue: Queue = Queue()
        with self._lock:
            self._subscribers[workflow_id].append(queue)
        return queue

    def _unsubscribe(self, workflow_id: str, queue: Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(workflow_id, [])
            self._subscribers[workflow_id] = [
                subscriber for subscriber in subscribers if subscriber is not queue
            ]
            if not self._subscribers[workflow_id]:
                self._subscribers.pop(workflow_id, None)

    async def stream(self, websocket: WebSocket, workflow_id: str) -> None:
        await websocket.accept()
        subscriber = self._subscribe(workflow_id)
        await websocket.send_json(self.build_snapshot(workflow_id))

        try:
            while True:
                try:
                    payload = await asyncio.to_thread(subscriber.get, True, 1.0)
                except Empty:
                    if websocket.client_state is WebSocketState.DISCONNECTED:
                        break

                    await websocket.send_json(
                        {
                            "type": "workflow.runs.keepalive",
                            "workflowId": workflow_id,
                            "timestamp": store.now_string(),
                            "items": [],
                            "run": None,
                        }
                    )
                    continue
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            return
        finally:
            self._unsubscribe(workflow_id, subscriber)


workflow_realtime_service = WorkflowRealtimeService()


def reset_workflow_realtime_state() -> None:
    with workflow_realtime_service._lock:
        workflow_realtime_service._subscribers.clear()
