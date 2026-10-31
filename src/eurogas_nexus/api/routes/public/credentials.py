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
    "ICIS",
    "Argus",
    "Trayport",
    "Kpler",
    "Platts",
    "Weather",
    "DEEPSEEK",
    "LLM",
]

PUBLIC_PROVIDERS = {"ECB", "ENTSOG"}

#: Providers whose live connection test is implemented by the backend. The API
#: reports this per provider as a capability flag so the UI derives support from
#: the backend instead of hardcoding a provider list of its own.
CONNECTION_TEST_PROVIDERS = frozenset({"DEEPSEEK", "LLM", "GIE"})

#: The two GIE products probed independently by the bounded connection test.
GIE_CONNECTION_PRODUCTS = ("AGSI", "ALSI")
PROVIDERS: tuple[dict[str, object], ...] = (
    {"provider_id": "ECB", "display_name": "ECB", "credential_required": False},
    {"provider_id": "ENTSOG", "display_name": "ENTSOG", "credential_required": False},
    {"provider_id": "GIE", "display_name": "GIE AGSI/ALSI", "credential_required": True},
    {"provider_id": "EEX", "display_name": "EEX", "credential_required": True},
    {"provider_id": "ICE_OCM", "display_name": "ICE OCM", "credential_required": True},
    {"provider_id": "ICIS", "display_name": "ICIS", "credential_required": True},
    {"provider_id": "Argus", "display_name": "Argus", "credential_required": True},
    {"provider_id": "Trayport", "display_name": "Trayport", "credential_required": True},
    {"provider_id": "Kpler", "display_name": "Kpler", "credential_required": True},
    {"provider_id": "Platts", "display_name": "Platts", "credential_required": True},
    {"provider_id": "Weather", "display_name": "Weather", "credential_required": True},
    {
        "provider_id": "DEEPSEEK",
        "display_name": "DeepSeek V4 Flash",
        "credential_required": True,
        "default_model": "deepseek-v4-flash",
    },
    {"provider_id": "LLM", "display_name": "Generic LLM Provider", "credential_required": True},
)


class CredentialUpdate(BaseModel):
    """Payload for setting or rotating one provider API key.

    Attributes:
        api_key: The provider API key (1-4096 chars).
        label: Key label (max 128 chars).
    """

    api_key: str = Field(min_length=1, max_length=4096)
    label: str = Field(default="default", max_length=128)


class CredentialStatusUpdate(BaseModel):
    """Payload for enabling/disabling one provider credential.

    Attributes:
        status: ``enabled`` or ``disabled``.
        reason: Operator-supplied reason (max 256 chars).
    """

    status: Literal["enabled", "disabled"]
    reason: str = Field(default="operator-requested", max_length=256)


@router.get("/api/credentials/providers")
def list_credential_providers() -> dict:
    """List credential providers with their current status.

    列出全部凭据提供商及各自状态（是否已配置/启用的摘要）。

    Returns:
        Enveloped provider status list.
    """

    rows = _credential_rows()
    gie_status = _gie_external_credential_status()
    data = []
    for provider in PROVIDERS:
        provider_id = str(provider["provider_id"])
        row = rows.get(provider_id)
        status = _provider_status(provider, row)
        status["connection_test_supported"] = provider_id in CONNECTION_TEST_PROVIDERS
        if provider_id == "GIE":
            status.update(gie_status)
        data.append(status)
    return _env(data)


@router.put("/api/credentials/{provider_id}")
def upsert_provider_credential(provider_id: ProviderId, payload: CredentialUpdate) -> dict:
    """Upsert (set or replace) one provider's API key.

    写入/替换指定提供商的 API 密钥（加密落库，绝不回显明文）。

    Args:
        provider_id: Provider id (validated enum).
        payload: New key and label.

    Returns:
        Enveloped stored credential status.

    Raises:
        HTTPException: 404 unknown provider; 503 credential store unavailable.
    """

    return _write_provider_credential(provider_id, payload)


@router.post("/api/credentials/{provider_id}/rotate")
def rotate_provider_credential(provider_id: ProviderId, payload: CredentialUpdate) -> dict:
    """Rotate one provider's API key (same write path as upsert).

    轮换提供商 API 密钥（与 upsert 同一写入路径，语义上标记为轮换）。

    Args:
        provider_id: Provider id (validated enum).
        payload: New key and label.

    Returns:
        Enveloped stored credential status.

    Raises:
        HTTPException: 404 unknown provider; 503 credential store unavailable.
    """

    return _write_provider_credential(provider_id, payload)


