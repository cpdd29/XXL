from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4
import json
import time
from urllib.parse import urljoin

import httpx

from app.services.store import store
from app.services.tool_source_service import (
    ToolSourceService,
    tool_source_service,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalized_provider(tool: dict[str, Any]) -> str:
    provider = str(tool.get("provider") or "").strip().lower()
    if provider:
        return provider
    if str(tool.get("type") or "").strip().lower() == "mcp":
        return "mcporter"
    return "unknown"


class MCPRuntimeClient(Protocol):
    def health(self, *, tool: dict[str, Any], runtime_config: dict[str, Any]) -> dict[str, Any]:
        ...

    def invoke(
        self,
        *,
        tool: dict[str, Any],
        payload: dict[str, Any],
        runtime_config: dict[str, Any],
        trace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class DefaultMCPRuntimeClient:
    def __init__(self) -> None:
        self._failure_counts: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}

    def _resolve_health_url(self, runtime_config: dict[str, Any]) -> str | None:
        base_url = str(runtime_config.get("base_url") or "").strip()
        if not base_url:
            return None
        health_path = str(runtime_config.get("health_path") or "/health").strip() or "/health"
        return urljoin(f"{base_url.rstrip('/')}/", health_path.lstrip("/"))

    def _resolve_invoke_url(self, *, tool: dict[str, Any], runtime_config: dict[str, Any]) -> str:
        base_url = str(runtime_config.get("base_url") or "").strip()
        if not base_url:
            raise RuntimeError(f"Tool '{tool.get('id')}' runtime is not configured")
        configured_path = str(runtime_config.get("invoke_path") or "").strip()
        if configured_path:
            return urljoin(f"{base_url.rstrip('/')}/", configured_path.lstrip("/"))

        tool_name = str(tool.get("name") or "").strip().lower()
        if "search" in tool_name:
            default_path = "/search"
        elif "pdf_read" in tool_name or tool_name.endswith("read"):
            default_path = "/tools/read"
        elif "pdf_summary" in tool_name or "summary" in tool_name:
            default_path = "/tools/summary"
        elif "to_docx" in tool_name or "docx" in tool_name:
            default_path = "/tools/to_docx"
        elif "writer" in tool_name or "speech" in tool_name:
            default_path = "/generate"
        elif "weather" in tool_name:
            default_path = "/weather"
        elif "order" in tool_name or "crm" in tool_name:
            default_path = "/query"
        else:
            default_path = "/invoke"
        return urljoin(f"{base_url.rstrip('/')}/", default_path.lstrip("/"))

    def _resolve_request_mode(self, *, tool: dict[str, Any], runtime_config: dict[str, Any]) -> str:
        configured = str(runtime_config.get("request_mode") or "").strip().lower()
        if configured in {
            "wrapped_payload",
            "raw_payload",
            "raw_payload_with_trace",
            "execute_tool_payload",
        }:
            return configured
        return "wrapped_payload"

    def _build_request_payload(
        self,
        *,
        tool: dict[str, Any],
        payload: dict[str, Any],
        runtime_config: dict[str, Any],
        trace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_mode = self._resolve_request_mode(tool=tool, runtime_config=runtime_config)
        normalized_payload = deepcopy(payload or {})
        normalized_trace = deepcopy(trace_context or {})

        if request_mode == "raw_payload":
            return normalized_payload
        if request_mode == "raw_payload_with_trace":
            if normalized_trace:
                normalized_payload["trace_context"] = normalized_trace
            return normalized_payload
        if request_mode == "execute_tool_payload":
            tool_alias = str(runtime_config.get("tool_alias") or tool.get("name") or "").strip()
            return {
                "tool": tool_alias,
                "payload": normalized_payload,
            }
        return {
            "tool_id": str(tool.get("id") or ""),
            "tool_name": str(tool.get("name") or ""),
            "payload": normalized_payload,
            "trace_context": normalized_trace,
        }

    def health(self, *, tool: dict[str, Any], runtime_config: dict[str, Any]) -> dict[str, Any]:
        if not bool(tool.get("enabled", True)):
            status = "disabled"
            reason = "tool_disabled"
        elif runtime_config.get("base_url"):
            status = "healthy"
            reason = "base_url_configured"
        elif runtime_config.get("command"):
            status = "degraded"
            reason = "command_bridge_configured"
        else:
            status = "unknown"
            reason = "runtime_config_missing"

        health_url = self._resolve_health_url(runtime_config)
        probe_health = bool(runtime_config.get("probe_health", False))
        timeout_seconds = float(runtime_config.get("timeout_seconds") or 3.0)
        if probe_health and health_url and status in {"healthy", "degraded"}:
            try:
                with httpx.Client(timeout=timeout_seconds) as client:
                    response = client.get(health_url)
                if response.status_code >= 500:
                    status = "degraded"
                    reason = f"health_http_{response.status_code}"
                elif response.status_code >= 400:
                    status = "degraded"
                    reason = f"health_client_error_{response.status_code}"
                else:
                    reason = "health_probe_ok"
            except Exception as exc:  # pragma: no cover - network dependent
                status = "degraded"
                reason = f"health_probe_failed:{exc.__class__.__name__}"

        return {
            "status": status,
            "reason": reason,
            "checked_at": _utc_now_iso(),
            "runtime": {
                "base_url": runtime_config.get("base_url"),
                "command": runtime_config.get("command"),
                "provider": runtime_config.get("provider"),
                "health_url": health_url,
            },
        }

    def invoke(
        self,
        *,
        tool: dict[str, Any],
        payload: dict[str, Any],
        runtime_config: dict[str, Any],
        trace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not bool(tool.get("enabled", True)):
            raise PermissionError(f"Tool '{tool.get('id')}' is disabled")
        invoke_url = self._resolve_invoke_url(tool=tool, runtime_config=runtime_config)
        tool_id = str(tool.get("id") or "")
        timeout_seconds = float(runtime_config.get("timeout_seconds") or 10.0)
        retry_attempts = max(1, int(runtime_config.get("retry_attempts") or 2))
        method = str(runtime_config.get("http_method") or "POST").strip().upper()
        breaker_threshold = max(1, int(runtime_config.get("circuit_breaker_threshold") or 3))
        breaker_ttl_seconds = float(runtime_config.get("circuit_breaker_ttl_seconds") or 30.0)

        now = time.monotonic()
        circuit_until = self._circuit_open_until.get(tool_id, 0.0)
        if circuit_until > now:
            remaining = round(circuit_until - now, 3)
            raise RuntimeError(f"Tool '{tool_id}' circuit_open for {remaining}s")

        last_error: Exception | None = None
        for attempt in range(1, retry_attempts + 1):
            try:
                with httpx.Client(timeout=timeout_seconds) as client:
                    if method == "GET":
                        response = client.get(invoke_url, params=payload or {})
                    else:
                        response = client.request(
                            method,
                            invoke_url,
                            json=self._build_request_payload(
                                tool=tool,
                                payload=payload,
                                runtime_config=runtime_config,
                                trace_context=trace_context,
                            ),
                        )
                if response.status_code >= 500:
                    raise RuntimeError(f"http_server_error:{response.status_code}")
                if response.status_code >= 400:
                    message = response.text[:240].strip() or f"http_client_error:{response.status_code}"
                    raise ValueError(message)
                try:
                    output = response.json()
                except Exception:
                    output = {"raw": response.text}

                self._failure_counts[tool_id] = 0
                self._circuit_open_until.pop(tool_id, None)
                return {
                    "ok": True,
                    "bridge_mode": "http",
                    "output": output if isinstance(output, dict) else {"result": output},
                    "meta": {
                        "provider": runtime_config.get("provider"),
                        "trace_context": deepcopy(trace_context or {}),
                        "endpoint": invoke_url,
                        "method": method,
                        "attempt": attempt,
                        "status_code": response.status_code,
                    },
                }
            except Exception as exc:  # pragma: no cover - covered via tests with mock server/patch
                last_error = exc
                if attempt >= retry_attempts:
                    break

        failures = self._failure_counts.get(tool_id, 0) + 1
        self._failure_counts[tool_id] = failures
        if failures >= breaker_threshold:
            self._circuit_open_until[tool_id] = now + breaker_ttl_seconds
        suffix = f"{last_error.__class__.__name__}: {last_error}" if last_error else "unknown"
        raise RuntimeError(
            f"MCP invoke failed for '{tool_id}' after {retry_attempts} attempts ({suffix})"
        )


class MCPRuntimeService:
    TRACE_BUFFER_LIMIT = 200

    def __init__(
        self,
        *,
        source_service: ToolSourceService | None = None,
        config_root: str | Path | None = None,
    ) -> None:
        self._source_service = source_service or tool_source_service
        self._config_root = Path(config_root) if config_root is not None else None
        self._clients: dict[str, MCPRuntimeClient] = {}
        self._tool_mapping: dict[str, dict[str, Any]] = {}
        self._traces: list[dict[str, Any]] = []
        self.register_client("mcporter", DefaultMCPRuntimeClient())
        self.register_client("agent-reach-cli", DefaultMCPRuntimeClient())
        self.register_client("unknown", DefaultMCPRuntimeClient())
        if not hasattr(store, "mcp_runtime_calls"):
            store.mcp_runtime_calls = []
        if not hasattr(store, "mcp_runtime_shadow_calls"):
            store.mcp_runtime_shadow_calls = []

    def register_client(self, provider: str, client: MCPRuntimeClient) -> None:
        normalized = str(provider or "").strip().lower() or "unknown"
        self._clients[normalized] = client

    def reset_traces(self) -> None:
        self._traces = []
        store.mcp_runtime_calls = []
        store.mcp_runtime_shadow_calls = []

    def _resolve_config_path(self) -> Path | None:
        if self._config_root is not None:
            return self._config_root / "config" / "mcporter.json"
        external_root = getattr(self._source_service, "_external_source_path", None)
        if external_root is None:
            return None
        try:
            return Path(external_root) / "config" / "mcporter.json"
        except TypeError:
            return None

    def load_config(self) -> dict[str, Any]:
        config_path = self._resolve_config_path()
        if config_path is None or not config_path.exists():
            return {}
        return _safe_read_json(config_path)

    def list_servers(self) -> list[dict[str, Any]]:
        config = self.load_config()
        payload = config.get("mcpServers")
        checked_at = _utc_now_iso()
        items: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            for name, entry in sorted(payload.items()):
                server = entry if isinstance(entry, dict) else {}
                base_url = str(server.get("baseUrl") or "").strip()
                status = "healthy" if base_url else "unknown"
                if base_url.startswith("http://localhost") or base_url.startswith("http://127.0.0.1"):
                    status = "degraded"
                reason = (
                    "base_url_configured"
                    if status == "healthy"
                    else "local_runtime_requires_process" if status == "degraded" else "missing_base_url"
                )
                items.append(
                    {
                        "id": f"mcp:{name}",
                        "name": str(name),
                        "provider": "mcporter",
                        "base_url": base_url or None,
                        "health_status": status,
                        "health_message": reason,
                        "config_summary": {
                            "baseUrl": base_url or None,
                            "importsCount": len(config.get("imports") or []),
                            "checkedAt": checked_at,
                        },
                    }
                )
            if items:
                return items

        # Fallback for environments without local mcporter.json:
        # infer runtime state from known tool mapping (local MCP + external adapters).
        servers_by_id: dict[str, dict[str, Any]] = {}
        for tool in self.build_tool_mapping(refresh=False).values():
            if not isinstance(tool, dict):
                continue
            tool_id = str(tool.get("id") or "").strip()
            if not tool_id or tool_id in servers_by_id:
                continue
            source_kind = str(tool.get("source_kind") or "").strip().lower()
            provider = _normalized_provider(tool)
            bridge_mode = str(tool.get("bridge_mode") or "").strip().lower()
            tool_type = str(tool.get("type") or "").strip().lower()
            if source_kind not in {"local_mcp", "external"} and provider not in {"mcporter", "agent-reach-cli"}:
                if "mcp" not in bridge_mode and tool_type != "mcp":
                    continue
            runtime_config = self.parse_runtime_config(tool)
            base_url = str(runtime_config.get("base_url") or "").strip()
            command = str(runtime_config.get("command") or "").strip()
            status = "healthy" if base_url else "degraded" if command else "unknown"
            if base_url.startswith("http://localhost") or base_url.startswith("http://127.0.0.1"):
                status = "degraded"
            reason = (
                "base_url_configured"
                if status == "healthy"
                else "command_bridge_configured" if command else "missing_runtime_endpoint"
            )
            servers_by_id[tool_id] = {
                "id": tool_id,
                "name": str(tool.get("name") or tool_id),
                "provider": str(runtime_config.get("provider") or provider),
                "base_url": base_url or None,
                "health_status": status,
                "health_message": reason,
                "config_summary": {
                    "baseUrl": base_url or None,
                    "command": command or None,
                    "source": str(tool.get("source") or ""),
                    "sourceKind": source_kind or None,
                    "checkedAt": checked_at,
                    "derivedFrom": "tool_mapping",
                },
            }
        return sorted(servers_by_id.values(), key=lambda item: str(item.get("name") or ""))

    def health_summary(self) -> dict[str, Any]:
        items = self.list_servers()
        return {
            "items": items,
            "counts": {
                "healthy": sum(1 for item in items if item["health_status"] == "healthy"),
                "degraded": sum(1 for item in items if item["health_status"] == "degraded"),
                "unknown": sum(1 for item in items if item["health_status"] == "unknown"),
            },
            "total": len(items),
        }

    def build_tool_mapping(self, *, refresh: bool = False) -> dict[str, dict[str, Any]]:
        if refresh or not self._tool_mapping:
            mapping: dict[str, dict[str, Any]] = {}
            for tool in self._source_service.list_tools(refresh=refresh):
                tool_id = str(tool.get("id") or "").strip()
                if not tool_id:
                    continue
                normalized = deepcopy(tool)
                mapping[tool_id] = normalized
                alias = f"{normalized.get('source', '')}:{normalized.get('name', '')}".strip(":")
                if alias and alias not in mapping:
                    mapping[alias] = normalized
            self._tool_mapping = mapping
        return deepcopy(self._tool_mapping)

    def get_tool(self, tool_id: str, *, refresh: bool = False) -> dict[str, Any]:
        normalized_tool_id = str(tool_id or "").strip()
        if not normalized_tool_id:
            raise LookupError("Tool id is required")
        mapping = self.build_tool_mapping(refresh=refresh)
        if normalized_tool_id not in mapping:
            raise LookupError(f"Tool '{normalized_tool_id}' not found")
        return deepcopy(mapping[normalized_tool_id])

    def parse_runtime_config(self, tool: dict[str, Any]) -> dict[str, Any]:
        config_summary = deepcopy(tool.get("config_summary") or {})
        base_url = config_summary.get("baseUrl") or config_summary.get("base_url")
        command = config_summary.get("command")
        timeout_seconds = config_summary.get("timeoutSeconds") or config_summary.get("timeout") or 30
        invoke_path = config_summary.get("invokePath") or config_summary.get("invoke_path")
        health_path = config_summary.get("healthPath") or config_summary.get("health_path") or "/health"
        http_method = config_summary.get("httpMethod") or config_summary.get("http_method") or "POST"
        retry_attempts = config_summary.get("retryAttempts") or config_summary.get("retry_attempts") or 2
        request_mode = config_summary.get("requestMode") or config_summary.get("request_mode")
        tool_alias = config_summary.get("toolAlias") or config_summary.get("tool_alias")
        probe_health = config_summary.get("probeHealth")
        if probe_health is None:
            probe_health = config_summary.get("probe_health", False)
        breaker_threshold = (
            config_summary.get("circuitBreakerThreshold")
            or config_summary.get("circuit_breaker_threshold")
            or 3
        )
        breaker_ttl_seconds = (
            config_summary.get("circuitBreakerTtlSeconds")
            or config_summary.get("circuit_breaker_ttl_seconds")
            or 30
        )
        migration_stage = deepcopy(tool.get("migration_stage") or {})
        rollback = deepcopy(tool.get("rollback") or {})
        traffic_policy = deepcopy(tool.get("traffic_policy") or {})
        return {
            "provider": _normalized_provider(tool),
            "base_url": str(base_url).strip() if base_url else None,
            "command": str(command).strip() if command else None,
            "timeout_seconds": float(timeout_seconds),
            "invoke_path": str(invoke_path).strip() if invoke_path else None,
            "health_path": str(health_path).strip() if health_path else "/health",
            "http_method": str(http_method).strip().upper() or "POST",
            "retry_attempts": max(1, int(retry_attempts)),
            "request_mode": str(request_mode).strip().lower() if request_mode else None,
            "tool_alias": str(tool_alias).strip() if tool_alias else None,
            "probe_health": bool(probe_health),
            "circuit_breaker_threshold": max(1, int(breaker_threshold)),
            "circuit_breaker_ttl_seconds": float(breaker_ttl_seconds),
            "source": str(tool.get("source") or "").strip() or None,
            "source_kind": str(tool.get("source_kind") or "").strip() or None,
            "bridge": str(tool.get("bridge_mode") or "").strip() or "catalog",
            "migration_stage": migration_stage,
            "rollback": rollback,
            "traffic_policy": traffic_policy,
            "raw": config_summary,
        }

    def _resolve_client(self, tool: dict[str, Any], runtime_config: dict[str, Any]) -> MCPRuntimeClient:
        provider = str(runtime_config.get("provider") or _normalized_provider(tool)).strip().lower() or "unknown"
        return self._clients.get(provider, self._clients["unknown"])

    def health_for_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        runtime_config = self.parse_runtime_config(tool)
        client = self._resolve_client(tool, runtime_config)
        check = client.health(tool=deepcopy(tool), runtime_config=runtime_config)
        return {
            "status": str(check.get("status") or "unknown"),
            "checked_at": str(check.get("checked_at") or _utc_now_iso()),
            "reason": str(check.get("reason") or ""),
            "runtime": deepcopy(check.get("runtime") or {}),
        }

    def record_call(self, tool_id: str, *, status: str, error: str | None = None) -> None:
        payload = {
            "tool_id": str(tool_id or "").strip(),
            "status": str(status or "").strip() or "unknown",
            "error": error,
            "at": _utc_now_iso(),
        }
        getattr(store, "mcp_runtime_calls").append(payload)

    def record_shadow_call(self, tool_id: str, *, status: str, error: str | None = None) -> None:
        payload = {
            "tool_id": str(tool_id or "").strip(),
            "status": str(status or "").strip() or "unknown",
            "error": error,
            "at": _utc_now_iso(),
        }
        getattr(store, "mcp_runtime_shadow_calls").append(payload)

    def recent_call_summary(self, tool_id: str) -> dict[str, Any]:
        normalized = str(tool_id or "").strip()
        entries = [
            item
            for item in getattr(store, "mcp_runtime_calls", [])
            if str(item.get("tool_id") or "").strip() == normalized
        ]
        if not entries and ":" in normalized:
            try:
                resolved = self.get_tool(normalized)
            except Exception:
                resolved = None
            if isinstance(resolved, dict):
                resolved_id = str(resolved.get("id") or "").strip()
                entries = [
                    item
                    for item in getattr(store, "mcp_runtime_calls", [])
                    if str(item.get("tool_id") or "").strip() == resolved_id
                ]
        if not entries:
            return {
                "total_calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "last_called_at": None,
                "last_status": "never_called",
                "last_error": None,
            }
        last = entries[-1]
        return {
            "total_calls": len(entries),
            "success_calls": sum(1 for item in entries if item.get("status") == "success"),
            "failed_calls": sum(1 for item in entries if item.get("status") == "failed"),
            "last_called_at": last.get("at"),
            "last_status": last.get("status"),
            "last_error": last.get("error"),
        }

    def recent_shadow_summary(self, tool_id: str) -> dict[str, Any]:
        normalized = str(tool_id or "").strip()
        entries = [
            item
            for item in getattr(store, "mcp_runtime_shadow_calls", [])
            if str(item.get("tool_id") or "").strip() == normalized
        ]
        if not entries:
            return {
                "shadow_total_calls": 0,
                "shadow_success_calls": 0,
                "shadow_failed_calls": 0,
                "shadow_last_called_at": None,
                "shadow_last_status": "never_called",
                "shadow_last_error": None,
            }
        last = entries[-1]
        return {
            "shadow_total_calls": len(entries),
            "shadow_success_calls": sum(1 for item in entries if item.get("status") == "success"),
            "shadow_failed_calls": sum(1 for item in entries if item.get("status") == "failed"),
            "shadow_last_called_at": last.get("at"),
            "shadow_last_status": last.get("status"),
            "shadow_last_error": last.get("error"),
        }

    def _append_trace(self, record: dict[str, Any]) -> None:
        self._traces.insert(0, deepcopy(record))
        del self._traces[self.TRACE_BUFFER_LIMIT :]

    def list_traces(self) -> list[dict[str, Any]]:
        return deepcopy(self._traces)

    def invoke_tool(
        self,
        *,
        tool_id: str,
        payload: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
        refresh: bool = False,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        trace_id = f"mcp-trace-{uuid4().hex[:12]}"
        normalized_payload = deepcopy(payload or {})
        try:
            tool = self.get_tool(tool_id, refresh=refresh)
            runtime_config = self.parse_runtime_config(tool)
            client = self._resolve_client(tool, runtime_config)
            result = client.invoke(
                tool=deepcopy(tool),
                payload=normalized_payload,
                runtime_config=runtime_config,
                trace_context=deepcopy(trace_context or {}),
            )
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            self.record_call(str(tool.get("id") or ""), status="success")
            self._append_trace(
                {
                    "trace_id": trace_id,
                    "tool_id": str(tool.get("id") or ""),
                    "status": "success",
                    "duration_ms": elapsed_ms,
                    "called_at": _utc_now_iso(),
                    "error": None,
                }
            )
            return {
                "ok": True,
                "trace_id": trace_id,
                "duration_ms": elapsed_ms,
                "tool": {
                    "id": str(tool.get("id") or ""),
                    "name": str(tool.get("name") or ""),
                },
                "result": deepcopy(result),
            }
        except Exception as exc:
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            self.record_call(str(tool_id or ""), status="failed", error=str(exc))
            self._append_trace(
                {
                    "trace_id": trace_id,
                    "tool_id": str(tool_id or ""),
                    "status": "failed",
                    "duration_ms": elapsed_ms,
                    "called_at": _utc_now_iso(),
                    "error": {"type": exc.__class__.__name__, "message": str(exc)},
                }
            )
            if raise_on_error:
                raise
            return {
                "ok": False,
                "trace_id": trace_id,
                "duration_ms": elapsed_ms,
                "error": {"type": exc.__class__.__name__, "message": str(exc)},
            }

    def invoke_shadow_tool(
        self,
        *,
        tool_id: str,
        payload: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        result = self.invoke_tool(
            tool_id=tool_id,
            payload=payload,
            trace_context=trace_context,
            refresh=refresh,
            raise_on_error=False,
        )
        if result.get("ok"):
            self.record_shadow_call(tool_id, status="success")
        else:
            error_message = str((result.get("error") or {}).get("message") or "shadow_failed")
            self.record_shadow_call(tool_id, status="failed", error=error_message)
        return result

    def list_health(self, *, refresh: bool = False) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        counters = {
            "healthy": 0,
            "degraded": 0,
            "unknown": 0,
            "disabled": 0,
            "error": 0,
        }
        for tool in self._source_service.list_tools(refresh=refresh):
            check = self.health_for_tool(tool)
            status = str(check.get("status") or "unknown")
            counters[status] = counters.get(status, 0) + 1
            items.append(
                {
                    "tool_id": str(tool.get("id") or ""),
                    "tool_name": str(tool.get("name") or ""),
                    "source": str(tool.get("source") or ""),
                    "provider": str(tool.get("provider") or ""),
                    "source_kind": str(tool.get("source_kind") or ""),
                    "bridge_mode": str(tool.get("bridge_mode") or ""),
                    "status": status,
                    "checked_at": str(check.get("checked_at") or _utc_now_iso()),
                    "reason": str(check.get("reason") or ""),
                    "runtime": deepcopy(check.get("runtime") or {}),
                    "migration_stage": deepcopy(tool.get("migration_stage") or {}),
                    "traffic_policy": deepcopy(tool.get("traffic_policy") or {}),
                    "rollback": deepcopy(tool.get("rollback") or {}),
                    "shadow": self.recent_shadow_summary(str(tool.get("id") or "")),
                }
            )
        return {
            "items": items,
            "total": len(items),
            "summary": counters,
            "checked_at": _utc_now_iso(),
        }

    def execute_bridge(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        payload = payload or {}
        if normalized_action.endswith(":tool:doctor") or normalized_action == "doctor":
            summary = self.health_summary()
            self.record_call(normalized_action, status="success")
            return {
                "ok": True,
                "action": "doctor",
                "summary": f"已完成 {summary['total']} 个 MCP Server 的健康检查",
                "details": summary,
            }
        if normalized_action.endswith(":tool:skill") or normalized_action in {"skill-management", "skill"}:
            self.record_call(normalized_action, status="success")
            return {
                "ok": True,
                "action": "skill-management",
                "summary": "当前已暴露 skill install/uninstall 桥接入口。",
                "details": {
                    "supported_actions": ["install", "uninstall", "list"],
                    "payload": payload,
                },
            }
        server_name = normalized_action.replace("mcp:", "").split(":")[-1]
        for server in self.list_servers():
            if str(server.get("name") or "").strip().lower() == server_name:
                self.record_call(server["id"], status="success")
                return {
                    "ok": True,
                    "action": server_name,
                    "summary": f"已桥接到 MCP Server {server['name']}",
                    "details": server,
                }
        self.record_call(normalized_action, status="failed", error="not_found")
        return {
            "ok": False,
            "action": normalized_action,
            "summary": "未找到对应 MCP 桥接目标",
            "details": {"requested_action": normalized_action},
        }


mcp_runtime_service = MCPRuntimeService()
