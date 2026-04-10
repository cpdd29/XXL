from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


logger = logging.getLogger(__name__)

ENCRYPTED_TEXT_PREFIX = "enc:v1:"
ENCRYPTED_JSON_KEY = "__encrypted_v1__"
ENCRYPTION_KEY_NAMESPACE = "workbot:data-encryption:"


class EncryptionService:
    def __init__(self) -> None:
        self._fernet: Fernet | None = None
        self._material_cache: str | None = None

    def _derive_key(self, material: str) -> bytes:
        digest = hashlib.sha256(f"{ENCRYPTION_KEY_NAMESPACE}{material}".encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def _get_fernet(self) -> Fernet:
        settings = get_settings()
        material = str(settings.data_encryption_key or settings.auth_jwt_secret or settings.app_name)
        if self._fernet is not None and self._material_cache == material:
            return self._fernet
        self._material_cache = material
        self._fernet = Fernet(self._derive_key(material))
        return self._fernet

    def encrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value)
        if text.startswith(ENCRYPTED_TEXT_PREFIX):
            return text
        token = self._get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")
        return f"{ENCRYPTED_TEXT_PREFIX}{token}"

    def decrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value)
        if not text.startswith(ENCRYPTED_TEXT_PREFIX):
            return text
        token = text[len(ENCRYPTED_TEXT_PREFIX) :]
        try:
            return self._get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.warning("Encrypted text could not be decrypted, returning raw payload")
            return text

    def encrypt_json(self, payload: Any) -> Any:
        if payload is None:
            return None
        if self.is_encrypted_json(payload):
            return deepcopy(payload)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        token = self._get_fernet().encrypt(serialized.encode("utf-8")).decode("utf-8")
        return {ENCRYPTED_JSON_KEY: token}

    def decrypt_json(self, payload: Any) -> Any:
        if not self.is_encrypted_json(payload):
            return deepcopy(payload)
        token = str(payload.get(ENCRYPTED_JSON_KEY) or "")
        try:
            decrypted = self._get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.warning("Encrypted JSON payload could not be decrypted, returning raw payload")
            return deepcopy(payload)
        return json.loads(decrypted)

    @staticmethod
    def is_encrypted_json(payload: Any) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get(ENCRYPTED_JSON_KEY), str)


encryption_service = EncryptionService()
