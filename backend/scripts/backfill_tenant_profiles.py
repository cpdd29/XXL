from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import delete, select


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.models import ConversationMessageRecord, UserProfileRecord  # noqa: E402
from app.modules.organization.application.tenancy_service import default_scope  # noqa: E402
from app.platform.persistence.persistence_service import StatePersistenceService  # noqa: E402
from app.platform.persistence.runtime_store import InMemoryStore, store  # noqa: E402


DEFAULT_TENANT_STATUS = "active"
DEFAULT_TENANT_NAME = "默认租户"
DEFAULT_SNAPSHOT_DIR = BACKEND_ROOT / "data" / "profile_migration_snapshots"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_language(value: object) -> str:
    normalized = _normalize_text(value).lower().replace("_", "-")
    prefix = normalized.split("-", 1)[0]
    if prefix in {"zh", "en"}:
        return prefix
    return "zh"


def _normalize_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        normalized = _normalize_text(raw)
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        items.append(normalized)
    return items


def _normalize_source_channels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    channels: list[str] = []
    seen: set[str] = set()
    for raw in value:
        normalized = _normalize_text(raw).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        channels.append(normalized)
    return channels


def _normalize_platform_accounts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    accounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        platform = _normalize_text(raw.get("platform")).lower()
        account_id = _normalize_text(raw.get("account_id") or raw.get("accountId"))
        if not platform or not account_id:
            continue
        key = (platform, account_id)
        if key in seen:
            continue
        seen.add(key)
        accounts.append({"platform": platform, "account_id": account_id})
    return accounts


def _normalize_interaction_count(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _normalize_timestamp(*values: object) -> str:
    for value in values:
        normalized = _normalize_text(value)
        if normalized:
            return normalized
    return ""


def _normalize_tenant_status(value: object) -> str:
    normalized = _normalize_text(value).lower()
    return normalized or DEFAULT_TENANT_STATUS


def _default_tenant_config(
    *,
    default_tenant_id: str | None = None,
    default_tenant_name: str | None = None,
) -> dict[str, str]:
    resolved_scope = default_scope()
    tenant_id = _normalize_text(default_tenant_id) or _normalize_text(resolved_scope.get("tenant_id")) or "default"
    tenant_name = _normalize_text(default_tenant_name)
    if tenant_name:
        resolved_tenant_name = tenant_name
    elif tenant_id == _normalize_text(resolved_scope.get("tenant_id")):
        resolved_tenant_name = DEFAULT_TENANT_NAME
    else:
        resolved_tenant_name = f"{tenant_id} 租户"
    return {
        "tenant_id": tenant_id,
        "tenant_name": resolved_tenant_name,
        "tenant_status": DEFAULT_TENANT_STATUS,
    }


def _normalize_tenant_assignment(
    candidate: dict[str, Any] | None,
    *,
    fallback: dict[str, str],
) -> dict[str, str]:
    normalized = candidate if isinstance(candidate, dict) else {}
    tenant_id = _normalize_text(
        normalized.get("tenant_id") or normalized.get("tenantId") or fallback["tenant_id"]
    )
    tenant_name = _normalize_text(
        normalized.get("tenant_name") or normalized.get("tenantName")
    )
    if not tenant_name:
        tenant_name = fallback["tenant_name"] if tenant_id == fallback["tenant_id"] else f"{tenant_id} 租户"
    tenant_status = _normalize_tenant_status(
        normalized.get("tenant_status") or normalized.get("tenantStatus") or fallback["tenant_status"]
    )
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "tenant_status": tenant_status,
    }


