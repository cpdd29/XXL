from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.knowledge.application import (
    knowledge_import_service,
    knowledge_injection_service,
    knowledge_retrieval_service,
    knowledge_sync_service,
    knowledge_vault_registry_service,
)
from app.modules.knowledge.application.vault_registry_service import KnowledgeVaultRegistryService
from app.modules.knowledge.schemas import (
    CreateVaultRegistryRequest,
    ImportKnowledgeVaultRequest,
    KnowledgeHit,
    KnowledgeHitMetadata,
    KnowledgeImportFileInput,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
    UpdateVaultRegistryRequest,
)
from app.platform.persistence.runtime_store import store


def _registry_service(tmp_path: Path) -> KnowledgeVaultRegistryService:
    return KnowledgeVaultRegistryService(managed_vault_root=tmp_path)


def _create_vault(
    service: KnowledgeVaultRegistryService,
    *,
    vault_name: str,
    tenant_id: str | None,
    tenant_name: str | None,
    vault_type: str = "tenant",
    source_type: str = "managed_fs",
    local_path: str | None = None,
):
    return service.create_vault(
        CreateVaultRegistryRequest(
            vault_name=vault_name,
            vault_type=vault_type,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            source_type=source_type,
            local_path=local_path,
        )
    ).vault


def _import_and_sync_markdown(
    *,
    vault,
    file_name: str,
    content: str,
) -> None:
    if vault.source_type == "managed_fs":
        knowledge_import_service.import_files(
            vault=vault,
            payload=ImportKnowledgeVaultRequest(
                files=[
                    KnowledgeImportFileInput(
                        file_name=file_name,
                        content=content,
                    )
                ]
            ),
        )
    else:
        Path(vault.local_path).joinpath(file_name).write_text(content, encoding="utf-8")
    response = knowledge_sync_service.sync_vault(vault_id=vault.vault_id)
    assert response.ok is True
    assert response.job.status == "success"


def test_external_vault_path_must_stay_inside_whitelist(tmp_path: Path) -> None:
    managed_root = tmp_path.joinpath("managed-root")
    managed_root.mkdir(parents=True, exist_ok=True)
    outside_root = tmp_path.parent.joinpath(f"outside-vault-{uuid4().hex[:6]}")
    outside_root.mkdir(parents=True, exist_ok=True)
    service = KnowledgeVaultRegistryService(managed_vault_root=managed_root)

    with pytest.raises(ValueError, match="outside allowed roots"):
        _create_vault(
            service,
            vault_name="非法外接知识仓",
            tenant_id="tenant-illegal",
            tenant_name="Illegal Corp",
            source_type="external_obsidian_fs",
            local_path=str(outside_root),
        )

    shutil.rmtree(outside_root, ignore_errors=True)


def test_disabled_tenant_vault_is_cut_off_from_retrieval(tmp_path: Path) -> None:
    service = _registry_service(tmp_path)
    vault = _create_vault(
        service,
        vault_name="Alpha Tenant Vault",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
    )
    _import_and_sync_markdown(
        vault=vault,
        file_name="faq.md",
        content="# 广州天气\n广州天气咨询统一回复为先确认日期。",
    )

    before = knowledge_retrieval_service.retrieve(
        KnowledgeRetrievalRequest(
            tenant_id="tenant-alpha",
            query="广州天气",
            scene="reception",
        )
    )
    assert before.total >= 1
    assert before.metadata["effective_tenant_vault_ids"] == [vault.vault_id]

    update_response = knowledge_vault_registry_service.update_vault(
        vault.vault_id,
        UpdateVaultRegistryRequest(enabled=False),
    )
    assert update_response.vault.enabled is False

    after = knowledge_retrieval_service.retrieve(
        KnowledgeRetrievalRequest(
            tenant_id="tenant-alpha",
            query="广州天气",
            scene="reception",
        )
    )
    assert after.total == 0
    assert after.tenant_hits == 0
    assert after.metadata["effective_tenant_vault_ids"] == []


def test_retrieval_keeps_tenant_and_shared_boundary_without_cross_tenant_leak(tmp_path: Path) -> None:
    service = _registry_service(tmp_path)
    alpha_vault = _create_vault(
        service,
        vault_name="Alpha Tenant Vault",
        tenant_id="tenant-alpha",
        tenant_name="Alpha Corp",
    )
    beta_vault = _create_vault(
        service,
        vault_name="Beta Tenant Vault",
        tenant_id="tenant-beta",
        tenant_name="Beta Corp",
    )
    shared_dir = tmp_path.joinpath("shared-vault")
    shared_dir.mkdir(parents=True, exist_ok=True)
    shared_vault = _create_vault(
        service,
        vault_name="Shared Vault",
        tenant_id=None,
        tenant_name=None,
        vault_type="shared",
        source_type="external_obsidian_fs",
        local_path=str(shared_dir),
    )

    _import_and_sync_markdown(
        vault=alpha_vault,
        file_name="alpha-sla.md",
        content="# Alpha 售后SLA\nAlpha 客户售后 SLA 约定为 2 小时内首次响应。",
    )
    _import_and_sync_markdown(
        vault=beta_vault,
        file_name="beta-internal.md",
        content="# Beta 内部排期\nBeta 专属实施排期，不对外共享。",
    )
    _import_and_sync_markdown(
        vault=shared_vault,
        file_name="shared-sla.md",
        content="# 通用售后SLA\n共享售后 SLA 基线包含节假日响应说明。",
    )

    response = knowledge_retrieval_service.retrieve(
        KnowledgeRetrievalRequest(
            tenant_id="tenant-alpha",
            query="SLA",
            scene="reception",
            top_k_tenant=3,
            top_k_shared=3,
        )
    )

    titles = [item.title for item in response.items]
    tenant_ids = {item.tenant_id for item in response.items if item.scope == "tenant"}

    assert response.tenant_hits >= 1
    assert response.shared_hits >= 1
    assert "Alpha 售后SLA" in titles
    assert "通用售后SLA" in titles
    assert "Beta 内部排期" not in titles
    assert tenant_ids == {"tenant-alpha"}