@router.patch("/api/credentials/{provider_id}/status")
def update_provider_credential_status(
    provider_id: ProviderId,
    payload: CredentialStatusUpdate,
) -> dict:
    """Enable or disable one provider's credential.

    启用/禁用指定提供商的凭据并记录操作原因。

    Args:
        provider_id: Provider id (validated enum).
        payload: Status change and reason.

    Returns:
        Enveloped updated credential status.

    Raises:
        HTTPException: 404 unknown provider or missing credential;
            503 credential store unavailable.
    """

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
    """Validate one provider's credential locally (syntax/shape checks).

    本地校验提供商凭据（仅语法/形态检查，不发起外部连接测试）。

    Args:
        provider_id: Provider id (validated enum).

    Returns:
        Enveloped validation outcome.

    Raises:
        HTTPException: 404 unknown provider or missing credential;
            503 credential store unavailable.
    """

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


@router.post("/api/credentials/{provider_id}/connection-test")
def test_provider_credential_connection(provider_id: ProviderId) -> dict:
    """Perform an explicit live provider check without returning the credential."""

    _ensure_private_provider(provider_id)
    if provider_id not in CONNECTION_TEST_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "connection_test_not_supported",
                "message": (
                    f"A governed live connection test is not implemented for {provider_id}."
                ),
            },
        )
    if not _db_is_configured():
        raise _credential_store_unavailable("Runtime database is not configured.")

    if provider_id == "GIE":
        return _connection_test_gie()

    from eurogas_nexus.llm import test_deepseek_connection
    from eurogas_nexus.security.credentials import utc_now
    from eurogas_nexus.security.provider_keys import load_provider_api_key

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        api_key = load_provider_api_key(provider_id)
        result = test_deepseek_connection(api_key=api_key or "")
        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is None:
                raise _credential_not_found(provider_id)
            now = utc_now()
            row.last_tested_at_utc = now
            row.updated_at_utc = now
            row.last_test_status = f"connection_test_{result.status}"
            row.last_test_message = (
                "Live DeepSeek connection test passed."
                if result.status == "success"
                else f"Live DeepSeek connection test failed: {result.error_code or result.status}"
            )
            session.commit()
            session.refresh(row)
            return _env(
                _credential_status(row)
                | {
                    "connection_status": result.status,
                    "connection_error_code": result.error_code,
                }
            )
    except HTTPException:
        raise
    except sqlalchemy_error as exc:
        raise _credential_store_unavailable(exc.__class__.__name__) from exc


def _connection_test_gie() -> dict:
    """Bounded one-page live connection test for GIE AGSI and ALSI.

    Deliberately distinct from certification: a passing check is transport
    connectivity plus envelope/normalization shape for the two products, not a
    certification decision. The test writes no market data, inserts no fake
    encrypted credential row when the key is externally configured, and never
    returns provider payload text -- only aggregate counts, the provider's
    advertised page count and stable error codes.
    """

    import httpx

    from eurogas_nexus.ingestion.gie_transport import (
        GIE_PRODUCT_HOSTS,
        GieProduct,
        test_gie_connection,
    )
    from eurogas_nexus.security.credentials import utc_now

    status = _gie_external_credential_status()
    if not status["configured"]:
        return _env(
            _gie_base_status(status)
            | {
                "connection": {
                    "ok": False,
                    "error_code": (status["credential_diagnostics"] or ["gie_credential_missing"])[
                        0
                    ],
                    "products": [],
                    "tested_at_utc": utc_now().isoformat(),
                }
            }
        )

    api_key = _resolve_gie_api_key_value()
    products = (
        GieProduct.agsi(f"https://{GIE_PRODUCT_HOSTS['AGSI']}/api"),
        GieProduct.alsi(f"https://{GIE_PRODUCT_HOSTS['ALSI']}/api"),
    )
    with httpx.Client(
        timeout=30.0,
        follow_redirects=False,
        headers={"User-Agent": "EurogasNexus/0.5 gie-connection-test"},
    ) as client:
        checks = test_gie_connection(client, api_key=api_key or "", products=products)

    product_payloads = [
        {
            "product": check.product,
            "ok": check.ok,
            "error_code": check.error_code,
            "http_status": check.http_status,
            "record_count": check.record_count,
            "normalized_rows": check.normalized_rows,
            "provider_last_page": check.provider_last_page,
            "page_size": check.page_size,
            "complete": check.complete,
            "bounded_partial": check.bounded_partial,
            "response_date": check.response_date,
        }
        for check in checks
    ]
    aggregate_ok = bool(checks) and all(check.ok for check in checks)
    aggregate_error = next((check.error_code for check in checks if not check.ok), None)
    now = utc_now()

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, "GIE")
            if row is not None:
                # An externally configured key has no stored row: the test must
                # not insert a fake encrypted credential just to record status.
                row.last_tested_at_utc = now
                row.updated_at_utc = now
                row.last_test_status = (
                    "connection_test_success"
                    if aggregate_ok
                    else f"connection_test_{aggregate_error or 'failed'}"
                )
                row.last_test_message = (
                    "Bounded one-page GIE AGSI/ALSI connection test passed; this is "
                    "not a certification decision."
                    if aggregate_ok
                    else "Bounded one-page GIE connection test failed; see connection error code."
                )
                session.commit()
    except sqlalchemy_error as exc:
        raise _credential_store_unavailable(exc.__class__.__name__) from exc

    return _env(
        _gie_base_status(status)
        | {
            "connection": {
                "ok": aggregate_ok,
                "error_code": aggregate_error,
                "products": product_payloads,
                "tested_at_utc": now.isoformat(),
                "bounded": True,
                "market_data_persisted": False,
            },
        }
    )