def _load_overrides(path: str | None = None, *, payload: dict[str, Any] | None = None) -> dict[str, dict[str, dict[str, str]]]:
    raw_payload = payload
    if raw_payload is None and path:
        raw_payload = json.loads(Path(path).read_text(encoding="utf-8"))

    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    normalized: dict[str, dict[str, dict[str, str]]] = {
        "profiles": {},
        "platform_accounts": {},
        "channels": {},
    }

    for profile_id, override in (raw_payload.get("profiles") or {}).items():
        normalized_id = _normalize_text(profile_id)
        if not normalized_id:
            continue
        normalized["profiles"][normalized_id] = _normalize_tenant_assignment(
            override,
            fallback=_default_tenant_config(),
        )

    for account_key, override in (raw_payload.get("platform_accounts") or {}).items():
        normalized_key = _normalize_text(account_key).lower()
        if not normalized_key:
            continue
        normalized["platform_accounts"][normalized_key] = _normalize_tenant_assignment(
            override,
            fallback=_default_tenant_config(),
        )

    for channel, override in (raw_payload.get("channels") or {}).items():
        normalized_channel = _normalize_text(channel).lower()
        if not normalized_channel:
            continue
        normalized["channels"][normalized_channel] = _normalize_tenant_assignment(
            override,
            fallback=_default_tenant_config(),
        )

    return normalized


def _profile_id(profile: dict[str, Any]) -> str:
    return _normalize_text(profile.get("id") or profile.get("user_id") or profile.get("profile_id"))


def _load_profiles(service: StatePersistenceService, runtime_store: InMemoryStore) -> list[dict[str, Any]]:
    database_profiles = service.list_user_profiles()
    if database_profiles is not None:
        return [deepcopy(item) for item in database_profiles if isinstance(item, dict)]
    return [
        deepcopy(profile)
        for profile in runtime_store.user_profiles.values()
        if isinstance(profile, dict)
    ]


def _message_counts(service: StatePersistenceService) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not service.enabled or service._session_factory is None:
        return counts

    with service._session_factory() as session:
        for row in session.scalars(select(ConversationMessageRecord)).all():
            user_id = _normalize_text(row.user_id)
            if user_id:
                counts[user_id] += 1
    return counts


def _task_counts(service: StatePersistenceService) -> Counter[str]:
    counts: Counter[str] = Counter()
    tasks = service.list_tasks()
    for task in tasks or []:
        user_key = _normalize_text(task.get("user_key") or task.get("userKey"))
        if user_key:
            counts[user_key] += 1
    return counts


def _audit_match_count(profile: dict[str, Any], audit_logs: list[dict[str, Any]]) -> int:
    candidate_tokens = {
        _profile_id(profile).lower(),
        _normalize_text(profile.get("name")).lower(),
        _normalize_text(profile.get("tenant_id")).lower(),
    }
    candidate_tokens.update(
        _normalize_text(account.get("account_id")).lower()
        for account in _normalize_platform_accounts(profile.get("platform_accounts"))
    )
    candidate_tokens = {token for token in candidate_tokens if token}

    matched = 0
    for log in audit_logs:
        haystack = " ".join(
            [
                _normalize_text(log.get("user")).lower(),
                _normalize_text(log.get("resource")).lower(),
                _normalize_text(log.get("details")).lower(),
                json.dumps(log.get("metadata") or {}, ensure_ascii=False).lower(),
            ]
        )
        if any(token in haystack for token in candidate_tokens):
            matched += 1
    return matched


def _account_key(platform: str, account_id: str) -> str:
    return f"{platform.lower()}:{account_id}"


