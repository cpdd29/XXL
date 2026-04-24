from __future__ import annotations

from app.modules.reception.schemas.messages import allowed_ingest_auth_scopes


ALLOWED_AUTH_SCOPES = allowed_ingest_auth_scopes()


def is_allowed_auth_scope(auth_scope: str) -> bool:
    return str(auth_scope or "").strip() in ALLOWED_AUTH_SCOPES


def format_auth_scope_details(auth_scope: str) -> str:
    return (
        f"auth_scope={auth_scope}; "
        f"allowed_scopes={', '.join(sorted(ALLOWED_AUTH_SCOPES))}"
    )
