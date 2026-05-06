from __future__ import annotations

from typing import Any

from app.modules.knowledge.schemas import (
    UpdateVaultRegistryRequest,
    VaultRegistry,
)
from app.modules.knowledge.storage.system_setting_store_utils import (
    clone_metadata,
    normalize_text,
    read_json_list_setting,
    write_json_list_setting,
)


KNOWLEDGE_VAULT_REGISTRY_SETTING_KEY = "knowledge_vault_registry"


def _coerce_vault(payload: object) -> VaultRegistry | None:
    if not isinstance(payload, dict):
        return None

    vault_id = normalize_text(payload.get("vault_id") or payload.get("vaultId"))
    vault_name = normalize_text(payload.get("vault_name") or payload.get("vaultName"))
    local_path = normalize_text(payload.get("local_path") or payload.get("localPath"))
    if not vault_id or not vault_name or not local_path:
        return None

    try:
        return VaultRegistry(
            vault_id=vault_id,
            vault_name=vault_name,
            vault_type=normalize_text(payload.get("vault_type") or payload.get("vaultType") or "tenant") or "tenant",
            tenant_id=normalize_text(payload.get("tenant_id") or payload.get("tenantId")) or None,
            tenant_name=normalize_text(payload.get("tenant_name") or payload.get("tenantName")) or None,
            source_type=(
                normalize_text(payload.get("source_type") or payload.get("sourceType") or "obsidian_fs")
                or "obsidian_fs"
            ),
            local_path=local_path,
            enabled=bool(payload.get("enabled", True)),
            sync_mode=normalize_text(payload.get("sync_mode") or payload.get("syncMode") or "manual") or "manual",
            last_sync_at=normalize_text(payload.get("last_sync_at") or payload.get("lastSyncAt")) or None,
            last_sync_status=(
                normalize_text(payload.get("last_sync_status") or payload.get("lastSyncStatus") or "never_synced")
                or "never_synced"
            ),
            remark=normalize_text(payload.get("remark")) or None,
            metadata=clone_metadata(payload.get("metadata")),
        )
    except Exception:
        return None


class SystemSettingKnowledgeVaultStore:
    """基于 system_settings 的知识仓注册存储。"""

    def list_vaults(
        self,
        *,
        vault_type: str | None = None,
        tenant_id: str | None = None,
        enabled: bool | None = None,
    ) -> list[VaultRegistry]:
        normalized_vault_type = normalize_text(vault_type).lower() or None
        normalized_tenant_id = normalize_text(tenant_id) or None

        items: list[VaultRegistry] = []
        for payload in read_json_list_setting(KNOWLEDGE_VAULT_REGISTRY_SETTING_KEY):
            vault = _coerce_vault(payload)
            if vault is None:
                continue
            if normalized_vault_type and vault.vault_type != normalized_vault_type:
                continue
            if normalized_tenant_id and vault.tenant_id != normalized_tenant_id:
                continue
            if enabled is not None and vault.enabled is not enabled:
                continue
            items.append(vault)
        items.sort(key=lambda item: (item.vault_type != "tenant", (item.tenant_id or "").lower(), item.vault_name.lower()))
        return items

    def get_vault(self, vault_id: str) -> VaultRegistry | None:
        normalized_vault_id = normalize_text(vault_id)
        if not normalized_vault_id:
            return None
        for vault in self.list_vaults():
            if vault.vault_id == normalized_vault_id:
                return vault
        return None

    def save_vault(self, vault: VaultRegistry) -> VaultRegistry:
        items = [item for item in read_json_list_setting(KNOWLEDGE_VAULT_REGISTRY_SETTING_KEY) if normalize_text(item.get("vault_id") or item.get("vaultId")) != vault.vault_id]
        items.append(vault.model_dump(mode="json", by_alias=False))
        write_json_list_setting(KNOWLEDGE_VAULT_REGISTRY_SETTING_KEY, items)
        return vault

    def update_vault(self, vault_id: str, payload: UpdateVaultRegistryRequest) -> VaultRegistry | None:
        current = self.get_vault(vault_id)
        if current is None:
            return None
        update_fields = payload.model_dump(mode="json", by_alias=False, exclude_none=True)
        merged = current.model_copy(update=update_fields)
        return self.save_vault(merged)

    def delete_vault(self, vault_id: str) -> bool:
        normalized_vault_id = normalize_text(vault_id)
        if not normalized_vault_id:
            return False
        original = read_json_list_setting(KNOWLEDGE_VAULT_REGISTRY_SETTING_KEY)
        filtered = [
            item
            for item in original
            if normalize_text(item.get("vault_id") or item.get("vaultId")) != normalized_vault_id
        ]
        if len(filtered) == len(original):
            return False
        write_json_list_setting(KNOWLEDGE_VAULT_REGISTRY_SETTING_KEY, filtered)
        return True


system_setting_knowledge_vault_store = SystemSettingKnowledgeVaultStore()