def _resolve_tenant_assignment(
    profile: dict[str, Any],
    *,
    overrides: dict[str, dict[str, dict[str, str]]],
    default_config: dict[str, str],
) -> tuple[dict[str, str], str, list[str]]:
    profile_identifier = _profile_id(profile)
    if profile_identifier and profile_identifier in overrides["profiles"]:
        return overrides["profiles"][profile_identifier], "profile_override", []

    explicit_tenant_id = _normalize_text(profile.get("tenant_id") or profile.get("tenantId"))
    explicit_tenant_name = _normalize_text(profile.get("tenant_name") or profile.get("tenantName"))
    explicit_tenant_status = _normalize_tenant_status(profile.get("tenant_status") or profile.get("tenantStatus"))
    if explicit_tenant_id:
        return (
            {
                "tenant_id": explicit_tenant_id,
                "tenant_name": explicit_tenant_name or (
                    default_config["tenant_name"]
                    if explicit_tenant_id == default_config["tenant_id"]
                    else f"{explicit_tenant_id} 租户"
                ),
                "tenant_status": explicit_tenant_status,
            },
            "existing_profile_fields",
            [],
        )

    conflicts: list[str] = []
    platform_assignments = [
        overrides["platform_accounts"][_account_key(account["platform"], account["account_id"])]
        for account in _normalize_platform_accounts(profile.get("platform_accounts") or profile.get("platformAccounts"))
        if _account_key(account["platform"], account["account_id"]) in overrides["platform_accounts"]
    ]
    if platform_assignments:
        distinct_account_tenants = {
            (
                item["tenant_id"],
                item["tenant_name"],
                item["tenant_status"],
            )
            for item in platform_assignments
        }
        if len(distinct_account_tenants) > 1:
            conflicts.append("platform_account_override_conflict")
        selected = platform_assignments[0]
        return selected, "platform_account_override", conflicts

    channel_assignments = [
        overrides["channels"][channel]
        for channel in _normalize_source_channels(profile.get("source_channels") or profile.get("sourceChannels"))
        if channel in overrides["channels"]
    ]
    if channel_assignments:
        distinct_channel_tenants = {
            (
                item["tenant_id"],
                item["tenant_name"],
                item["tenant_status"],
            )
            for item in channel_assignments
        }
        if len(distinct_channel_tenants) > 1:
            conflicts.append("source_channel_override_conflict")
        selected = channel_assignments[0]
        return selected, "source_channel_override", conflicts

    return default_config, "default_scope", conflicts


def _normalize_profile_for_backfill(
    profile: dict[str, Any],
    *,
    assignment: dict[str, str],
) -> dict[str, Any]:
    profile_identifier = _profile_id(profile)
    return {
        **deepcopy(profile),
        "id": profile_identifier,
        "user_id": profile_identifier,
        "tenant_id": assignment["tenant_id"],
        "tenant_name": assignment["tenant_name"],
        "tenant_status": assignment["tenant_status"],
        "name": _normalize_text(profile.get("name")) or profile_identifier,
        "source_channels": _normalize_source_channels(
            profile.get("source_channels") or profile.get("sourceChannels")
        ),
        "platform_accounts": _normalize_platform_accounts(
            profile.get("platform_accounts") or profile.get("platformAccounts")
        ),
        "tags": _normalize_tags(profile.get("tags")),
        "preferred_language": _normalize_language(
            profile.get("preferred_language") or profile.get("preferredLanguage")
        ),
        "notes": _normalize_text(profile.get("notes")),
        "last_active_at": _normalize_timestamp(
            profile.get("last_active_at"),
            profile.get("lastActiveAt"),
            profile.get("last_login"),
            profile.get("updated_at"),
            profile.get("created_at"),
        ),
        "total_interactions": _normalize_interaction_count(
            profile.get("total_interactions") or profile.get("totalInteractions")
        ),
    }


def _write_snapshot(snapshot_dir: Path, payload: dict[str, Any]) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    snapshot_path = snapshot_dir / f"tenant_profile_snapshot_{stamp}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_path


def _persist_profiles(
    service: StatePersistenceService,
    runtime_store: InMemoryStore,
    profiles: list[dict[str, Any]],
) -> None:
    if service.enabled:
        for profile in profiles:
            service.persist_user_state(profile=profile)
    for profile in profiles:
        profile_identifier = _profile_id(profile)
        runtime_store.user_profiles[profile_identifier] = deepcopy(profile)


def _remove_profiles_not_in_snapshot(
    service: StatePersistenceService,
    snapshot_ids: set[str],
) -> int:
    if not service.enabled or service._session_factory is None:
        return 0

    with service._session_factory() as session:
        existing_ids = {
            _normalize_text(row.user_id)
            for row in session.scalars(select(UserProfileRecord)).all()
        }
        removed_ids = existing_ids - snapshot_ids
        if removed_ids:
            session.execute(delete(UserProfileRecord).where(UserProfileRecord.user_id.in_(removed_ids)))
            session.commit()
        return len(removed_ids)


