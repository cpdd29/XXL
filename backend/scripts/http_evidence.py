from __future__ import annotations

import json
from typing import Any, Callable
from urllib import error, request


def parse_key_value_specs(specs: list[str], *, lower_keys: bool = False) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in specs:
        value = str(raw or "").strip()
        if not value:
            continue
        if "=" not in value:
            raise ValueError(f"Invalid spec: {raw}. Expected format: key=value")
        key, item = value.split("=", 1)
        normalized_key = key.strip().lower() if lower_keys else key.strip()
        normalized_value = item.strip()
        if not normalized_key or not normalized_value:
            raise ValueError(f"Invalid spec: {raw}. Expected format: key=value")
        parsed[normalized_key] = normalized_value
    return parsed


def json_request(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 3.0,
    opener: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    request_headers = dict(headers or {})
    body_bytes: bytes | None = None
    if payload is not None:
        body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    req = request.Request(
        url=url,
        data=body_bytes,
        headers=request_headers,
        method=method.upper(),
    )
    try:
        with opener(req, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", 200))
            body = response.read()
            text = body.decode("utf-8", errors="replace")
            try:
                payload_json = json.loads(text) if text.strip() else None
            except json.JSONDecodeError:
                payload_json = None
            return {
                "ok": 200 <= status_code < 400,
                "status_code": status_code,
                "url": url,
                "method": method.upper(),
                "headers": request_headers,
                "text": text,
                "json": payload_json,
                "error": None,
            }
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            payload_json = json.loads(text) if text.strip() else None
        except json.JSONDecodeError:
            payload_json = None
        return {
            "ok": False,
            "status_code": int(exc.code),
            "url": url,
            "method": method.upper(),
            "headers": request_headers,
            "text": text,
            "json": payload_json,
            "error": f"HTTPError: {exc.reason}",
        }
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return {
            "ok": False,
            "status_code": 0,
            "url": url,
            "method": method.upper(),
            "headers": request_headers,
            "text": "",
            "json": None,
            "error": f"URLError: {reason}",
        }
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "status_code": 0,
            "url": url,
            "method": method.upper(),
            "headers": request_headers,
            "text": "",
            "json": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def login_access_token(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout_seconds: float = 5.0,
    login_path: str = "/api/auth/login",
    opener: Callable[..., Any] = request.urlopen,
) -> str:
    normalized_base = str(base_url or "").rstrip("/")
    normalized_path = login_path if login_path.startswith("/") else f"/{login_path}"
    response = json_request(
        url=f"{normalized_base}{normalized_path}",
        method="POST",
        headers={"Content-Type": "application/json"},
        payload={"email": email, "password": password},
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    if not response["ok"]:
        raise RuntimeError(response["error"] or f"login failed with status {response['status_code']}")
    payload = response["json"] if isinstance(response["json"], dict) else {}
    access_token = str(payload.get("accessToken") or payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("login response missing access token")
    return access_token
