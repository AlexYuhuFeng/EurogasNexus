"""Identity key rotation preserves scope, expiry, and operator attribution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.identity import IdentityApiKeyRecord
from eurogas_nexus.db.repositories.identity import (
    authenticate_identity_bearer,
    create_identity_api_key,
    create_identity_principal,
    rotate_identity_api_key,
)
from eurogas_nexus.security.identity import IdentityAuthError, principal_allows_source_family

PUBLIC_TOKEN = "test-public-api-token"
INTERNAL_TOKEN = "test-internal-token"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


@pytest.fixture()
def sqlite_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_rotation_preserves_nonempty_scopes_and_attenuation(sqlite_session):
    principal = create_identity_principal(
        sqlite_session,
        name="rotation-scoped",
        display_name="Rotation scoped",
        role="ANALYST",
        data_scopes=["EEX", "Trayport"],
    )
    old, old_bearer = create_identity_api_key(
        sqlite_session,
        principal.principal_id,
        scopes=["EEX"],
    )

    new, new_bearer = rotate_identity_api_key(
        sqlite_session,
        principal.principal_id,
        old.key_id,
        created_by="ops-admin",
    )

    assert new.key_id != old.key_id
    assert new.scopes == ["EEX"]
    assert new.created_by == "ops-admin"
    assert old.revoked_at_utc is not None

    with pytest.raises(IdentityAuthError) as exc_info:
        authenticate_identity_bearer(sqlite_session, old_bearer)
    assert exc_info.value.code == "identity_key_revoked"

    authenticated = authenticate_identity_bearer(sqlite_session, new_bearer)
    assert authenticated.data_scopes == ("EEX",)
    assert principal_allows_source_family(authenticated, "EEX_Sim") is True
    assert principal_allows_source_family(authenticated, "Trayport") is False


@pytest.mark.parametrize(
    "old_expiry",
    [None, datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)],
)
def test_rotation_preserves_old_expiry_when_unspecified(sqlite_session, old_expiry):
    principal = create_identity_principal(
        sqlite_session,
        name="rotation-expiry",
        display_name="Rotation expiry",
        role="VIEWER",
    )
    old, _ = create_identity_api_key(
        sqlite_session,
        principal.principal_id,
        expires_at_utc=old_expiry,
        scopes=["EEX"],
    )

    new, _ = rotate_identity_api_key(sqlite_session, principal.principal_id, old.key_id)

    assert (new.expires_at_utc is None) is (old_expiry is None)
    if old_expiry is not None:
        assert new.expires_at_utc is not None
        assert _utc(new.expires_at_utc) == _utc(old_expiry)


def test_rotation_explicit_none_expiry_also_preserves_old_expiry(sqlite_session):
    old_expiry = datetime(2030, 2, 3, 4, 5, 6, tzinfo=UTC)
    principal = create_identity_principal(
        sqlite_session,
        name="rotation-explicit-none",
        display_name="Rotation explicit none",
        role="VIEWER",
    )
    old, _ = create_identity_api_key(
        sqlite_session,
        principal.principal_id,
        expires_at_utc=old_expiry,
    )

    new, _ = rotate_identity_api_key(
        sqlite_session,
        principal.principal_id,
        old.key_id,
        expires_at_utc=None,
    )

    assert new.expires_at_utc is not None
    assert _utc(new.expires_at_utc) == _utc(old_expiry)


def test_rotation_explicit_expiry_is_honored(sqlite_session):
    old_expiry = datetime(2030, 3, 4, 5, 6, 7, tzinfo=UTC)
    override = old_expiry + timedelta(days=30)
    principal = create_identity_principal(
        sqlite_session,
        name="rotation-override",
        display_name="Rotation override",
        role="VIEWER",
    )
    old, _ = create_identity_api_key(
        sqlite_session,
        principal.principal_id,
        expires_at_utc=old_expiry,
    )

    new, _ = rotate_identity_api_key(
        sqlite_session,
        principal.principal_id,
        old.key_id,
        expires_at_utc=override,
    )

    assert new.expires_at_utc is not None
    assert _utc(new.expires_at_utc) == _utc(override)


def test_wrong_owner_or_missing_key_does_not_replace_or_revoke_other_owner(sqlite_session):
    owner = create_identity_principal(
        sqlite_session,
        name="rotation-owner",
        display_name="Rotation owner",
        role="VIEWER",
    )
    other = create_identity_principal(
        sqlite_session,
        name="rotation-other",
        display_name="Rotation other",
        role="VIEWER",
    )
    other_key, other_bearer = create_identity_api_key(
        sqlite_session,
        other.principal_id,
        scopes=["EEX"],
    )
    original_count = sqlite_session.query(IdentityApiKeyRecord).count()

    assert rotate_identity_api_key(sqlite_session, owner.principal_id, other_key.key_id) is None
    assert other_key.revoked_at_utc is None
    assert sqlite_session.query(IdentityApiKeyRecord).count() == original_count
    assert (
        authenticate_identity_bearer(sqlite_session, other_bearer).principal_id
        == other.principal_id
    )

    assert rotate_identity_api_key(sqlite_session, owner.principal_id, "missing-key") is None
    assert sqlite_session.query(IdentityApiKeyRecord).count() == original_count


def _db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "identity.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _internal_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="internal")))


def _release_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="release")))


def _internal_headers() -> dict[str, str]:
    return {
        "X-Eurogas-Internal-Token": INTERNAL_TOKEN,
        "X-Eurogas-Principal": "ops-admin",
    }


def _identity_headers(bearer: str) -> dict[str, str]:
    return {
        "X-Eurogas-Api-Key": PUBLIC_TOKEN,
        "X-Eurogas-Identity": bearer,
    }


def _create_identity(client: TestClient, *, name: str, scopes: list[str]) -> dict:
    response = client.post(
        "/api/internal/identities",
        headers=_internal_headers(),
        json={
            "name": name,
            "display_name": name.title(),
            "principal_type": "USER",
            "role": "ANALYST",
            "data_scopes": scopes,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_rotate_route_passes_validated_operator_and_retains_expiry_scopes(
    tmp_path, monkeypatch
) -> None:
    database_url = _db(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", INTERNAL_TOKEN)
    internal = _internal_client()
    release = _release_client()
    principal = _create_identity(
        internal,
        name="rotation-api",
        scopes=["EEX", "Trayport"],
    )

    old_expiry = datetime(2030, 4, 5, 6, 7, 8, tzinfo=UTC)
    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            old_key, old_bearer = create_identity_api_key(
                session,
                principal["principal_id"],
                display_name="scoped-old",
                expires_at_utc=old_expiry,
                scopes=["EEX"],
                created_by="seed",
            )
            old_key_id = old_key.key_id
            session.commit()
    finally:
        engine.dispose()

    response = internal.post(
        f"/api/internal/identities/{principal['principal_id']}/keys/{old_key_id}/rotate",
        headers=_internal_headers(),
        json={"display_name": "rotated-key"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    new_bearer = data["api_key"]
    new_key = data["key"]
    assert new_bearer != old_bearer
    assert _parse_utc(new_key["expires_at_utc"]) == _utc(old_expiry)

    old_health = release.get("/api/health", headers=_identity_headers(old_bearer))
    assert old_health.status_code == 403
    assert old_health.json()["detail"]["error"] == "identity_key_revoked"
    new_health = release.get("/api/health", headers=_identity_headers(new_bearer))
    assert new_health.status_code == 200

    listed = internal.get("/api/internal/identities", headers=_internal_headers()).json()["data"]
    listed_principal = next(
        row for row in listed if row["principal_id"] == principal["principal_id"]
    )
    listed_key = next(
        key for key in listed_principal["keys"] if key["key_id"] == new_key["key_id"]
    )
    assert listed_key["scopes"] == ["EEX"]
    assert listed_key["created_by"] == "ops-admin"
    assert _parse_utc(listed_key["expires_at_utc"]) == _utc(old_expiry)

    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            authenticated = authenticate_identity_bearer(session, new_bearer)
            assert authenticated.data_scopes == ("EEX",)
            assert principal_allows_source_family(authenticated, "EEX_Sim") is True
            assert principal_allows_source_family(authenticated, "Trayport") is False
    finally:
        engine.dispose()