def run_tenant_profile_backfill(
    *,
    database_url: str | None = None,
    runtime_store: InMemoryStore | None = None,
    apply: bool = False,
    snapshot_dir: str | None = None,
    override_path: str | None = None,
    override_payload: dict[str, Any] | None = None,
    default_tenant_id: str | None = None,
    default_tenant_name: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_store = runtime_store or store
    service = StatePersistenceService(runtime_store=resolved_runtime_store, database_url=database_url)
    service.initialize()

    try:
        source_profiles = _load_profiles(service, resolved_runtime_store)
        default_config = _default_tenant_config(
            default_tenant_id=default_tenant_id,
            default_tenant_name=default_tenant_name,
        )
        overrides = _load_overrides(override_path, payload=override_payload)
        audit_logs = service.list_audit_logs() or []
        message_counts = _message_counts(service)
        task_counts = _task_counts(service)

        normalized_profiles: list[dict[str, Any]] = []
        changed_profiles: list[dict[str, Any]] = []
        tenant_counter: Counter[tuple[str, str, str]] = Counter()
        cross_tenant_accounts: dict[str, dict[str, Any]] = {}
        same_tenant_duplicates: dict[str, dict[str, Any]] = {}
        profile_associations: list[dict[str, Any]] = []
        resolution_conflicts: list[dict[str, Any]] = []

        account_occurrences: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)

        for original_profile in source_profiles:
            profile_identifier = _profile_id(original_profile)
            if not profile_identifier:
                continue

            assignment, resolution_source, assignment_conflicts = _resolve_tenant_assignment(
                original_profile,
                overrides=overrides,
                default_config=default_config,
            )
            normalized_profile = _normalize_profile_for_backfill(
                original_profile,
                assignment=assignment,
            )
            normalized_profiles.append(normalized_profile)
            tenant_counter[(
                normalized_profile["tenant_id"],
                normalized_profile["tenant_name"],
                normalized_profile["tenant_status"],
            )] += 1

            if normalized_profile != original_profile:
                changed_profiles.append(
                    {
                        "id": profile_identifier,
                        "resolution_source": resolution_source,
                        "tenant_id": normalized_profile["tenant_id"],
                        "tenant_name": normalized_profile["tenant_name"],
                    }
                )

            if assignment_conflicts:
                resolution_conflicts.append(
                    {
                        "id": profile_identifier,
                        "conflicts": assignment_conflicts,
                    }
                )

            for account in normalized_profile["platform_accounts"]:
                account_occurrences[_account_key(account["platform"], account["account_id"])].append(
                    (profile_identifier, normalized_profile["tenant_id"])
                )

            profile_associations.append(
                {
                    "id": profile_identifier,
                    "tenant_id": normalized_profile["tenant_id"],
                    "message_count": message_counts.get(profile_identifier, 0),
                    "task_count": task_counts.get(profile_identifier, 0),
                    "audit_candidate_count": _audit_match_count(normalized_profile, audit_logs),
                }
            )

        for account_key, occurrences in account_occurrences.items():
            tenant_ids = sorted({tenant_id for _, tenant_id in occurrences})
            profile_ids = sorted({profile_id for profile_id, _ in occurrences})
            if len(tenant_ids) > 1:
                cross_tenant_accounts[account_key] = {
                    "account_key": account_key,
                    "tenant_ids": tenant_ids,
                    "profile_ids": profile_ids,
                }
            elif len(profile_ids) > 1:
                same_tenant_duplicates[account_key] = {
                    "account_key": account_key,
                    "tenant_id": tenant_ids[0] if tenant_ids else "",
                    "profile_ids": profile_ids,
                }

        snapshot_path: Path | None = None
        if apply:
            snapshot_payload = {
                "captured_at": utc_now_iso(),
                "database_url": service.database_url,
                "profiles": source_profiles,
            }
            snapshot_path = _write_snapshot(
                Path(snapshot_dir).expanduser().resolve() if snapshot_dir else DEFAULT_SNAPSHOT_DIR,
                snapshot_payload,
            )
            _persist_profiles(service, resolved_runtime_store, normalized_profiles)

        return {
            "ok": True,
            "mode": "apply" if apply else "plan",
            "generated_at": utc_now_iso(),
            "database_url": service.database_url,
            "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
            "default_tenant": default_config,
            "profile_totals": {
                "loaded": len(source_profiles),
                "updated": len(changed_profiles),
                "unchanged": max(len(source_profiles) - len(changed_profiles), 0),
            },
            "tenants": [
                {
                    "tenant_id": tenant_id,
                    "tenant_name": tenant_name,
                    "tenant_status": tenant_status,
                    "profile_count": profile_count,
                }
                for (tenant_id, tenant_name, tenant_status), profile_count in sorted(tenant_counter.items())
            ],
            "overrides": {
                "profiles": len(overrides["profiles"]),
                "platform_accounts": len(overrides["platform_accounts"]),
                "channels": len(overrides["channels"]),
            },
            "changed_profiles": changed_profiles,
            "conflicts": {
                "resolution_conflicts": resolution_conflicts,
                "cross_tenant_platform_accounts": list(cross_tenant_accounts.values()),
                "duplicate_platform_accounts_within_tenant": list(same_tenant_duplicates.values()),
            },
            "associations": {
                "message_links": sum(item["message_count"] for item in profile_associations),
                "task_links": sum(item["task_count"] for item in profile_associations),
                "audit_candidates": sum(item["audit_candidate_count"] for item in profile_associations),
                "profiles": profile_associations,
            },
        }
    finally:
        service.close()


