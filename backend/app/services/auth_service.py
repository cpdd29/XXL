from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import hmac
import json
import logging
import secrets
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.config import get_settings
from app.services.persistence_service import persistence_service
from app.services.store import store


logger = logging.getLogger(__name__)
PASSWORD_HASH_ITERATIONS = 200_000
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
DATABASE_LOOKUP_FOUND = "found"
DATABASE_LOOKUP_MISSING = "missing"
DATABASE_LOOKUP_UNAVAILABLE = "unavailable"
DATABASE_LOOKUP_DISABLED = "disabled"
AUTH_STORAGE_UNAVAILABLE_DETAIL = "Authentication service temporarily unavailable"


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp_string() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def build_password_record(password: str) -> dict[str, str | int]:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    return {
        "auth_password_salt": salt,
        "auth_password_hash": derived.hex(),
        "auth_password_iterations": PASSWORD_HASH_ITERATIONS,
    }


def _profile_has_password(profile: dict[str, Any] | None) -> bool:
    if not isinstance(profile, dict):
        return False
    return bool(
        profile.get("auth_password_hash")
        or profile.get("auth_password")
        or profile.get("password")
    )


def _verify_password(profile: dict[str, Any] | None, password: str, *, fallback_password: str | None) -> bool:
    if profile:
        stored_hash = str(profile.get("auth_password_hash") or "")
        stored_salt = str(profile.get("auth_password_salt") or "")
        if stored_hash and stored_salt:
            iterations = int(profile.get("auth_password_iterations") or PASSWORD_HASH_ITERATIONS)
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                stored_salt.encode("utf-8"),
                iterations,
            ).hex()
            return hmac.compare_digest(candidate, stored_hash)

        plaintext = profile.get("auth_password") or profile.get("password")
        if plaintext is not None:
            return hmac.compare_digest(str(plaintext), password)

    if fallback_password is not None:
        return hmac.compare_digest(fallback_password, password)
    return False


