from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import httpx
import secrets

from app.modules.organization.application import profile_service as organization_profile_service
from app.modules.reception.channel_binding.schemas import (
    ConfirmWecomBindSessionRequest,
    WecomBindSession,
    WecomBindingStateResponse,
    WecomBindingStateStore,
    WecomChannelBinding,
    WecomChannelCredential,
    WecomStoredBindSession,
)
from app.platform.persistence.persistence_service import persistence_service
from app.platform.persistence.runtime_store import store


WECOM_CHANNEL_BINDING_SETTING_KEY = "reception_wecom_channel_binding"
WECOM_BIND_SESSION_TTL_MINUTES = 15
ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0
ILINK_GET_BOT_QR_ENDPOINT = "ilink/bot/get_bot_qrcode"
ILINK_GET_QR_STATUS_ENDPOINT = "ilink/bot/get_qrcode_status"

try:
    import certifi

    _HTTP_VERIFY: bool | str = certifi.where()
except Exception:  # pragma: no cover - optional dependency fallback
    _HTTP_VERIFY = True


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _now() -> datetime:
    return datetime.now(UTC)


def _now_text() -> str:
    return _now().isoformat()


def _default_state() -> WecomBindingStateStore:
    return WecomBindingStateStore()


def _normalize_state(payload: object) -> WecomBindingStateStore:
    if not isinstance(payload, dict):
        return _default_state()
    try:
        return WecomBindingStateStore.model_validate(payload)
    except Exception:
        return _default_state()


def _load_state() -> WecomBindingStateStore:
    read_setting = getattr(persistence_service, "read_system_setting", None)
    if callable(read_setting):
        persisted, authoritative = read_setting(WECOM_CHANNEL_BINDING_SETTING_KEY)
        if authoritative and isinstance(persisted, dict):
            normalized = _normalize_state(persisted.get("payload"))
            store.system_settings[WECOM_CHANNEL_BINDING_SETTING_KEY] = normalized.model_dump(mode="json")
            return normalized

    cached = store.system_settings.get(WECOM_CHANNEL_BINDING_SETTING_KEY)
    if isinstance(cached, dict):
        return _normalize_state(cached)

    default_state = _default_state()
    store.system_settings[WECOM_CHANNEL_BINDING_SETTING_KEY] = default_state.model_dump(mode="json")
    return default_state


def _persist_state(state: WecomBindingStateStore) -> None:
    dumped = state.model_dump(mode="json")
    store.system_settings[WECOM_CHANNEL_BINDING_SETTING_KEY] = store.clone(dumped)
    persistence_service.persist_system_setting(
        key=WECOM_CHANNEL_BINDING_SETTING_KEY,
        payload=deepcopy(dumped),
        updated_at=state.updated_at or _now_text(),
    )


def _resolve_canonical_tenant_binding(
    tenant_id: object | None,
    tenant_name: object | None = None,
) -> tuple[str | None, str | None]:
    return organization_profile_service.resolve_tenant_binding(tenant_id, tenant_name)


def _reconcile_state_tenant_bindings(state: WecomBindingStateStore) -> bool:
    changed = False

    next_bindings: list[WecomChannelBinding] = []
    seen_binding_tenants: set[str] = set()
    for binding in state.bindings:
        next_binding = binding.model_copy(deep=True)
        tenant_id, tenant_name = _resolve_canonical_tenant_binding(
            next_binding.tenant_id,
            next_binding.tenant_name,
        )
        if tenant_id and tenant_id != next_binding.tenant_id:
            next_binding.tenant_id = tenant_id
            changed = True
        if tenant_name and tenant_name != next_binding.tenant_name:
            next_binding.tenant_name = tenant_name
            changed = True
        normalized_tenant_id = _normalize_text(next_binding.tenant_id)
        if normalized_tenant_id and normalized_tenant_id in seen_binding_tenants:
            changed = True
            continue
        if normalized_tenant_id:
            seen_binding_tenants.add(normalized_tenant_id)
        next_bindings.append(next_binding)
    state.bindings = next_bindings

    next_credentials: list[WecomChannelCredential] = []
    seen_credential_tenants: set[str] = set()
    for credential in state.credentials:
        next_credential = credential.model_copy(deep=True)
        tenant_id, tenant_name = _resolve_canonical_tenant_binding(
            next_credential.tenant_id,
            next_credential.tenant_name,
        )
        if tenant_id and tenant_id != next_credential.tenant_id:
            next_credential.tenant_id = tenant_id
            changed = True
        if tenant_name and tenant_name != next_credential.tenant_name:
            next_credential.tenant_name = tenant_name
            changed = True
        normalized_tenant_id = _normalize_text(next_credential.tenant_id)
        if normalized_tenant_id and normalized_tenant_id in seen_credential_tenants:
            changed = True
            continue
        if normalized_tenant_id:
            seen_credential_tenants.add(normalized_tenant_id)
        next_credentials.append(next_credential)
    state.credentials = next_credentials

    next_sessions: list[WecomStoredBindSession] = []
    for session in state.sessions:
        next_session = session.model_copy(deep=True)
        tenant_id, tenant_name = _resolve_canonical_tenant_binding(
            next_session.tenant_id,
            next_session.tenant_name,
        )
        if tenant_id and tenant_id != next_session.tenant_id:
            next_session.tenant_id = tenant_id
            changed = True
        if tenant_name and tenant_name != next_session.tenant_name:
            next_session.tenant_name = tenant_name
            changed = True
        next_sessions.append(next_session)
    state.sessions = next_sessions

    if changed:
        state.updated_at = _now_text()
    return changed