def run_tenant_profile_rollback(
    *,
    snapshot_path: str,
    database_url: str | None = None,
    runtime_store: InMemoryStore | None = None,
) -> dict[str, Any]:
    resolved_runtime_store = runtime_store or store
    resolved_snapshot_path = Path(snapshot_path).expanduser().resolve()
    snapshot_payload = json.loads(resolved_snapshot_path.read_text(encoding="utf-8"))
    snapshot_profiles = [
        deepcopy(item)
        for item in (snapshot_payload.get("profiles") or [])
        if isinstance(item, dict)
    ]
    service = StatePersistenceService(runtime_store=resolved_runtime_store, database_url=database_url)
    service.initialize()

    try:
        snapshot_ids = {_profile_id(profile) for profile in snapshot_profiles if _profile_id(profile)}
        removed_profiles = _remove_profiles_not_in_snapshot(service, snapshot_ids)

        if service.enabled:
            for profile in snapshot_profiles:
                service.persist_user_state(profile=profile)

        resolved_runtime_store.user_profiles = {
            profile_id: deepcopy(profile)
            for profile in snapshot_profiles
            if (profile_id := _profile_id(profile))
        }

        return {
            "ok": True,
            "mode": "rollback",
            "generated_at": utc_now_iso(),
            "database_url": service.database_url,
            "snapshot_path": str(resolved_snapshot_path),
            "profile_totals": {
                "restored": len(snapshot_profiles),
                "removed": removed_profiles,
            },
        }
    finally:
        service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, apply, or rollback tenant profile backfill.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--database-url", default=None)
    plan_parser.add_argument("--override-file", default=None)
    plan_parser.add_argument("--default-tenant-id", default=None)
    plan_parser.add_argument("--default-tenant-name", default=None)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--database-url", default=None)
    apply_parser.add_argument("--override-file", default=None)
    apply_parser.add_argument("--snapshot-dir", default=None)
    apply_parser.add_argument("--default-tenant-id", default=None)
    apply_parser.add_argument("--default-tenant-name", default=None)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--database-url", default=None)
    rollback_parser.add_argument("--snapshot-path", required=True)

    args = parser.parse_args()

    if args.command == "rollback":
        payload = run_tenant_profile_rollback(
            snapshot_path=args.snapshot_path,
            database_url=args.database_url,
        )
    else:
        payload = run_tenant_profile_backfill(
            database_url=args.database_url,
            apply=args.command == "apply",
            snapshot_dir=getattr(args, "snapshot_dir", None),
            override_path=args.override_file,
            default_tenant_id=args.default_tenant_id,
            default_tenant_name=args.default_tenant_name,
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