def _gie_base_status(status: dict) -> dict:
    return {
        "provider_id": "GIE",
        "configured": status["configured"],
        "status": status["status"],
        "credential_source_kind": status["credential_source_kind"],
        "credential_diagnostics": status["credential_diagnostics"],
        "support_flags": status["support_flags"],
        "connection_test_supported": True,
        "certification": status["certification"],
    }


def _resolve_gie_api_key_value() -> str | None:
    """Resolve the runtime GIE key value in memory only; never store or return it.

    Uses the shared runtime resolver so the operator-disable enforcement at the
    fetch boundary and the reported status cannot disagree.
    """

    from eurogas_nexus.ingestion.gie_transport import resolve_gie_runtime_api_key

    resolved = resolve_gie_runtime_api_key()
    return resolved.value if resolved is not None else None


def _gie_external_credential_status() -> dict:
    """Shared resolver-derived GIE status with only safe codes and flags.

    The same runtime resolver the fetch path uses decides the reported status, so
    an operator-disabled stored credential or a disabled source operation keeps
    the status blocked -- external environment/file configuration cannot silently
    re-enable it. An unreadable operator state is reported blocked with its own
    diagnostic rather than as a confirmed permit.
    """

    from eurogas_nexus.ingestion.gie_transport import (
        resolve_gie_runtime_credential_status,
    )

    resolved = resolve_gie_runtime_credential_status()
    return {
        "configured": resolved.configured,
        "status": (
            "configured" if resolved.configured else ("disabled" if resolved.blocked else "missing")
        ),
        "credential_source_kind": resolved.source_kind,
        "credential_diagnostics": list(resolved.diagnostics),
        "support_flags": list(resolved.support_flags),
        "certification": _gie_certification_status(),
    }


def _gie_certification_status() -> dict:
    """Report the existing certification gate state without changing it."""

    try:
        from eurogas_nexus.db.repositories.certification import latest_certification
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.domain.ingestion.certification import certification_gate

        with get_session_factory()() as session:
            certification = latest_certification(session, "GIE")
    except Exception:  # noqa: BLE001 - a status read must never fail the probe
        certification = None
    stage = (certification or {}).get("stage", "unverified")
    gate = certification_gate(
        "GIE",
        stage=stage,
        checks=(certification or {}).get("checks"),
    )
    return {
        "stage": stage,
        "allows_live": gate.allows_live,
        "reason": gate.reason,
    }


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
        from eurogas_nexus.db.models import MonitoringAlertRecord, ProviderCredentialRecord
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
            from eurogas_nexus.db.repositories.audit import record_audit_event

            record_audit_event(
                session,
                event_type="credential.upsert",
                principal="operator",
                action="upsert_credential",
                resource=f"provider_credential:{provider_id}",
                outcome="configured",
                severity="warning",
                source_system="credentials",
                now_utc=now,
            )
            if provider_id in {"DEEPSEEK", "LLM"}:
                session.query(MonitoringAlertRecord).filter(
                    MonitoringAlertRecord.status == "open",
                    MonitoringAlertRecord.llm_status == "missing_credential",
                ).update(
                    {
                        MonitoringAlertRecord.llm_status: "pending",
                        MonitoringAlertRecord.llm_last_attempt_at_utc: None,
                    },
                    synchronize_session=False,
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
    """Delete one provider's stored credential (audited).

    删除指定提供商的凭据并写审计事件（credential.delete）。

    Args:
        provider_id: Provider id (validated enum).

    Returns:
        Enveloped confirmation with ``configured=False``.

    Raises:
        HTTPException: 503 credential store unavailable.
    """

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
                from eurogas_nexus.db.repositories.audit import record_audit_event

                record_audit_event(
                    session,
                    event_type="credential.delete",
                    principal="operator",
                    action="delete_credential",
                    resource=f"provider_credential:{provider_id}",
                    outcome="deleted",
                    severity="warning",
                    source_system="credentials",
                )
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
        "default_model": provider.get("default_model"),
        "label": None,
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
        "default_model": ("deepseek-v4-flash" if row.provider_id == "DEEPSEEK" else None),
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