def _cleanup_sessions(state: WecomBindingStateStore) -> bool:
    now = _now()
    changed = False
    normalized_sessions: list[WecomStoredBindSession] = []
    for session in state.sessions:
        next_session = session.model_copy(deep=True)
        if next_session.status == "pending":
            try:
                expires_at = datetime.fromisoformat(next_session.expires_at)
            except ValueError:
                expires_at = now - timedelta(seconds=1)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                next_session.status = "expired"
                next_session.updated_at = _now_text()
                changed = True
        normalized_sessions.append(next_session)
    state.sessions = normalized_sessions
    if changed:
        state.updated_at = _now_text()
    return changed


def _find_binding(state: WecomBindingStateStore, tenant_id: str) -> WecomChannelBinding | None:
    normalized_tenant_id = _normalize_text(tenant_id)
    if not normalized_tenant_id:
        return None
    for binding in state.bindings:
        if _normalize_text(binding.tenant_id) == normalized_tenant_id:
            return binding.model_copy(deep=True)
    return None


def _to_public_session(session: WecomStoredBindSession | None) -> WecomBindSession | None:
    if session is None:
        return None
    return WecomBindSession(
        session_id=session.session_id,
        tenant_id=session.tenant_id,
        tenant_name=session.tenant_name,
        channel=session.channel,
        status=session.status,
        bind_path=session.bind_path,
        qr_code_url=session.qr_code_url,
        scan_status=session.scan_status,
        expires_at=session.expires_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
        display_name=session.display_name,
        external_account=session.external_account,
    )


def _find_active_session_index(state: WecomBindingStateStore, tenant_id: str) -> int | None:
    normalized_tenant_id = _normalize_text(tenant_id)
    if not normalized_tenant_id:
        return None
    candidates = [
        (index, session)
        for index, session in enumerate(state.sessions)
        if _normalize_text(session.tenant_id) == normalized_tenant_id and session.status == "pending"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1].created_at, reverse=True)
    return candidates[0][0]


def _find_session_by_token(state: WecomBindingStateStore, token: str) -> WecomStoredBindSession | None:
    bind_path = f"/wechat-bind?token={_normalize_text(token)}"
    for session in state.sessions:
        if _normalize_text(session.bind_path) == bind_path:
            return session.model_copy(deep=True)
    return None


def _replace_session(state: WecomBindingStateStore, next_session: WecomStoredBindSession) -> None:
    replaced = False
    next_sessions: list[WecomStoredBindSession] = []
    for session in state.sessions:
        if _normalize_text(session.session_id) == _normalize_text(next_session.session_id):
            next_sessions.append(next_session)
            replaced = True
        else:
            next_sessions.append(session)
    if not replaced:
        next_sessions.insert(0, next_session)
    state.sessions = next_sessions[:50]


def _replace_binding(state: WecomBindingStateStore, next_binding: WecomChannelBinding) -> None:
    replaced = False
    next_bindings: list[WecomChannelBinding] = []
    for binding in state.bindings:
        if _normalize_text(binding.tenant_id) == _normalize_text(next_binding.tenant_id):
            next_bindings.append(next_binding)
            replaced = True
        else:
            next_bindings.append(binding)
    if not replaced:
        next_bindings.insert(0, next_binding)
    state.bindings = next_bindings