def test_knowledge_injection_governance_truncates_and_redacts_sensitive_hits() -> None:
    retrieval = KnowledgeRetrievalResponse(
        items=[
            KnowledgeHit(
                title="内部升级路径",
                summary="这是需要被脱敏的内部升级路径说明",
                scope="tenant",
                tenant_id="tenant-alpha",
                metadata=KnowledgeHitMetadata(
                    document_id="doc-1",
                    chunk_id="chunk-1",
                    vault_id="vault-1",
                    tags=["内部"],
                ),
            ),
            *[
                KnowledgeHit(
                    title=f"知识-{index}",
                    summary="A" * 300,
                    scope="tenant" if index % 2 else "shared",
                    tenant_id="tenant-alpha" if index % 2 else None,
                    metadata=KnowledgeHitMetadata(
                        document_id=f"doc-{index + 1}",
                        chunk_id=f"chunk-{index + 1}",
                        vault_id=f"vault-{index + 1}",
                        tags=["faq"],
                    ),
                )
                for index in range(1, 7)
            ],
        ],
        total=7,
        tenant_hits=4,
        shared_hits=3,
        query="售后SLA",
        scene="reception",
    )

    metadata_hits = knowledge_injection_service.build_metadata_hits(retrieval)
    governance = knowledge_injection_service.build_governance_summary(retrieval)

    assert len(metadata_hits) == 5
    assert metadata_hits[0]["summary"] == "该知识片段因敏感标签已做摘要脱敏"
    assert all(len(str(item["summary"])) <= 220 for item in metadata_hits[1:])
    assert governance["raw_total"] == 7
    assert governance["delivered_total"] == 5
    assert governance["dropped_total"] == 2
    assert governance["redacted_total"] == 1


def test_sync_updates_vault_status_and_writes_audit_and_operational_logs(tmp_path: Path) -> None:
    service = _registry_service(tmp_path)
    vault = _create_vault(
        service,
        vault_name="Audit Tenant Vault",
        tenant_id="tenant-audit",
        tenant_name="Audit Corp",
    )

    _import_and_sync_markdown(
        vault=vault,
        file_name="audit.md",
        content="# 审计知识\n同步成功后需要写入治理日志。",
    )

    saved_vault = knowledge_vault_registry_service.get_vault(vault.vault_id)

    assert saved_vault is not None
    assert saved_vault.last_sync_status == "success"
    assert saved_vault.last_sync_at
    assert any(
        str(log.get("action") or "") == "knowledge.vault.sync.completed"
        and str((log.get("metadata") or {}).get("vault_id") or "") == vault.vault_id
        for log in store.audit_logs
    )
    assert any(
        str((log.get("metadata") or {}).get("event") or "") == "knowledge_sync_completed"
        and str((log.get("metadata") or {}).get("vault_id") or "") == vault.vault_id
        for log in store.operational_logs
    )


def test_failed_sync_marks_vault_failed_and_emits_failure_audit(tmp_path: Path) -> None:
    service = _registry_service(tmp_path)
    external_dir = tmp_path.joinpath("broken-vault")
    external_dir.mkdir(parents=True, exist_ok=True)
    vault = _create_vault(
        service,
        vault_name="Broken External Vault",
        tenant_id=None,
        tenant_name=None,
        vault_type="shared",
        source_type="external_obsidian_fs",
        local_path=str(external_dir),
    )

    shutil.rmtree(external_dir, ignore_errors=True)

    response = knowledge_sync_service.sync_vault(vault_id=vault.vault_id)
    saved_vault = knowledge_vault_registry_service.get_vault(vault.vault_id)

    assert response.ok is False
    assert response.job.status == "failed"
    assert saved_vault is not None
    assert saved_vault.last_sync_status == "failed"
    assert any(
        str(log.get("action") or "") == "knowledge.vault.sync.failed"
        and str((log.get("metadata") or {}).get("vault_id") or "") == vault.vault_id
        for log in store.audit_logs
    )
    assert any(
        str((log.get("metadata") or {}).get("event") or "") == "knowledge_sync_failed"
        and str((log.get("metadata") or {}).get("vault_id") or "") == vault.vault_id
        for log in store.operational_logs
    )
