from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


KnowledgeVaultType = Literal["shared", "tenant"]
KnowledgeVaultSourceType = Literal["obsidian_fs", "managed_fs", "external_obsidian_fs"]
KnowledgeVaultSyncMode = Literal["manual", "scheduled"]
KnowledgeVaultSyncStatus = Literal["never_synced", "idle", "running", "success", "failed", "partial", "disabled"]


class VaultRegistry(APIModel):
    vault_id: str
    vault_name: str
    vault_type: KnowledgeVaultType = "tenant"
    tenant_id: str | None = None
    tenant_name: str | None = None
    source_type: KnowledgeVaultSourceType = "obsidian_fs"
    local_path: str
    enabled: bool = True
    sync_mode: KnowledgeVaultSyncMode = "manual"
    last_sync_at: str | None = None
    last_sync_status: KnowledgeVaultSyncStatus = "never_synced"
    remark: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateVaultRegistryRequest(APIModel):
    vault_name: str
    vault_type: KnowledgeVaultType = "tenant"
    tenant_id: str | None = None
    tenant_name: str | None = None
    source_type: KnowledgeVaultSourceType = "managed_fs"
    local_path: str | None = None
    enabled: bool = True
    sync_mode: KnowledgeVaultSyncMode = "manual"
    remark: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateVaultRegistryRequest(APIModel):
    vault_name: str | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    source_type: KnowledgeVaultSourceType | None = None
    local_path: str | None = None
    enabled: bool | None = None
    sync_mode: KnowledgeVaultSyncMode | None = None
    remark: str | None = None
    metadata: dict[str, Any] | None = None


class VaultRegistryListResponse(APIModel):
    items: list[VaultRegistry] = Field(default_factory=list)
    total: int = 0
    updated_at: str | None = None


class VaultRegistryActionResponse(APIModel):
    ok: bool
    message: str
    vault: VaultRegistry


class VaultRegistryDeleteResponse(APIModel):
    ok: bool
    message: str
    vault_id: str


class KnowledgeImportFileInput(APIModel):
    file_name: str
    content: str


class ImportKnowledgeVaultRequest(APIModel):
    files: list[KnowledgeImportFileInput] = Field(default_factory=list)


class KnowledgeVaultImportResponse(APIModel):
    ok: bool
    message: str
    vault_id: str
    vault_path: str
    imported_files: list[str] = Field(default_factory=list)
    total_files: int = 0


class RenameKnowledgeVaultEntryRequest(APIModel):
    path: str
    new_name: str


class DeleteKnowledgeVaultEntryRequest(APIModel):
    path: str


class CreateKnowledgeVaultFolderRequest(APIModel):
    parent_path: str | None = None
    name: str


class KnowledgeVaultEntryActionResponse(APIModel):
    ok: bool
    message: str
    vault_id: str
    entry_kind: Literal["file", "folder"]
    path: str
    next_path: str | None = None


class KnowledgeVaultValidationResponse(APIModel):
    ok: bool
    message: str
    vault_id: str
    source_type: KnowledgeVaultSourceType
    local_path: str
    markdown_file_count: int = 0
    sample_files: list[str] = Field(default_factory=list)
    checked_at: str