def _replace_credential(state: WecomBindingStateStore, next_credential: WecomChannelCredential) -> None:
    replaced = False
    next_credentials: list[WecomChannelCredential] = []
    for credential in state.credentials:
        if _normalize_text(credential.tenant_id) == _normalize_text(next_credential.tenant_id):
            next_credentials.append(next_credential)
            replaced = True
        else:
            next_credentials.append(credential)
    if not replaced:
        next_credentials.insert(0, next_credential)
    state.credentials = next_credentials


def _ilink_headers() -> dict[str, str]:
    return {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }


def _fetch_ilink_login_qr(*, bot_type: str = "3") -> dict[str, str]:
    url = f"{ILINK_BASE_URL}/{ILINK_GET_BOT_QR_ENDPOINT}?bot_type={bot_type}"
    response = httpx.get(
        url,
        headers=_ilink_headers(),
        timeout=20.0,
        follow_redirects=True,
        verify=_HTTP_VERIFY,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("微信登录二维码返回格式无效")
    if payload.get("ret") not in (None, 0):
        raise RuntimeError(f"微信登录二维码生成失败，ret={payload.get('ret')}")
    qr_code_token = _normalize_text(payload.get("qrcode"))
    qr_code_url = _normalize_text(payload.get("qrcode_img_content")) or qr_code_token
    if not qr_code_token or not qr_code_url:
        raise RuntimeError("微信登录二维码数据缺失")
    return {
        "qr_code_token": qr_code_token,
        "qr_code_url": qr_code_url,
    }


def _fetch_ilink_qr_status(qr_code_token: str, *, base_url: str | None = None) -> dict[str, object]:
    normalized_qr_code_token = _normalize_text(qr_code_token)
    if not normalized_qr_code_token:
        raise RuntimeError("微信登录二维码令牌缺失")
    request_base_url = _normalize_text(base_url) or ILINK_BASE_URL
    url = f"{request_base_url.rstrip('/')}/{ILINK_GET_QR_STATUS_ENDPOINT}?qrcode={normalized_qr_code_token}"
    response = httpx.get(
        url,
        headers=_ilink_headers(),
        timeout=20.0,
        follow_redirects=True,
        verify=_HTTP_VERIFY,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("微信登录状态返回格式无效")
    if payload.get("ret") not in (None, 0):
        raise RuntimeError(f"微信登录状态查询失败，ret={payload.get('ret')}")
    return payload


def _sync_pending_session(state: WecomBindingStateStore, index: int) -> bool:
    if index < 0 or index >= len(state.sessions):
        return False

    current_session = state.sessions[index].model_copy(deep=True)
    if current_session.status != "pending" or not _normalize_text(current_session.qr_code_token):
        return False

    try:
        payload = _fetch_ilink_qr_status(
            _normalize_text(current_session.qr_code_token),
            base_url=current_session.qr_poll_base_url,
        )
    except Exception:
        return False

    next_session = current_session.model_copy(deep=True)
    now_text = _now_text()
    changed = False

    scan_status = _normalize_text(payload.get("status")) or "wait"
    if next_session.scan_status != scan_status:
        next_session.scan_status = scan_status
        next_session.updated_at = now_text
        changed = True

    if scan_status == "scaned_but_redirect":
        redirect_host = _normalize_text(payload.get("redirect_host"))
        if redirect_host:
            next_base_url = f"https://{redirect_host}"
            if next_session.qr_poll_base_url != next_base_url:
                next_session.qr_poll_base_url = next_base_url
                next_session.updated_at = now_text
                changed = True
    elif scan_status == "expired":
        # iLink 的二维码状态存在“远端先报 expired、本地二维码短时间内仍可展示/复用”的情况。
        # 本地会话是否过期只由 expires_at 控制，避免前端二维码刚生成就被轮询清空。
        pass
    elif scan_status == "confirmed":
        account_id = _normalize_text(payload.get("ilink_bot_id"))
        access_token = _normalize_text(payload.get("bot_token"))
        base_url = _normalize_text(payload.get("baseurl")) or ILINK_BASE_URL
        user_id = _normalize_text(payload.get("ilink_user_id")) or None
        if account_id and access_token:
            next_session.status = "bound"
            next_session.external_account = user_id or account_id
            next_session.updated_at = now_text
            binding = WecomChannelBinding(
                tenant_id=next_session.tenant_id,
                tenant_name=next_session.tenant_name,
                display_name=next_session.display_name or next_session.tenant_name or "微信接入",
                external_account=user_id or account_id,
                bound_at=now_text,
                updated_at=now_text,
            )
            credential = WecomChannelCredential(
                tenant_id=next_session.tenant_id,
                tenant_name=next_session.tenant_name,
                account_id=account_id,
                access_token=access_token,
                base_url=base_url,
                user_id=user_id,
                updated_at=now_text,
            )
            _replace_binding(state, binding)
            _replace_credential(state, credential)
            changed = True

    if changed:
        state.sessions[index] = next_session
        state.updated_at = now_text
    return changed


class WecomChannelBindingService:
    def get_binding_state(self, tenant_id: str | None, tenant_name: str | None = None) -> WecomBindingStateResponse:
        state = _load_state()
        changed = _cleanup_sessions(state)
        changed = _reconcile_state_tenant_bindings(state) or changed

        normalized_tenant_id, normalized_tenant_name = _resolve_canonical_tenant_binding(
            tenant_id,
            tenant_name,
        )
        normalized_tenant_id = _normalize_text(normalized_tenant_id)
        if not normalized_tenant_id:
            if changed:
                _persist_state(state)
            return WecomBindingStateResponse()

        active_session_index = _find_active_session_index(state, normalized_tenant_id)
        if active_session_index is not None:
            changed = _sync_pending_session(state, active_session_index) or changed

        if changed:
            _persist_state(state)
        binding = _find_binding(state, normalized_tenant_id)
        refreshed_active_session_index = _find_active_session_index(state, normalized_tenant_id)
        active_session = (
            state.sessions[refreshed_active_session_index].model_copy(deep=True)
            if refreshed_active_session_index is not None
            else None
        )
        resolved_tenant_name = _normalize_text(normalized_tenant_name) or (
            binding.tenant_name if binding is not None else None
        ) or (active_session.tenant_name if active_session is not None else None)
        return WecomBindingStateResponse(
            tenant_id=normalized_tenant_id,
            tenant_name=resolved_tenant_name,
            binding=binding,
            active_session=_to_public_session(active_session),
        )

    def create_bind_session(self, tenant_id: str, tenant_name: str | None = None) -> WecomBindingStateResponse:
        resolved_tenant_id, resolved_tenant_name = _resolve_canonical_tenant_binding(tenant_id, tenant_name)
        normalized_tenant_id = _normalize_text(resolved_tenant_id)
        normalized_tenant_name = _normalize_text(resolved_tenant_name) or normalized_tenant_id
        if not normalized_tenant_id:
            raise ValueError("租户不能为空")

        qr_payload = _fetch_ilink_login_qr()

        state = _load_state()
        _cleanup_sessions(state)
        _reconcile_state_tenant_bindings(state)
        now_text = _now_text()
        next_sessions: list[WecomStoredBindSession] = []
        for session in state.sessions:
            next_session = session.model_copy(deep=True)
            if (
                _normalize_text(next_session.tenant_id) == normalized_tenant_id
                and next_session.status == "pending"
            ):
                next_session.status = "cancelled"
                next_session.updated_at = now_text
            next_sessions.append(next_session)
        state.sessions = next_sessions

        bind_token = secrets.token_urlsafe(24)
        session = WecomStoredBindSession(
            session_id=f"wecom-bind-{secrets.token_hex(8)}",
            tenant_id=normalized_tenant_id,
            tenant_name=normalized_tenant_name,
            status="pending",
            bind_path=f"/wechat-bind?token={bind_token}",
            qr_code_url=qr_payload["qr_code_url"],
            scan_status="wait",
            qr_code_token=qr_payload["qr_code_token"],
            qr_poll_base_url=ILINK_BASE_URL,
            expires_at=(_now() + timedelta(minutes=WECOM_BIND_SESSION_TTL_MINUTES)).isoformat(),
            created_at=now_text,
            updated_at=now_text,
            display_name=f"{normalized_tenant_name} 微信接入",
        )
        _replace_session(state, session)
        state.updated_at = now_text
        _persist_state(state)
        return WecomBindingStateResponse(
            tenant_id=normalized_tenant_id,
            tenant_name=normalized_tenant_name,
            binding=_find_binding(state, normalized_tenant_id),
            active_session=_to_public_session(session),
        )

    def clear_binding(self, tenant_id: str, tenant_name: str | None = None) -> WecomBindingStateResponse:
        resolved_tenant_id, resolved_tenant_name = _resolve_canonical_tenant_binding(tenant_id, tenant_name)
        normalized_tenant_id = _normalize_text(resolved_tenant_id)
        normalized_tenant_name = _normalize_text(resolved_tenant_name) or normalized_tenant_id
        if not normalized_tenant_id:
            raise ValueError("租户不能为空")

        state = _load_state()
        _cleanup_sessions(state)
        _reconcile_state_tenant_bindings(state)
        state.bindings = [
            binding
            for binding in state.bindings
            if _normalize_text(binding.tenant_id) != normalized_tenant_id
        ]
        state.credentials = [
            credential
            for credential in state.credentials
            if _normalize_text(credential.tenant_id) != normalized_tenant_id
        ]

        next_sessions: list[WecomStoredBindSession] = []
        now_text = _now_text()
        for session in state.sessions:
            if (
                _normalize_text(session.tenant_id) == normalized_tenant_id
                and session.status == "pending"
            ):
                cancelled = session.model_copy(deep=True)
                cancelled.status = "cancelled"
                cancelled.updated_at = now_text
                next_sessions.append(cancelled)
                continue
            next_sessions.append(session)
        state.sessions = next_sessions
        state.updated_at = now_text
        _persist_state(state)
        return self.get_binding_state(normalized_tenant_id, normalized_tenant_name)

    def list_credentials(self) -> list[WecomChannelCredential]:
        state = _load_state()
        changed = _cleanup_sessions(state)
        changed = _reconcile_state_tenant_bindings(state) or changed
        pending_indexes = [
            index
            for index, session in enumerate(state.sessions)
            if session.status == "pending"
        ]
        for pending_index in pending_indexes:
            changed = _sync_pending_session(state, pending_index) or changed
        if changed:
            _persist_state(state)
        return [credential.model_copy(deep=True) for credential in state.credentials]

    def get_credential(self, tenant_id: str) -> WecomChannelCredential | None:
        resolved_tenant_id, _ = _resolve_canonical_tenant_binding(tenant_id, None)
        normalized_tenant_id = _normalize_text(resolved_tenant_id)
        if not normalized_tenant_id:
            return None
        for credential in self.list_credentials():
            if _normalize_text(credential.tenant_id) == normalized_tenant_id:
                return credential
        return None

    def get_public_session(self, token: str) -> WecomBindSession:
        normalized_token = _normalize_text(token)
        if not normalized_token:
            raise LookupError("绑定会话不存在")

        state = _load_state()
        changed = _cleanup_sessions(state)
        changed = _reconcile_state_tenant_bindings(state) or changed
        if changed:
            _persist_state(state)

        session = _find_session_by_token(state, normalized_token)
        if session is None:
            raise LookupError("绑定会话不存在")
        public_session = _to_public_session(session)
        if public_session is None:
            raise LookupError("绑定会话不存在")
        return public_session

    def confirm_bind_session(
        self,
        token: str,
        payload: ConfirmWecomBindSessionRequest,
    ) -> tuple[WecomChannelBinding, WecomBindSession]:
        normalized_token = _normalize_text(token)
        display_name = _normalize_text(payload.display_name)
        external_account = _normalize_text(payload.external_account) or None
        if not normalized_token:
            raise LookupError("绑定会话不存在")
        if not display_name:
            raise ValueError("请填写接入备注")

        state = _load_state()
        _cleanup_sessions(state)
        _reconcile_state_tenant_bindings(state)

        target_index: int | None = None
        target_session: WecomStoredBindSession | None = None
        bind_path = f"/wechat-bind?token={normalized_token}"
        for index, session in enumerate(state.sessions):
            if _normalize_text(session.bind_path) == bind_path:
                target_index = index
                target_session = session.model_copy(deep=True)
                break

        if target_session is None or target_index is None:
            raise LookupError("绑定会话不存在")
        if target_session.status == "expired":
            raise RuntimeError("绑定二维码已过期，请重新生成")
        if target_session.status == "bound":
            raise RuntimeError("该绑定会话已完成")
        if target_session.status == "cancelled":
            raise RuntimeError("该绑定会话已失效，请重新生成")
        if target_session.status != "pending":
            raise RuntimeError("绑定会话状态不可用")
        if _normalize_text(target_session.qr_code_token):
            raise RuntimeError("当前渠道已改为真实微信扫码绑定，请在微信客户端内确认登录")

        now_text = _now_text()
        target_session.status = "bound"
        target_session.display_name = display_name
        target_session.external_account = external_account
        target_session.updated_at = now_text
        state.sessions[target_index] = target_session

        binding = WecomChannelBinding(
            tenant_id=target_session.tenant_id,
            tenant_name=target_session.tenant_name,
            display_name=display_name,
            external_account=external_account,
            bound_at=now_text,
            updated_at=now_text,
        )
        _replace_binding(state, binding)
        state.updated_at = now_text
        _persist_state(state)
        public_session = _to_public_session(target_session)
        if public_session is None:
            raise LookupError("绑定会话不存在")
        return binding, public_session


wecom_channel_binding_service = WecomChannelBindingService()
