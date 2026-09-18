"""Architecture V2 platform-administration vs commercial-data boundary tests.

``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` section 7: a platform administrator
manages identity, providers, runtime and the capability catalogue without
automatically seeing contract prices, strategy parameters, commercial PnL or
restricted datasets. These tests pin that boundary at the API level, and pin
that every non-admin role keeps the commercial reach it had before.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.permissions import (
    COMMERCIAL_DATA_PREFIXES,
    serves_commercial_data,
)

PUBLIC_TOKEN = "test-public-api-token"

COMMERCIAL_PATH = "/api/market/observations"
PLATFORM_PATH = "/api/access/users"


def _prepare_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "boundary.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MarketObservationRecord(
                observation_id="m-1",
                market_venue="ENTSOG",
                product="NBP Day-Ahead",
                price=31.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=now,
                period_end_utc=now,
                observed_at_utc=now,
                source_system="ENTSOG",
                source_reference="test:ENTSOG",
                source_record_id="ENTSOG-1",
                freshness="live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "NBP"},
            )
        )
        session.commit()

    return database_url


def _bearer(session: Session, *, name: str, roles: list[str], scopes: list[str]) -> str:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=roles[0],
        data_scopes=scopes,
    )
    row.roles = list(roles)
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="boundary")
    return bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def test_commercial_surface_declaration_matches_the_intended_boundary() -> None:
    """Commercial paths are declared; platform paths are not."""

    assert serves_commercial_data(COMMERCIAL_PATH) is True
    assert serves_commercial_data("/api/portfolio/summary") is True
    assert serves_commercial_data("/api/strategy-lab/evaluate") is True
    assert serves_commercial_data("/api/research/datasets") is True
    assert serves_commercial_data("/api/agent/runs") is True

    assert serves_commercial_data(PLATFORM_PATH) is False
    assert serves_commercial_data("/api/audit") is False
    assert serves_commercial_data("/api/runtime/pipeline-health") is False
    assert serves_commercial_data("/api/credentials/providers") is False
    assert serves_commercial_data("/api/capabilities") is False
    assert serves_commercial_data("/api/me") is False
    assert serves_commercial_data("/api/health") is False
    assert all(
        prefix.startswith("/api/") and prefix.endswith("/") for prefix in COMMERCIAL_DATA_PREFIXES
    )


def test_platform_admin_cannot_read_commercial_data(tmp_path, monkeypatch) -> None:
    """ADMIN alone is refused commercial data and keeps the control plane."""

    _prepare_db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'boundary.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        admin_bearer = _bearer(session, name="boundary-admin", roles=["ADMIN"], scopes=[])
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    denied = client.get(COMMERCIAL_PATH, headers=_headers(admin_bearer))
    assert denied.status_code == 403
    detail = denied.json()["detail"]
    assert detail["error"] == "commercial_access_not_granted"
    assert "ANALYST" in detail["message"]

    allowed = client.get(PLATFORM_PATH, headers=_headers(admin_bearer))
    assert allowed.status_code == 200


def test_admin_with_a_commercial_assignment_keeps_full_access(tmp_path, monkeypatch) -> None:
    """Overlapping assignments: ADMIN + ANALYST reaches both planes."""

    _prepare_db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'boundary.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        both_bearer = _bearer(
            session, name="boundary-both", roles=["ADMIN", "ANALYST"], scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    commercial = client.get(COMMERCIAL_PATH, headers=_headers(both_bearer))
    assert commercial.status_code == 200
    assert [row["observation_id"] for row in commercial.json()["data"]] == ["m-1"]

    platform = client.get(PLATFORM_PATH, headers=_headers(both_bearer))
    assert platform.status_code == 200


def test_commercial_roles_and_legacy_token_are_unaffected(tmp_path, monkeypatch) -> None:
    """VIEWER/REVIEWER/ANALYST/OPERATOR and the static token keep their reach."""

    _prepare_db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'boundary.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        viewers = {
            role: _bearer(session, name=f"boundary-{role.lower()}", roles=[role], scopes=["ENTSOG"])
            for role in ("VIEWER", "REVIEWER", "ANALYST", "OPERATOR")
        }
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    for role, bearer in viewers.items():
        response = client.get(COMMERCIAL_PATH, headers=_headers(bearer))
        assert response.status_code == 200, role

    # The legacy single-trust-domain service token is unchanged.
    legacy = client.get(COMMERCIAL_PATH, headers=_headers())
    assert legacy.status_code == 200

    # A viewer still cannot reach the control plane (rank floor, unchanged).
    denied_platform = client.get(PLATFORM_PATH, headers=_headers(viewers["VIEWER"]))
    assert denied_platform.status_code == 403
    assert denied_platform.json()["detail"]["error"] == "identity_role_forbidden"


def test_platform_admin_keeps_identity_and_provider_operations(tmp_path, monkeypatch) -> None:
    """The V2 control plane stays usable for an administration-only identity."""

    _prepare_db(tmp_path, monkeypatch)
    url = f"sqlite+pysqlite:///{(tmp_path / 'boundary.sqlite').as_posix()}"
    with Session(create_engine(url, future=True)) as session:
        admin_bearer = _bearer(session, name="boundary-admin", roles=["ADMIN"], scopes=[])
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    headers = _headers(admin_bearer)

    for path in (
        PLATFORM_PATH,
        "/api/access/api-keys",
        "/api/access/sso",
        "/api/audit",
        "/api/credentials/providers",
        "/api/sources",
        "/api/runtime/pipeline-health",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.status_code)
