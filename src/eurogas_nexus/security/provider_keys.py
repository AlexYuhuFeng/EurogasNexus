"""Runtime-only provider key retrieval from encrypted PostgreSQL records."""

from __future__ import annotations


def load_provider_api_key(provider_id: str) -> str | None:
    """Return an enabled provider key for backend use without logging it."""

    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        return None
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.security.credentials import decrypt_credential_payload

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is None or row.status == "disabled":
                return None
            payload = decrypt_credential_payload(row.encrypted_payload)
            value = str(payload.get("api_key") or "").strip()
            return value or None
    except Exception:
        return None
