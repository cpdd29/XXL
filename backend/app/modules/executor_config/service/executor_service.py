from __future__ import annotations

import os
from datetime import UTC, datetime
import re
import shutil
import shlex
import subprocess
from typing import Any, Literal
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


EXECUTORS_SETTING_KEY = "executors"
DEFAULT_EXECUTORS_PAYLOAD = {"items": []}
ALLOWED_DRIVER_TYPES = {"codex_cli", "claude_code_cli", "http_runner"}
ALLOWED_RUN_MODES = {"local", "remote"}
ALLOWED_WORKSPACE_POLICIES = {"tenant_sandbox", "fixed_path"}
ALLOWED_SHELL_PERMISSIONS = {"read_only", "limited_exec", "full_exec"}
ALLOWED_APPROVAL_POLICIES = {"auto", "confirm_on_risk", "always_confirm"}
ALLOWED_STATUSES = {"unknown", "online", "offline", "degraded"}
DEFAULT_ENTRY_BY_DRIVER = {
    "codex_cli": "codex",
    "claude_code_cli": "claude",
}
LOCAL_DRIVER_COMMANDS: dict[str, str] = {
    "codex_cli": "codex",
    "claude_code_cli": "claude",
}
LOCAL_DRIVER_PACKAGES: dict[str, str] = {
    "codex_cli": "@openai/codex",
    "claude_code_cli": "@anthropic-ai/claude-code",
}
LOCAL_DRIVER_TYPE_ORDER = ("codex_cli", "claude_code_cli")
REMOTE_DRIVER_TYPES = ["http_runner"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _slugify_fragment(value: Any) -> str:
    lowered = _normalize_text(value).lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered)
    return normalized.strip("-")


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalize_text(value).lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value in {None, ""}:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return max(minimum, min(maximum, normalized))


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace("\r", "\n").replace(",", "\n").split("\n")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    items: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = _normalize_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _clone_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return store.clone(value)
    return {}


def _read_setting_with_source(key: str) -> tuple[dict[str, Any] | None, bool]:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        persisted_setting, database_authoritative = read_setting(key)
        if persisted_setting is not None or database_authoritative:
            return persisted_setting, database_authoritative
        if getattr(persistence_service, "enabled", False):
            return None, True
        return None, False

    persisted_setting = persistence_service.get_system_setting(key)
    if persisted_setting is not None:
        return persisted_setting, True
    if getattr(persistence_service, "enabled", False):
        return None, True
    return None, False


def _normalize_driver_type(value: Any, *, default: str) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_DRIVER_TYPES:
        return normalized
    return default


def _normalize_run_mode(value: Any, *, default: str, driver_type: str) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_RUN_MODES:
        return normalized
    if driver_type == "http_runner":
        return "remote"
    return default


def _normalize_workspace_policy(value: Any, *, default: str) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_WORKSPACE_POLICIES:
        return normalized
    return default


def _normalize_shell_permission(value: Any, *, default: str) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_SHELL_PERMISSIONS:
        return normalized
    return default


def _normalize_approval_policy(value: Any, *, default: str) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_APPROVAL_POLICIES:
        return normalized
    return default


def _normalize_status(value: Any, *, default: str) -> str:
    normalized = _normalize_text(value).lower()
    if normalized in ALLOWED_STATUSES:
        return normalized
    return default


