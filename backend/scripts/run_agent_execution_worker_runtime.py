from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from threading import Event
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_execution_worker_service import agent_execution_worker_service  # noqa: E402


def _configure_worker_runtime(
    *,
    worker_id: str,
    poll_interval_seconds: float | None,
    lease_seconds: float | None,
    scan_limit: int | None,
) -> dict[str, Any]:
    agent_execution_worker_service.worker_id = worker_id
    if poll_interval_seconds is not None:
        agent_execution_worker_service._poll_interval_seconds = max(float(poll_interval_seconds), 0.1)
    if lease_seconds is not None:
        agent_execution_worker_service._lease_seconds = max(float(lease_seconds), 1.0)
    if scan_limit is not None:
        agent_execution_worker_service._scan_limit = max(int(scan_limit), 1)
    return {
        "worker_id": agent_execution_worker_service.worker_id,
        "poll_interval_seconds": float(getattr(agent_execution_worker_service, "_poll_interval_seconds", 0.0)),
        "lease_seconds": float(getattr(agent_execution_worker_service, "_lease_seconds", 0.0)),
        "scan_limit": int(getattr(agent_execution_worker_service, "_scan_limit", 0)),
    }


def run_agent_execution_worker_runtime(
    *,
    worker_id: str,
    poll_interval_seconds: float | None = None,
    lease_seconds: float | None = None,
    scan_limit: int | None = None,
    run_once: bool = False,
    shutdown_after_seconds: float | None = None,
) -> dict[str, Any]:
    runtime = _configure_worker_runtime(
        worker_id=worker_id,
        poll_interval_seconds=poll_interval_seconds,
        lease_seconds=lease_seconds,
        scan_limit=scan_limit,
    )
    if run_once:
        runtime["mode"] = "run_once"
        runtime["summary"] = agent_execution_worker_service.poll_once()
        return runtime

    stop_event = Event()

    def _stop(_: int, __) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    event_bus_ready = agent_execution_worker_service.start()
    started_at = time.time()
    runtime["mode"] = "daemon"
    runtime["event_bus_ready"] = bool(event_bus_ready)
    runtime["started_at_epoch"] = started_at
    try:
        while not stop_event.wait(timeout=0.5):
            if shutdown_after_seconds is not None and time.time() - started_at >= shutdown_after_seconds:
                break
    finally:
        agent_execution_worker_service.stop()
    runtime["stopped"] = True
    runtime["ran_for_seconds"] = round(time.time() - started_at, 3)
    return runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a standalone agent execution worker runtime.")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--poll-interval-seconds", type=float, default=None)
    parser.add_argument("--lease-seconds", type=float, default=None)
    parser.add_argument("--scan-limit", type=int, default=None)
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--shutdown-after-seconds", type=float, default=None)
    args = parser.parse_args()

    payload = run_agent_execution_worker_runtime(
        worker_id=str(args.worker_id).strip(),
        poll_interval_seconds=args.poll_interval_seconds,
        lease_seconds=args.lease_seconds,
        scan_limit=args.scan_limit,
        run_once=bool(args.run_once),
        shutdown_after_seconds=args.shutdown_after_seconds,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
