from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.knowledge.adapters import ObsidianVaultScanResult, obsidian_filesystem_adapter
from app.modules.knowledge.application import (
    knowledge_document_query_service,
    knowledge_vault_entry_service,
    knowledge_import_service,
    knowledge_injection_service,
    knowledge_retrieval_log_service,
    knowledge_retrieval_service,
    knowledge_sync_service,
    knowledge_vault_registry_service,
)
from app.modules.knowledge.schemas import (
    CreateKnowledgeSyncJobRequest,
    CreateKnowledgeVaultFolderRequest,
    CreateVaultRegistryRequest,
    DeleteKnowledgeVaultEntryRequest,
    ImportKnowledgeVaultRequest,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    KnowledgeRetrievalLogListResponse,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
    KnowledgeSyncJob,
    KnowledgeSyncJobActionResponse,
    KnowledgeSyncJobListResponse,
    KnowledgeVaultEntryActionResponse,
    KnowledgeVaultImportResponse,
    KnowledgeVaultValidationResponse,
    RenameKnowledgeVaultEntryRequest,
    UpdateVaultRegistryRequest,
    VaultRegistry,
    VaultRegistryActionResponse,
    VaultRegistryDeleteResponse,
    VaultRegistryListResponse,
)
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log
from app.platform.auth.authz import require_authenticated_user, require_permission


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


def _translate_error(exc: Exception) -> HTTPException:
    detail = exc.args[0] if getattr(exc, "args", None) else str(exc)
    if isinstance(exc, KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(detail))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(detail))


