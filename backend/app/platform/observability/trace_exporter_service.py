from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.config import get_settings


logger = logging.getLogger(__name__)


class TraceExporterService:
    def __init__(self) -> None:
        self._warned_endpoint_failure = False
        self._warned_file_failure = False

    def _settings(self):
        return get_settings()

    def is_enabled(self) -> bool:
        settings = self._settings()
        return bool(
            settings.trace_export_enabled
            and (settings.trace_export_endpoint or settings.trace_export_file_path)
        )

    def export_audit_event(self, log_payload: dict[str, Any]) -> bool:
        if not self.is_enabled():
            return False

        metadata = log_payload.get("metadata")
        if not isinstance(metadata, dict):
            return False

        trace = metadata.get("trace")
        if not isinstance(trace, dict) or not trace.get("trace_id"):
            return False

        export_payload = {
            "schemaVersion": "workbot.trace.v1",
            "exportedAt": datetime.now(UTC).isoformat(),
            "source": "security_gateway",
            "audit": {
                "id": str(log_payload.get("id") or ""),
                "timestamp": str(log_payload.get("timestamp") or ""),
                "action": str(log_payload.get("action") or ""),
                "user": str(log_payload.get("user") or ""),
                "resource": str(log_payload.get("resource") or ""),
                "status": str(log_payload.get("status") or ""),
                "ip": str(log_payload.get("ip") or "-"),
                "details": str(log_payload.get("details") or ""),
            },
            "trace": trace,
        }
        for key in (
            "prompt_injection_assessment",
            "rewrite_diffs",
            "rewrite_notes",
            "penalty",
        ):
            value = metadata.get(key)
            if value is not None:
                export_payload[key] = value

        settings = self._settings()
        exported = False

        if settings.trace_export_endpoint:
            exported = self._export_to_endpoint(
                endpoint=settings.trace_export_endpoint,
                payload=export_payload,
                timeout_seconds=float(settings.trace_export_timeout_seconds),
            ) or exported

        if settings.trace_export_file_path:
            exported = self._export_to_file(
                file_path=settings.trace_export_file_path,
                payload=export_payload,
            ) or exported

        return exported

    def _export_to_endpoint(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> bool:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib_request.Request(
            endpoint,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout_seconds):
                self._warned_endpoint_failure = False
                return True
        except (urllib_error.URLError, ValueError, OSError) as exc:
            if not self._warned_endpoint_failure:
                logger.warning("Trace exporter endpoint unavailable, skipping export: %s", exc)
                self._warned_endpoint_failure = True
            return False

    def _export_to_file(self, *, file_path: str, payload: dict[str, Any]) -> bool:
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False))
                handle.write("\n")
            self._warned_file_failure = False
            return True
        except OSError as exc:
            if not self._warned_file_failure:
                logger.warning("Trace exporter file sink unavailable, skipping export: %s", exc)
                self._warned_file_failure = True
            return False


trace_exporter_service = TraceExporterService()