def _encode_token(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    signature_segment = _base64url_encode(hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest())
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _decode_token(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    header_segment, payload_segment, signature_segment = parts
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    expected_signature = _base64url_encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected_signature, signature_segment):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        payload = json.loads(_base64url_decode(payload_segment))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    expires_at = int(payload.get("exp") or 0)
    if expires_at <= int(_utc_now().timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return payload


def _find_runtime_user_by_email(email: str) -> dict[str, Any] | None:
    for item in store.users:
        if _normalize_email(str(item.get("email") or "")) == email:
            return store.clone(item)
    return None


def _ensure_runtime_user(user: dict[str, Any]) -> dict[str, Any]:
    user_id = str(user["id"])
    for index, item in enumerate(store.users):
        if item["id"] == user_id:
            store.users[index] = store.clone(user)
            return store.users[index]

    store.users.append(store.clone(user))
    return store.users[-1]


def _ensure_runtime_profile(profile: dict[str, Any]) -> dict[str, Any]:
    user_id = str(profile.get("id") or profile.get("user_id") or "")
    if not user_id:
        raise KeyError("User profile requires id or user_id")
    store.user_profiles[user_id] = store.clone(profile)
    return store.user_profiles[user_id]


def _delete_runtime_profile(user_id: str) -> None:
    store.user_profiles.pop(user_id, None)


def _raise_auth_storage_unavailable(*, reason: str) -> None:
    logger.warning("Auth database lookup unavailable: %s", reason)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=AUTH_STORAGE_UNAVAILABLE_DETAIL,
    )


def _get_database_user_by_email(email: str) -> tuple[dict[str, Any] | None, str]:
    if not getattr(persistence_service, "enabled", False):
        return None, DATABASE_LOOKUP_DISABLED

    database_user = persistence_service.get_user_by_email(email)
    if database_user is not None:
        return database_user, DATABASE_LOOKUP_FOUND

    database_candidates = persistence_service.list_users(search=email)
    if database_candidates is None:
        return None, DATABASE_LOOKUP_UNAVAILABLE

    for candidate in database_candidates:
        if _normalize_email(str(candidate.get("email") or "")) == email:
            return candidate, DATABASE_LOOKUP_FOUND
    return None, DATABASE_LOOKUP_MISSING


def _get_database_user_by_id(user_id: str) -> tuple[dict[str, Any] | None, str]:
    if not getattr(persistence_service, "enabled", False):
        return None, DATABASE_LOOKUP_DISABLED

    database_user = persistence_service.get_user(user_id)
    if database_user is not None:
        return database_user, DATABASE_LOOKUP_FOUND

    database_users = persistence_service.list_users()
    if database_users is None:
        return None, DATABASE_LOOKUP_UNAVAILABLE

    for candidate in database_users:
        if str(candidate.get("id") or "").strip() == user_id:
            return candidate, DATABASE_LOOKUP_FOUND
    return None, DATABASE_LOOKUP_MISSING


def _get_user_and_profile_by_email(email: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    database_user, database_status = _get_database_user_by_email(email)
    if database_status == DATABASE_LOOKUP_FOUND:
        if database_user is None:
            return None, None
        return database_user, persistence_service.get_user_profile(str(database_user["id"]))
    if database_status == DATABASE_LOOKUP_MISSING:
        return None, None
    if database_status == DATABASE_LOOKUP_UNAVAILABLE:
        _raise_auth_storage_unavailable(reason=f"email={email}")

    runtime_user = _find_runtime_user_by_email(email)
    if runtime_user is None:
        return None, None
    runtime_profile = store.user_profiles.get(str(runtime_user["id"]))
    return runtime_user, store.clone(runtime_profile) if runtime_profile is not None else None


def _get_user_by_id(user_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    database_user, database_status = _get_database_user_by_id(user_id)
    if database_status == DATABASE_LOOKUP_FOUND:
        if database_user is None:
            return None, None
        return database_user, persistence_service.get_user_profile(user_id)
    if database_status == DATABASE_LOOKUP_MISSING:
        return None, None
    if database_status == DATABASE_LOOKUP_UNAVAILABLE:
        _raise_auth_storage_unavailable(reason=f"user_id={user_id}")

    for item in store.users:
        if item["id"] == user_id:
            runtime_profile = store.user_profiles.get(user_id)
            return store.clone(item), store.clone(runtime_profile) if runtime_profile is not None else None
    return None, None


def _demo_admin_user_payload() -> dict[str, Any]:
    settings = get_settings()
    demo_user = store.clone(store.demo_user)
    return {
        "id": demo_user["id"],
        "name": demo_user["name"],
        "email": settings.demo_admin_email,
        "role": demo_user["role"],
        "status": "active",
        "last_login": "",
        "total_interactions": 0,
        "created_at": _utc_now().date().isoformat(),
    }


def _is_default_demo_admin_user(user: dict[str, Any] | None) -> bool:
    if user is None:
        return True

    settings = get_settings()
    demo_user = store.demo_user
    return (
        str(user.get("id") or "").strip() == str(demo_user.get("id") or "").strip()
        and _normalize_email(str(user.get("email") or "")) == _normalize_email(settings.demo_admin_email)
    )


def _ensure_demo_admin_account() -> tuple[dict[str, Any], dict[str, Any] | None]:
    settings = get_settings()
    user, _profile = _get_user_and_profile_by_email(_normalize_email(settings.demo_admin_email))
    if user is None:
        user = _demo_admin_user_payload()

    mutable_user = _ensure_runtime_user(user)
    user_id = str(mutable_user["id"])
    _delete_runtime_profile(user_id)
    delete_profiles = getattr(persistence_service, "delete_user_profiles", None)
    if callable(delete_profiles):
        delete_profiles(user_ids=[user_id])
    _persist_login_state(mutable_user, None)
    return mutable_user, None


def _issue_token_pair(user: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    now = int(_utc_now().timestamp())
    base_payload = {
        "sub": str(user["id"]),
        "email": str(user["email"]),
        "role": str(user["role"]),
        "iat": now,
    }
    access_token = _encode_token(
        {
            **base_payload,
            "type": ACCESS_TOKEN_TYPE,
            "exp": now + settings.auth_access_token_ttl_seconds,
        },
        settings.auth_jwt_secret,
    )
    refresh_token = _encode_token(
        {
            **base_payload,
            "type": REFRESH_TOKEN_TYPE,
            "exp": now + settings.auth_refresh_token_ttl_seconds,
        },
        settings.auth_jwt_secret,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.auth_access_token_ttl_seconds,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
        },
    }


def _public_user_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["id"]),
        "name": str(user["name"]),
        "email": str(user["email"]),
        "role": str(user["role"]),
        "status": str(user.get("status") or "active"),
    }


def _record_auth_audit_log(*, user: str, status_text: str, details: str) -> None:
    log_payload = {
        "id": f"audit-auth-{uuid4().hex}",
        "timestamp": _timestamp_string(),
        "action": "用户登录" if status_text == "success" else "登录失败",
        "user": user,
        "resource": "认证系统",
        "status": status_text,
        "ip": "-",
        "details": details,
    }
    store.audit_logs.insert(0, store.clone(log_payload))
    persistence_service.append_audit_log(log=log_payload)


def _persist_login_state(user: dict[str, Any], profile: dict[str, Any] | None) -> None:
    if not persistence_service.persist_user_state(user=user, profile=profile):
        logger.debug("User login state was not persisted to database")


class AuthService:
    def login(self, email: str, password: str) -> dict[str, Any]:
        settings = get_settings()
        normalized_email = _normalize_email(email)
        fallback_password = None
        user, profile = _get_user_and_profile_by_email(normalized_email)
        is_demo_admin_login = normalized_email == _normalize_email(settings.demo_admin_email)
        if is_demo_admin_login and _is_default_demo_admin_user(user):
            profile = None

        if (
            settings.auth_demo_fallback_enabled
            and is_demo_admin_login
            and hmac.compare_digest(settings.demo_admin_password, password)
            and _is_default_demo_admin_user(user)
            and not _profile_has_password(profile)
        ):
            user, profile = _ensure_demo_admin_account()
            fallback_password = settings.demo_admin_password

        if user is None:
            _record_auth_audit_log(
                user=normalized_email or "anonymous",
                status_text="error",
                details="登录失败：账号不存在或密码错误",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if str(user.get("status") or "active").lower() != "active":
            _record_auth_audit_log(
                user=str(user["email"]),
                status_text="warning",
                details="登录失败：账号已被停用",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active",
            )

        if not _verify_password(profile, password, fallback_password=fallback_password):
            _record_auth_audit_log(
                user=str(user["email"]),
                status_text="error",
                details="登录失败：账号不存在或密码错误",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        now_text = _timestamp_string()
        mutable_user = _ensure_runtime_user({**store.clone(user), "last_login": now_text})
        mutable_profile = None
        if profile is not None:
            profile_payload = {**store.clone(profile), "last_login": now_text}
            mutable_profile = _ensure_runtime_profile(profile_payload)
        else:
            _delete_runtime_profile(str(mutable_user["id"]))

        _persist_login_state(mutable_user, mutable_profile)
        _record_auth_audit_log(
            user=str(mutable_user["email"]),
            status_text="success",
            details="管理员登录成功",
        )
        return _issue_token_pair(mutable_user)

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        settings = get_settings()
        payload = _decode_token(refresh_token, settings.auth_jwt_secret)
        if payload.get("type") != REFRESH_TOKEN_TYPE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user_id = str(payload.get("sub") or "")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user, _profile = _get_user_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if str(user.get("status") or "active").lower() != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
        return _issue_token_pair(_ensure_runtime_user(user))

    def authenticate_access_token(self, access_token: str) -> dict[str, Any]:
        settings = get_settings()
        payload = _decode_token(access_token, settings.auth_jwt_secret)
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

        user_id = str(payload.get("sub") or "")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

        user, _profile = _get_user_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if str(user.get("status") or "active").lower() != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
        return _public_user_payload(_ensure_runtime_user(user))


def login(email: str, password: str) -> dict[str, Any]:
    return AuthService().login(email, password)


def refresh(refresh_token: str) -> dict[str, Any]:
    return AuthService().refresh(refresh_token)


def authenticate_access_token(access_token: str) -> dict[str, Any]:
    return AuthService().authenticate_access_token(access_token)