@router.get(
    "/vaults",
    response_model=VaultRegistryListResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def list_knowledge_vaults_route(
    vault_type: str | None = Query(default=None, alias="vaultType"),
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    enabled: bool | None = Query(default=None),
) -> VaultRegistryListResponse:
    return knowledge_vault_registry_service.list_vaults(
        vault_type=vault_type,
        tenant_id=tenant_id,
        enabled=enabled,
    )


@router.get(
    "/vaults/{vault_id}",
    response_model=VaultRegistry,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_knowledge_vault_route(vault_id: str) -> VaultRegistry:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")
    return vault


@router.post(
    "/vaults",
    response_model=VaultRegistryActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def create_knowledge_vault_route(
    payload: CreateVaultRegistryRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> VaultRegistryActionResponse:
    try:
        response = knowledge_vault_registry_service.create_vault(payload)
    except Exception as exc:
        raise _translate_error(exc) from exc
    append_control_plane_audit_log(
        action="knowledge.vault.created",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{response.vault.vault_id}",
        details=f"新增知识仓 {response.vault.vault_name}",
        metadata=response.vault.model_dump(mode="json", by_alias=False),
    )
    return response


@router.put(
    "/vaults/{vault_id}",
    response_model=VaultRegistryActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def update_knowledge_vault_route(
    vault_id: str,
    payload: UpdateVaultRegistryRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> VaultRegistryActionResponse:
    try:
        response = knowledge_vault_registry_service.update_vault(vault_id, payload)
    except Exception as exc:
        raise _translate_error(exc) from exc
    append_control_plane_audit_log(
        action="knowledge.vault.updated",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{vault_id}",
        details=f"更新知识仓 {response.vault.vault_name}",
        metadata=response.vault.model_dump(mode="json", by_alias=False),
    )
    return response


@router.delete(
    "/vaults/{vault_id}",
    response_model=VaultRegistryDeleteResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def delete_knowledge_vault_route(
    vault_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> VaultRegistryDeleteResponse:
    try:
        response = knowledge_vault_registry_service.delete_vault(vault_id)
    except Exception as exc:
        raise _translate_error(exc) from exc
    append_control_plane_audit_log(
        action="knowledge.vault.deleted",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{vault_id}",
        details=f"删除知识仓 {vault_id}",
    )
    return response


@router.post(
    "/vaults/{vault_id}/import",
    response_model=KnowledgeVaultImportResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def import_knowledge_vault_files_route(
    vault_id: str,
    payload: ImportKnowledgeVaultRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> KnowledgeVaultImportResponse:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")

    try:
        response = knowledge_import_service.import_files(vault=vault, payload=payload)
    except Exception as exc:
        raise _translate_error(exc) from exc

    append_control_plane_audit_log(
        action="knowledge.vault.imported",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{vault_id}",
        details=f"导入知识文件到 {vault.vault_name}",
        metadata={
            "vault_id": vault_id,
            "vault_name": vault.vault_name,
            "total_files": response.total_files,
            "imported_files": response.imported_files,
        },
    )
    return response


@router.post(
    "/vaults/{vault_id}/entries/folders",
    response_model=KnowledgeVaultEntryActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def create_knowledge_vault_folder_route(
    vault_id: str,
    payload: CreateKnowledgeVaultFolderRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> KnowledgeVaultEntryActionResponse:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")

    try:
        response = knowledge_vault_entry_service.create_folder(vault=vault, payload=payload)
    except Exception as exc:
        raise _translate_error(exc) from exc

    append_control_plane_audit_log(
        action="knowledge.vault.folder.created",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{vault_id}",
        details=f"创建知识目录 {response.next_path}",
        metadata={
            "vault_id": vault_id,
            "parent_path": payload.parent_path,
            "next_path": response.next_path,
        },
    )
    return response


@router.post(
    "/vaults/{vault_id}/entries/rename",
    response_model=KnowledgeVaultEntryActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def rename_knowledge_vault_entry_route(
    vault_id: str,
    payload: RenameKnowledgeVaultEntryRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> KnowledgeVaultEntryActionResponse:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")

    try:
        response = knowledge_vault_entry_service.rename_entry(vault=vault, payload=payload)
        knowledge_sync_service.sync_vault(
            vault_id=vault_id,
            trigger_type="manual",
            metadata={
                "reason": "entry_renamed",
                "path": payload.path,
                "next_path": response.next_path,
                "operator_user": _operator_identity(current_user),
            },
        )
    except Exception as exc:
        raise _translate_error(exc) from exc

    append_control_plane_audit_log(
        action="knowledge.vault.entry.renamed",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{vault_id}",
        details=f"重命名知识节点 {payload.path} -> {response.next_path}",
        metadata={
            "vault_id": vault_id,
            "path": payload.path,
            "next_path": response.next_path,
        },
    )
    return response


@router.delete(
    "/vaults/{vault_id}/entries",
    response_model=KnowledgeVaultEntryActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def delete_knowledge_vault_entry_route(
    vault_id: str,
    payload: DeleteKnowledgeVaultEntryRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> KnowledgeVaultEntryActionResponse:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")

    try:
        response = knowledge_vault_entry_service.delete_entry(vault=vault, payload=payload)
        knowledge_sync_service.sync_vault(
            vault_id=vault_id,
            trigger_type="manual",
            metadata={
                "reason": "entry_deleted",
                "path": payload.path,
                "operator_user": _operator_identity(current_user),
            },
        )
    except Exception as exc:
        raise _translate_error(exc) from exc

    append_control_plane_audit_log(
        action="knowledge.vault.entry.deleted",
        user=_operator_identity(current_user),
        resource=f"knowledge.vault.{vault_id}",
        details=f"删除知识节点 {payload.path}",
        metadata={
            "vault_id": vault_id,
            "path": payload.path,
            "entry_kind": response.entry_kind,
        },
    )
    return response


@router.post(
    "/vaults/{vault_id}/validate-source",
    response_model=KnowledgeVaultValidationResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def validate_knowledge_vault_source_route(vault_id: str) -> KnowledgeVaultValidationResponse:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")

    try:
        return knowledge_vault_registry_service.validate_vault_source(vault)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/vaults/{vault_id}/scan-preview",
    response_model=ObsidianVaultScanResult,
    dependencies=[Depends(require_permission("settings:read"))],
)
def scan_knowledge_vault_preview_route(
    vault_id: str,
    limit: int = Query(default=20, ge=1, le=200),
) -> ObsidianVaultScanResult:
    vault = knowledge_vault_registry_service.get_vault(vault_id)
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge vault not found")
    try:
        return obsidian_filesystem_adapter.scan_vault(vault.local_path, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/documents",
    response_model=KnowledgeDocumentListResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def list_knowledge_documents_route(
    vault_id: str | None = Query(default=None, alias="vaultId"),
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    scope: str | None = Query(default=None),
    status_filter: str | None = Query(default="active", alias="status"),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> KnowledgeDocumentListResponse:
    return knowledge_document_query_service.list_documents(
        vault_id=vault_id,
        tenant_id=tenant_id,
        scope=scope,
        status=status_filter,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentDetailResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_knowledge_document_detail_route(document_id: str) -> KnowledgeDocumentDetailResponse:
    document = knowledge_document_query_service.get_document_detail(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found")
    return document


@router.get(
    "/sync-jobs",
    response_model=KnowledgeSyncJobListResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def list_knowledge_sync_jobs_route(
    vault_id: str | None = Query(default=None, alias="vaultId"),
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> KnowledgeSyncJobListResponse:
    return knowledge_sync_service.list_sync_jobs(
        vault_id=vault_id,
        tenant_id=tenant_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/sync-jobs/{sync_job_id}",
    response_model=KnowledgeSyncJob,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_knowledge_sync_job_route(sync_job_id: str) -> KnowledgeSyncJob:
    job = knowledge_sync_service.get_sync_job(sync_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge sync job not found")
    return job


@router.post(
    "/vaults/{vault_id}/sync",
    response_model=KnowledgeSyncJobActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def trigger_knowledge_vault_sync_route(
    vault_id: str,
    payload: CreateKnowledgeSyncJobRequest | None = None,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> KnowledgeSyncJobActionResponse:
    request = payload or CreateKnowledgeSyncJobRequest(vault_id=vault_id)
    request = request.model_copy(update={"vault_id": vault_id})
    try:
        response = knowledge_sync_service.sync_vault(
            vault_id=request.vault_id,
            trigger_type=request.trigger_type,
            force_full_scan=request.force_full_scan,
            metadata={
                **dict(request.metadata or {}),
                "operator_user": _operator_identity(current_user),
            },
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return response


@router.post(
    "/retrieve",
    response_model=KnowledgeRetrievalResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def retrieve_knowledge_route(
    payload: KnowledgeRetrievalRequest,
    request_source: str | None = Query(default=None, alias="requestSource"),
    trace_id: str | None = Query(default=None, alias="traceId"),
) -> KnowledgeRetrievalResponse:
    response = knowledge_retrieval_service.retrieve(payload)
    log = knowledge_retrieval_log_service.build_log(
        request=payload,
        response=response,
        request_source=request_source,
        trace_id=trace_id,
        metadata={"mode": "debug_api"},
    )
    knowledge_retrieval_log_service.append_log(log)
    return response


@router.post(
    "/retrieve/metadata-preview",
    dependencies=[Depends(require_permission("settings:read"))],
)
def preview_knowledge_injection_route(payload: KnowledgeRetrievalRequest) -> dict[str, Any]:
    response = knowledge_retrieval_service.retrieve(payload)
    return {
        "knowledge_hits": knowledge_injection_service.build_metadata_hits(response),
        "knowledge_retrieval": {
            "query": response.query,
            "scene": response.scene,
            "total": response.total,
            "tenant_hits": response.tenant_hits,
            "shared_hits": response.shared_hits,
        },
    }


@router.get(
    "/retrieval-logs",
    response_model=KnowledgeRetrievalLogListResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def list_knowledge_retrieval_logs_route(
    tenant_id: str | None = Query(default=None, alias="tenantId"),
    scene: str | None = Query(default=None),
    request_source: str | None = Query(default=None, alias="requestSource"),
    trace_id: str | None = Query(default=None, alias="traceId"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> KnowledgeRetrievalLogListResponse:
    return knowledge_retrieval_log_service.list_logs(
        tenant_id=tenant_id,
        scene=scene,
        request_source=request_source,
        trace_id=trace_id,
        limit=limit,
        offset=offset,
    )
