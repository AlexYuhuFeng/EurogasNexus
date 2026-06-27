"""Backend-owned provider credential management routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["credentials"])

ProviderId = Literal[
    "ECB",
    "ENTSOG",
    "GIE",
    "EEX",
    "ICE_OCM",
    "Trayport",
    "Kpler",
    "Platts",
    "Weather",
    "DEEPSEEK",
    "LLM",
]

PUBLIC_PROVIDERS = {"ECB", "ENTSOG"}
PROVIDERS: tuple[dict[str, object], ...] = (
    {"provider_id": "ECB", "display_name": "ECB", "credential_required": False},
    {"provider_id": "ENTSOG", "display_name": "ENTSOG", "credential_required": False},
    {"provider_id": "GIE", "display_name": "GIE AGSI/ALSI", "credential_required": True},
    {"provider_id": "EEX", "display_name": "EEX", "credential_required": True},
    {"provider_id": "ICE_OCM", "display_name": "ICE OCM", "credential_required": True},
    {"provider_id": "Trayport", "display_name": "Trayport", "credential_required": True},
    {"provider_id": "Kpler", "display_name": "Kpler", "credential_required": True},
    {"provider_id": "Platts", "display_name": "Platts", "credential_required": True},
    {"provider_id": "Weather", "display_name": "Weather", "credential_required": True},
    {"provider_id": "DEEPSEEK", "display_name": "DeepSeek LLM", "credential_required": True},
    {"provider_id": "LLM", "display_name": "Generic LLM Provider", "credential_required": True},
)


class CredentialUpdate(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)
    label: str = Field(default="default", max_length=128)


class CredentialStatusUpdate(BaseModel):
    status: Literal["enabled", "disabled"]
    reason: str = Field(default="operator-requested", max_length=256)


@router.get("/api/credentials/providers")
def list_credential_providers() -> dict:
    rows = _credential_rows()
    data = []
    for provider in PROVIDERS:
        provider_id = str(provider["provider_id"])
        row = rows.get(provider_id)
        data.append(_provider_status(provider, row))
    return _env(data)


@router.put("/api/credentials/{provider_id}")
def upsert_provider_credential(provider_id: ProviderId, payload: CredentialUpdate) -> dict:
    return _write_provider_credential(provider_id, payload)


@router.post("/api/credentials/{provider_id}/rotate")
def rotate_provider_credential(provider_id: ProviderId, payload: CredentialUpdate) -> dict:
    return _write_provider_credential(provider_id, payload)


@router.patch("/api/credentials/{provider_id}/status")
def update_provider_credential_status(
    provider_id: ProviderId,
    payload: CredentialStatusUpdate,
) -> dict:
    _ensure_private_provider(provider_id)
    if not _db_is_configured():
        raise _credential_store_unavailable("Runtime database is not configured.")

    from eurogas_nexus.security.credentials import utc_now

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is None:
                raise _credential_not_found(provider_id)
            row.status = "disabled" if payload.status == "disabled" else "configured"
            row.updated_at_utc = utc_now()
            row.last_tested_at_utc = row.updated_at_utc
            row.last_test_status = f"operator_{payload.status}"
            row.last_test_message = f"Status changed by operator: {payload.reason}"
            session.commit()
            session.refresh(row)
            return _env(_credential_status(row))
    except HTTPException:
        raise
    except sqlalchemy_error as exc:
        raise _credential_store_unavailable(exc.__class__.__name__) from exc


@router.post("/api/credentials/{provider_id}/local-validation")
def validate_provider_credential_locally(provider_id: ProviderId) -> dict:
    _ensure_private_provider(provider_id)
    if not _db_is_configured():
        raise _credential_store_unavailable("Runtime database is not configured.")

    from eurogas_nexus.security.credentials import (
        credential_store_configured,
        decrypt_credential_payload,
        fingerprint_secret_value,
        utc_now,
    )

    if not credential_store_configured():
        raise _credential_store_unavailable("Credential encryption key is not configured.")

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is None:
                raise _credential_not_found(provider_id)
            now = utc_now()
            row.last_tested_at_utc = now
            row.updated_at_utc = now
            if row.status == "disabled":
                row.last_test_status = "local_validation_skipped_disabled"
                row.last_test_message = "Credential is disabled; no provider call was made."
            else:
                try:
                    payload = decrypt_credential_payload(row.encrypted_payload)
                    api_key = str(payload.get("api_key") or "")
                    if not api_key:
                        raise ValueError("Missing api_key in credential payload.")
                    if fingerprint_secret_value(api_key) != row.credential_fingerprint:
                        raise ValueError("Credential fingerprint mismatch.")
                    row.last_test_status = "local_validation_passed"
                    row.last_test_message = (
                        "Credential payload decrypts locally; no provider call was made."
                    )
                except Exception as exc:
                    row.last_test_status = "local_validation_failed"
                    row.last_test_message = f"Local validation failed: {exc.__class__.__name__}"
            session.commit()
            session.refresh(row)
            return _env(_credential_status(row))
    except HTTPException:
        raise
    except sqlalchemy_error as exc:
        raise _credential_store_unavailable(exc.__class__.__name__) from exc


def _write_provider_credential(provider_id: ProviderId, payload: CredentialUpdate) -> dict:
    _ensure_private_provider(provider_id)
    if not _db_is_configured():
        raise _credential_store_unavailable("Runtime database is not configured.")

    from eurogas_nexus.security.credentials import (
        credential_store_configured,
        encrypt_credential_payload,
        utc_now,
    )

    if not credential_store_configured():
        raise _credential_store_unavailable("Credential encryption key is not configured.")

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        encrypted = encrypt_credential_payload({"api_key": payload.api_key})
        now = utc_now()
        with get_session_factory()() as session:
            existing = session.get(ProviderCredentialRecord, provider_id)
            created_at = existing.created_at_utc if existing else now
            session.merge(
                ProviderCredentialRecord(
                    provider_id=provider_id,
                    label=payload.label,
                    encrypted_payload=encrypted.encrypted_payload,
                    redacted_preview=encrypted.redacted_preview,
                    credential_fingerprint=encrypted.credential_fingerprint,
                    status="configured",
                    created_at_utc=created_at,
                    updated_at_utc=now,
                    last_tested_at_utc=None,
                    last_test_status=None,
                    last_test_message=None,
                    research_only=True,
                    human_review_required=True,
                )
            )
            session.commit()
            row = session.get(ProviderCredentialRecord, provider_id)
            return _env(_credential_status(row))
    except sqlalchemy_error as exc:
        raise _credential_store_unavailable(exc.__class__.__name__) from exc


def _ensure_private_provider(provider_id: ProviderId) -> None:
    if provider_id in PUBLIC_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "credential_not_required",
                "message": (
                    f"{provider_id} does not require an API key for the supported public feed."
                ),
            },
        )


@router.delete("/api/credentials/{provider_id}")
def delete_provider_credential(provider_id: ProviderId) -> dict:
    if not _db_is_configured():
        raise _credential_store_unavailable("Runtime database is not configured.")

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is not None:
                session.delete(row)
                session.commit()
        return _env({"provider_id": provider_id, "configured": False})
    except sqlalchemy_error as exc:
        raise _credential_store_unavailable(exc.__class__.__name__) from exc


def _credential_rows() -> dict[str, object]:
    if not _db_is_configured():
        return {}

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(ProviderCredentialRecord).all()
            return {row.provider_id: row for row in rows}
    except sqlalchemy_error:
        return {}


def _provider_status(provider: dict[str, object], row: object | None) -> dict:
    provider_id = str(provider["provider_id"])
    base = {
        "provider_id": provider_id,
        "display_name": provider["display_name"],
        "credential_required": provider["credential_required"],
        "configured": False,
        "status": "public" if provider_id in PUBLIC_PROVIDERS else "missing",
        "redacted_preview": None,
        "last_tested_at_utc": None,
        "last_test_status": None,
    }
    if row is None:
        return base
    return base | _credential_status(row)


def _credential_status(row: object) -> dict:
    return {
        "provider_id": row.provider_id,
        "label": row.label,
        "configured": row.status != "disabled",
        "status": row.status,
        "redacted_preview": row.redacted_preview,
        "last_tested_at_utc": _iso(row.last_tested_at_utc),
        "last_test_status": row.last_test_status,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _credential_store_unavailable(message: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "credential_store_not_configured",
            "message": message,
        },
    )


def _credential_not_found(provider_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "credential_not_found",
            "message": f"No credential is stored for {provider_id}.",
        },
    )


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(data: object) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": ["Credential values are write-only and never returned by the API."],
        },
    }