def _normalize_executor_item(
    payload: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    source = store.clone(existing) if isinstance(existing, dict) else {}
    source.update(_clone_dict(payload))

    executor_id = _normalize_text(source.get("id") or source.get("executor_id") or source.get("executorId"))
    if not executor_id:
        return None

    driver_default = _normalize_driver_type(source.get("driver_type") or source.get("driverType"), default="codex_cli")
    run_mode_default = "remote" if driver_default == "http_runner" else "local"
    run_mode = _normalize_run_mode(
        source.get("run_mode") or source.get("runMode"),
        default=run_mode_default,
        driver_type=driver_default,
    )
    entry = _normalize_text(source.get("entry"))
    if not entry and run_mode == "local":
        entry = DEFAULT_ENTRY_BY_DRIVER.get(driver_default, "")

    health_path = _normalize_text(source.get("health_path") or source.get("healthPath"))
    if run_mode == "remote" and not health_path:
        health_path = "/health"

    metadata = _clone_dict(source.get("metadata"))

    return {
        "id": executor_id,
        "name": _normalize_text(source.get("name")) or executor_id,
        "description": _normalize_text(source.get("description")),
        "driver_type": driver_default,
        "run_mode": run_mode,
        "entry": entry,
        "health_path": health_path,
        "workspace_policy": _normalize_workspace_policy(
            source.get("workspace_policy") or source.get("workspacePolicy"),
            default="tenant_sandbox",
        ),
        "shell_permission": _normalize_shell_permission(
            source.get("shell_permission") or source.get("shellPermission"),
            default="limited_exec",
        ),
        "approval_policy": _normalize_approval_policy(
            source.get("approval_policy") or source.get("approvalPolicy"),
            default="confirm_on_risk",
        ),
        "blocked_commands": _normalize_list(source.get("blocked_commands") or source.get("blockedCommands")),
        "timeout_seconds": _coerce_int(
            source.get("timeout_seconds") or source.get("timeoutSeconds"),
            default=120,
            minimum=10,
            maximum=3600,
        ),
        "enabled": _coerce_bool(source.get("enabled"), default=True),
        "status": _normalize_status(source.get("status"), default="unknown"),
        "last_validated_at": _normalize_text(source.get("last_validated_at") or source.get("lastValidatedAt")) or None,
        "last_health_at": _normalize_text(source.get("last_health_at") or source.get("lastHealthAt")) or None,
        "last_error": _normalize_text(source.get("last_error") or source.get("lastError")) or None,
        "validation_message": _normalize_text(
            source.get("validation_message") or source.get("validationMessage")
        ) or None,
        "version_info": _normalize_text(source.get("version_info") or source.get("versionInfo")) or None,
        "metadata": metadata,
    }


def _normalize_executor_store_payload(payload: Any) -> dict[str, Any]:
    items_source = payload
    if isinstance(payload, dict):
        items_source = payload.get("items", [])
    if not isinstance(items_source, list):
        items_source = []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items_source:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_executor_item(raw)
        if normalized is None:
            continue
        executor_id = str(normalized.get("id") or "").strip()
        if not executor_id or executor_id in seen:
            continue
        seen.add(executor_id)
        items.append(normalized)
    return {"items": items}


def _sync_runtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_executor_store_payload(payload)
    store.system_settings[EXECUTORS_SETTING_KEY] = store.clone(normalized)
    return store.clone(normalized)


def _current_executor_payload() -> tuple[dict[str, Any], str]:
    persisted_setting, database_authoritative = _read_setting_with_source(EXECUTORS_SETTING_KEY)
    if persisted_setting is not None:
        payload = _normalize_executor_store_payload(persisted_setting.get("payload") or {})
        return _sync_runtime_payload(payload), _normalize_text(persisted_setting.get("updated_at"))

    if database_authoritative:
        payload = _normalize_executor_store_payload(DEFAULT_EXECUTORS_PAYLOAD)
        return _sync_runtime_payload(payload), ""

    cached_payload = store.system_settings.get(EXECUTORS_SETTING_KEY)
    if isinstance(cached_payload, dict):
        payload = _normalize_executor_store_payload(cached_payload)
        return _sync_runtime_payload(payload), ""

    payload = _normalize_executor_store_payload(DEFAULT_EXECUTORS_PAYLOAD)
    return _sync_runtime_payload(payload), ""


def _persist_executor_payload(payload: dict[str, Any]) -> str:
    normalized = _sync_runtime_payload(payload)
    updated_at = _now_iso()
    persistence_service.persist_system_setting(
        key=EXECUTORS_SETTING_KEY,
        payload=normalized,
        updated_at=updated_at,
    )
    return updated_at


def _find_executor_index(items: list[dict[str, Any]], executor_id: str) -> int:
    normalized_id = _normalize_text(executor_id)
    for index, item in enumerate(items):
        if _normalize_text(item.get("id")) == normalized_id:
            return index
    return -1


def _generate_executor_id(payload: dict[str, Any], existing_items: list[dict[str, Any]]) -> str:
    existing_ids = {
        _normalize_text(item.get("id"))
        for item in existing_items
        if _normalize_text(item.get("id"))
    }
    driver_type = _normalize_driver_type(
        payload.get("driver_type") or payload.get("driverType"),
        default="codex_cli",
    )
    driver_prefix_map = {
        "codex_cli": "codex",
        "claude_code_cli": "claude",
        "http_runner": "http",
    }
    driver_prefix = driver_prefix_map.get(driver_type, "runner")
    name_fragment = _slugify_fragment(payload.get("name"))

    base = f"executor-{driver_prefix}"
    if name_fragment:
        base = f"{base}-{name_fragment}"
    base = base[:56].rstrip("-") or "executor"

    if base not in existing_ids:
        return base

    for _ in range(8):
        candidate = f"{base}-{uuid4().hex[:6]}"
        if candidate not in existing_ids:
            return candidate
    return f"executor-{uuid4().hex[:10]}"


def _resolve_local_cli_command(executor: dict[str, Any]) -> str:
    entry = _normalize_text(executor.get("entry"))
    if entry:
        try:
            parts = shlex.split(entry)
            if parts:
                return _normalize_text(parts[0])
        except ValueError:
            pass
        if " " in entry:
            return entry.split(" ")[0].strip()
        return entry

    driver_type = _normalize_text(executor.get("driver_type"))
    return DEFAULT_ENTRY_BY_DRIVER.get(driver_type, "")


def _resolve_executable_path(command: str) -> str | None:
    normalized = _normalize_text(command)
    if not normalized:
        return None

    if os.path.sep in normalized:
        return normalized if os.path.isfile(normalized) else None

    resolved = shutil.which(normalized)
    if resolved:
        return resolved

    for directory in (
        "/usr/local/bin",
        "/opt/homebrew/bin",
        os.path.expanduser("~/.local/bin"),
    ):
        candidate = os.path.join(directory, normalized)
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_remote_health_url(executor: dict[str, Any]) -> str:
    entry = _normalize_text(executor.get("entry"))
    if not entry:
        raise ValueError("entry 为空，无法进行远程健康检查")

    parsed = urlparse(entry)
    if not parsed.scheme:
        entry = f"http://{entry}"
        parsed = urlparse(entry)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("entry 必须为 http/https 地址")

    health_path = _normalize_text(executor.get("health_path")) or "/health"
    if health_path.startswith("http://") or health_path.startswith("https://"):
        return health_path
    return urljoin(f"{entry.rstrip('/')}/", health_path.lstrip("/"))


def _check_local_executor(executor: dict[str, Any]) -> tuple[bool, str, dict[str, Any], str | None]:
    command = _resolve_local_cli_command(executor)
    if not command:
        return False, "未配置可执行命令(entry)", {"check_type": "cli_version"}, None
    executable = _resolve_executable_path(command)
    if not executable:
        return (
            False,
            f"命令不存在: {command}",
            {
                "check_type": "cli_version",
                "command": command,
                "path_hint": _normalize_text(os.environ.get("PATH")),
            },
            None,
        )

    timeout_seconds = _coerce_int(executor.get("timeout_seconds"), default=120, minimum=10, maximum=3600)
    limited_timeout = max(3, min(timeout_seconds, 20))

    try:
        completed = subprocess.run(  # noqa: S603
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=limited_timeout,
            check=False,
        )
    except FileNotFoundError:
        return (
            False,
            f"命令不存在: {command}",
            {
                "check_type": "cli_version",
                "command": command,
                "resolved_command": executable,
            },
            None,
        )
    except subprocess.TimeoutExpired:
        return (
            False,
            f"执行超时: {command} --version",
            {
                "check_type": "cli_version",
                "command": command,
                "resolved_command": executable,
                "timeout_seconds": limited_timeout,
            },
            None,
        )
    except Exception as exc:
        return (
            False,
            f"执行失败: {exc}",
            {
                "check_type": "cli_version",
                "command": command,
                "resolved_command": executable,
            },
            None,
        )

    output = _normalize_text(completed.stdout) or _normalize_text(completed.stderr)
    version_info = output.splitlines()[0].strip() if output else None
    details = {
        "check_type": "cli_version",
        "command": command,
        "resolved_command": executable,
        "exit_code": int(completed.returncode),
        "output": output[:300],
    }
    if completed.returncode == 0:
        return True, "CLI 校验通过", details, version_info
    return False, "CLI 校验失败", details, version_info


def _detect_local_driver_capability(driver_type: str, command: str) -> dict[str, Any]:
    resolved_path = _resolve_executable_path(command)
    capability: dict[str, Any] = {
        "driver_type": driver_type,
        "command": command,
        "installed": bool(resolved_path),
        "resolved_path": resolved_path,
        "version_info": None,
    }
    if not resolved_path:
        return capability

    try:
        completed = subprocess.run(  # noqa: S603
            [resolved_path, "--version"],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
    except Exception:
        return capability

    output = _normalize_text(completed.stdout) or _normalize_text(completed.stderr)
    if output:
        capability["version_info"] = output.splitlines()[0].strip()
    return capability


def _project_runtime_status(executor: dict[str, Any]) -> dict[str, Any]:
    projected = store.clone(executor)
    run_mode = _normalize_text(projected.get("run_mode")).lower()
    driver_type = _normalize_text(projected.get("driver_type")).lower()
    if run_mode == "remote" or driver_type == "http_runner":
        return projected

    command = _resolve_local_cli_command(projected)
    capability = _detect_local_driver_capability(driver_type, command)
    if capability.get("installed"):
        version_info = _normalize_text(capability.get("version_info")) or None
        if version_info:
            projected["version_info"] = version_info
        return projected

    projected["status"] = "offline"
    projected["last_error"] = f"当前后端运行环境未检测到命令: {command}" if command else "当前后端运行环境未检测到本地执行器命令"
    projected["validation_message"] = "当前后端运行环境缺少本地执行器 CLI"
    return projected


def _install_npm_global_package(package_name: str) -> tuple[bool, str]:
    npm_executable = _resolve_executable_path("npm")
    if not npm_executable:
        return False, "未找到 npm 命令，请先安装 Node.js/npm。"

    try:
        completed = subprocess.run(  # noqa: S603
            [npm_executable, "install", "-g", package_name],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"安装超时: npm install -g {package_name}"
    except Exception as exc:
        return False, f"安装失败: {exc}"

    output = _normalize_text(completed.stdout) or _normalize_text(completed.stderr)
    if completed.returncode == 0:
        if output:
            return True, output.splitlines()[-1].strip()
        return True, "安装完成"

    if output:
        return False, output[:300]
    return False, f"npm install 返回非零退出码: {completed.returncode}"


def _check_remote_executor(executor: dict[str, Any]) -> tuple[bool, str, dict[str, Any], str | None]:
    url = _resolve_remote_health_url(executor)
    timeout_seconds = _coerce_int(executor.get("timeout_seconds"), default=120, minimum=10, maximum=3600)
    limited_timeout = max(3, min(timeout_seconds, 20))

    try:
        with httpx.Client(timeout=limited_timeout, follow_redirects=True, trust_env=False) as client:
            response = client.get(url)
    except Exception as exc:
        return (
            False,
            f"远程健康检查失败: {exc}",
            {"check_type": "http_health", "url": url, "timeout_seconds": limited_timeout},
            None,
        )

    body_preview = _normalize_text(response.text)[:300]
    details = {
        "check_type": "http_health",
        "url": url,
        "status_code": int(response.status_code),
        "response_preview": body_preview,
    }
    if 200 <= response.status_code < 300:
        return True, "远程健康检查通过", details, f"HTTP {response.status_code}"
    return False, "远程健康检查失败", details, f"HTTP {response.status_code}"


def _run_executor_check(
    executor: dict[str, Any],
    *,
    check_kind: Literal["validate", "health"],
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_mode = _normalize_text(executor.get("run_mode")).lower()
    driver_type = _normalize_text(executor.get("driver_type")).lower()

    if run_mode == "remote" or driver_type == "http_runner":
        ok, message, details, version_info = _check_remote_executor(executor)
    else:
        ok, message, details, version_info = _check_local_executor(executor)

    checked_at = _now_iso()
    updated = store.clone(executor)
    updated["status"] = "online" if ok else "offline"
    updated["validation_message"] = message
    updated["last_error"] = None if ok else message
    if version_info:
        updated["version_info"] = version_info
    if check_kind == "validate":
        updated["last_validated_at"] = checked_at
    if check_kind == "health":
        updated["last_health_at"] = checked_at

    result = {
        "ok": ok,
        "message": message,
        "details": {
            **details,
            "checked_at": checked_at,
            "check_kind": check_kind,
        },
    }
    return updated, result


def list_executors() -> dict[str, Any]:
    payload, updated_at = _current_executor_payload()
    items = [_project_runtime_status(item) for item in store.clone(payload.get("items") or [])]
    return {
        "items": items,
        "total": len(items),
        "updated_at": updated_at,
    }


def get_executor_runtime_capabilities() -> dict[str, Any]:
    local_drivers: list[dict[str, Any]] = []
    available_local_driver_types: list[str] = []
    missing_local_driver_types: list[str] = []

    for driver_type, command in LOCAL_DRIVER_COMMANDS.items():
        capability = _detect_local_driver_capability(driver_type, command)
        local_drivers.append(capability)
        if capability["installed"]:
            available_local_driver_types.append(driver_type)
        else:
            missing_local_driver_types.append(driver_type)

    return {
        "local_drivers": local_drivers,
        "available_local_driver_types": available_local_driver_types,
        "missing_local_driver_types": missing_local_driver_types,
        "remote_driver_types": REMOTE_DRIVER_TYPES,
        "detected_at": _now_iso(),
    }


def install_missing_local_drivers(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = _clone_dict(payload) if isinstance(payload, dict) else {}
    requested_targets = request_payload.get("targets")
    requested_driver_types: list[str] = []
    if isinstance(requested_targets, list):
        for raw in requested_targets:
            normalized = _normalize_text(raw).lower()
            if normalized in LOCAL_DRIVER_COMMANDS and normalized not in requested_driver_types:
                requested_driver_types.append(normalized)

    capabilities_before = get_executor_runtime_capabilities()
    missing_before = set(capabilities_before.get("missing_local_driver_types") or [])

    if requested_driver_types:
        target_driver_types = [
            driver_type
            for driver_type in LOCAL_DRIVER_TYPE_ORDER
            if driver_type in requested_driver_types
        ]
    else:
        target_driver_types = [
            driver_type
            for driver_type in LOCAL_DRIVER_TYPE_ORDER
            if driver_type in missing_before
        ]

    if not target_driver_types:
        capabilities_after = get_executor_runtime_capabilities()
        return {
            "ok": True,
            "message": "当前没有需要安装的本地执行器 CLI。",
            "results": [],
            "capabilities": capabilities_after,
        }

    results: list[dict[str, Any]] = []
    for driver_type in target_driver_types:
        command = LOCAL_DRIVER_COMMANDS[driver_type]
        package_name = LOCAL_DRIVER_PACKAGES[driver_type]

        before_capability = _detect_local_driver_capability(driver_type, command)
        if before_capability.get("installed"):
            results.append(
                {
                    "driver_type": driver_type,
                    "command": command,
                    "package_name": package_name,
                    "attempted": False,
                    "installed": True,
                    "resolved_path": before_capability.get("resolved_path"),
                    "version_info": before_capability.get("version_info"),
                    "message": "已安装，无需重复安装。",
                }
            )
            continue

        install_ok, install_message = _install_npm_global_package(package_name)
        after_capability = _detect_local_driver_capability(driver_type, command)
        installed = bool(after_capability.get("installed"))
        results.append(
            {
                "driver_type": driver_type,
                "command": command,
                "package_name": package_name,
                "attempted": True,
                "installed": installed,
                "resolved_path": after_capability.get("resolved_path"),
                "version_info": after_capability.get("version_info"),
                "message": "安装成功。" if install_ok and installed else install_message,
            }
        )

    capabilities_after = get_executor_runtime_capabilities()
    installed_count = sum(1 for item in results if item.get("installed"))
    total_count = len(results)
    ok = installed_count == total_count
    summary = (
        f"安装完成（{installed_count}/{total_count}）。"
        if ok
        else f"安装部分失败（{installed_count}/{total_count}），请查看失败项。"
    )

    return {
        "ok": ok,
        "message": summary,
        "results": results,
        "capabilities": capabilities_after,
    }


def get_executor(executor_id: str) -> dict[str, Any]:
    payload, _ = _current_executor_payload()
    items = payload.get("items") or []
    index = _find_executor_index(items, executor_id)
    if index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Executor not found")
    return _project_runtime_status(items[index])


def create_executor(payload: dict[str, Any]) -> dict[str, Any]:
    current_payload, _ = _current_executor_payload()
    items = list(current_payload.get("items") or [])

    incoming_payload = _clone_dict(payload)
    if not _normalize_text(incoming_payload.get("id")):
        incoming_payload["id"] = _generate_executor_id(incoming_payload, items)

    normalized = _normalize_executor_item(incoming_payload)
    if normalized is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid executor payload")
    if not _normalize_text(normalized.get("name")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="executor name is required")

    if _find_executor_index(items, normalized["id"]) >= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Executor already exists")

    items.append(normalized)
    _persist_executor_payload({"items": items})
    return {
        "ok": True,
        "message": f"Executor {normalized['name']} created",
        "executor": normalized,
    }


def update_executor(executor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current_payload, _ = _current_executor_payload()
    items = list(current_payload.get("items") or [])
    index = _find_executor_index(items, executor_id)
    if index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Executor not found")

    existing = items[index]
    if "id" in payload and _normalize_text(payload.get("id")) and _normalize_text(payload.get("id")) != _normalize_text(executor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Executor id cannot be changed")

    updated = _normalize_executor_item(payload, existing=existing)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid executor payload")

    items[index] = updated
    _persist_executor_payload({"items": items})
    return {
        "ok": True,
        "message": f"Executor {updated['name']} updated",
        "executor": updated,
    }


def delete_executor(executor_id: str) -> dict[str, Any]:
    current_payload, _ = _current_executor_payload()
    items = list(current_payload.get("items") or [])
    index = _find_executor_index(items, executor_id)
    if index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Executor not found")

    removed = items.pop(index)
    _persist_executor_payload({"items": items})
    return {
        "ok": True,
        "message": f"Executor {removed['name']} deleted",
        "executor_id": _normalize_text(removed.get("id")),
    }


def validate_executor(executor_id: str) -> dict[str, Any]:
    current_payload, _ = _current_executor_payload()
    items = list(current_payload.get("items") or [])
    index = _find_executor_index(items, executor_id)
    if index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Executor not found")

    updated, result = _run_executor_check(items[index], check_kind="validate")
    items[index] = updated
    persisted_at = _persist_executor_payload({"items": items})
    return {
        "ok": bool(result.get("ok")),
        "message": str(result.get("message") or ""),
        "executor": updated,
        "details": {
            **_clone_dict(result.get("details")),
            "persisted_at": persisted_at,
        },
    }


def health_check_executor(executor_id: str) -> dict[str, Any]:
    current_payload, _ = _current_executor_payload()
    items = list(current_payload.get("items") or [])
    index = _find_executor_index(items, executor_id)
    if index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Executor not found")

    updated, result = _run_executor_check(items[index], check_kind="health")
    items[index] = updated
    persisted_at = _persist_executor_payload({"items": items})
    return {
        "ok": bool(result.get("ok")),
        "message": str(result.get("message") or ""),
        "executor": updated,
        "details": {
            **_clone_dict(result.get("details")),
            "persisted_at": persisted_at,
        },
    }
