from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.schemas import (
    UpdateVaultRegistryRequest,
    VaultRegistry,
)


class KnowledgeVaultStore(Protocol):
    def list_vaults(
        self,
        *,
        vault_type: str | None = None,
        tenant_id: str | None = None,
        enabled: bool | None = None,
    ) -> list[VaultRegistry]:
        ...

    def get_vault(self, vault_id: str) -> VaultRegistry | None:
        ...

    def save_vault(self, vault: VaultRegistry) -> VaultRegistry:
        ...

    def update_vault(self, vault_id: str, payload: UpdateVaultRegistryRequest) -> VaultRegistry | None:
        ...

    def delete_vault(self, vault_id: str) -> bool:
        ...

