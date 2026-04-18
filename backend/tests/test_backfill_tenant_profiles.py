from pathlib import Path

from app.services.persistence_service import StatePersistenceService
from app.services.store import InMemoryStore
from app.services.tenancy_service import default_scope
from scripts.backfill_tenant_profiles import run_tenant_profile_backfill, run_tenant_profile_rollback


def _seed_profiles(database_url: str, profiles: list[dict]) -> None:
    runtime_store = InMemoryStore()
    runtime_store.user_profiles = {}
    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert service.initialize() is True

    try:
        for profile in profiles:
            runtime_store.user_profiles[str(profile["id"])] = dict(profile)
            assert service.persist_user_state(profile=profile) is True
    finally:
        service.close()


def _load_profile(database_url: str, profile_id: str) -> dict | None:
    service = StatePersistenceService(runtime_store=InMemoryStore(), database_url=database_url)
    assert service.initialize() is True

    try:
        return service.get_user_profile(profile_id)
    finally:
        service.close()


def test_run_tenant_profile_backfill_applies_default_scope_and_writes_snapshot(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'tenant-profile-backfill-default.db'}"
    _seed_profiles(
        database_url,
        [
            {
                "id": "profile-default",
                "name": "默认租户画像",
                "source_channels": ["telegram"],
                "platform_accounts": [{"platform": "telegram", "account_id": "default-user"}],
                "preferred_language": "zh-CN",
                "notes": "待补租户字段",
                "last_login": "2026-04-16T08:00:00+00:00",
                "total_interactions": 3,
            }
        ],
    )

    report = run_tenant_profile_backfill(
        database_url=database_url,
        runtime_store=InMemoryStore(),
        apply=True,
        snapshot_dir=str(tmp_path),
    )

    restored_profile = _load_profile(database_url, "profile-default")

    assert report["ok"] is True
    assert report["mode"] == "apply"
    assert report["profile_totals"]["loaded"] == 1
    assert report["profile_totals"]["updated"] == 1
    assert report["snapshot_path"] is not None
    assert Path(report["snapshot_path"]).exists()
    assert restored_profile is not None
    assert restored_profile["tenant_id"] == default_scope()["tenant_id"]
    assert restored_profile["tenant_name"] == "默认租户"
    assert restored_profile["tenant_status"] == "active"
    assert restored_profile["last_active_at"] == "2026-04-16T08:00:00+00:00"
    assert restored_profile["total_interactions"] == 3


def test_run_tenant_profile_backfill_uses_overrides_and_reports_cross_tenant_account_conflicts(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'tenant-profile-backfill-overrides.db'}"
    _seed_profiles(
        database_url,
        [
            {
                "id": "profile-alpha",
                "name": "待分配画像",
                "source_channels": ["telegram"],
                "platform_accounts": [{"platform": "telegram", "account_id": "shared-user"}],
            },
            {
                "id": "profile-beta",
                "name": "已分配画像",
                "tenant_id": "tenant-beta",
                "tenant_name": "Beta Corp",
                "tenant_status": "active",
                "source_channels": ["telegram"],
                "platform_accounts": [{"platform": "telegram", "account_id": "shared-user"}],
            },
        ],
    )

    report = run_tenant_profile_backfill(
        database_url=database_url,
        runtime_store=InMemoryStore(),
        apply=False,
        override_payload={
            "platform_accounts": {
                "telegram:shared-user": {
                    "tenant_id": "tenant-alpha",
                    "tenant_name": "Alpha Corp",
                    "tenant_status": "active",
                }
            }
        },
    )

    changed_profile = next(item for item in report["changed_profiles"] if item["id"] == "profile-alpha")
    conflict = report["conflicts"]["cross_tenant_platform_accounts"][0]

    assert report["ok"] is True
    assert changed_profile["tenant_id"] == "tenant-alpha"
    assert changed_profile["resolution_source"] == "platform_account_override"
    assert conflict["account_key"] == "telegram:shared-user"
    assert conflict["tenant_ids"] == ["tenant-alpha", "tenant-beta"]
    assert set(conflict["profile_ids"]) == {"profile-alpha", "profile-beta"}


def test_run_tenant_profile_rollback_restores_snapshot_and_removes_new_profiles(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'tenant-profile-backfill-rollback.db'}"
    original_profile = {
        "id": "profile-rollback",
        "name": "回滚画像",
        "source_channels": ["wecom"],
        "platform_accounts": [{"platform": "wecom", "account_id": "rollback-user"}],
        "notes": "原始画像",
    }
    _seed_profiles(database_url, [original_profile])

    apply_report = run_tenant_profile_backfill(
        database_url=database_url,
        runtime_store=InMemoryStore(),
        apply=True,
        snapshot_dir=str(tmp_path),
    )

    runtime_store = InMemoryStore()
    service = StatePersistenceService(runtime_store=runtime_store, database_url=database_url)
    assert service.initialize() is True
    try:
        assert service.persist_user_state(
            profile={
                "id": "profile-added-later",
                "tenant_id": "tenant-extra",
                "tenant_name": "Extra Corp",
                "tenant_status": "active",
                "name": "新增画像",
            }
        ) is True
    finally:
        service.close()

    rollback_report = run_tenant_profile_rollback(
        snapshot_path=str(apply_report["snapshot_path"]),
        database_url=database_url,
        runtime_store=InMemoryStore(),
    )

    restored_profile = _load_profile(database_url, "profile-rollback")
    removed_profile = _load_profile(database_url, "profile-added-later")

    assert rollback_report["ok"] is True
    assert rollback_report["profile_totals"]["restored"] == 1
    assert rollback_report["profile_totals"]["removed"] == 1
    assert restored_profile == original_profile
    assert removed_profile is None
